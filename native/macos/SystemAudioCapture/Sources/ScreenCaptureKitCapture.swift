import AVFoundation
import CoreGraphics
import CoreMedia
import Foundation
import ScreenCaptureKit

enum ScreenCaptureKitCaptureError: Error, CustomStringConvertible {
    case conversionFailed
    case unsupportedAudioFormat
    case sharingCancelled

    var description: String {
        switch self {
        case .conversionFailed:
            return "Failed to convert ScreenCaptureKit audio to float32 PCM."
        case .unsupportedAudioFormat:
            return "ScreenCaptureKit returned an unsupported audio buffer format."
        case .sharingCancelled:
            return "User cancelled the content sharing picker."
        }
    }
}

@available(macOS 14.0, *)
final class ScreenCaptureKitAudioCapture: NSObject, SCStreamOutput, SCStreamDelegate {
    let targetID: String
    let targetSampleRate: Int

    private let stdout = FileHandle.standardOutput
    private let outputQueue = DispatchQueue(label: "system-audio-capture.output", qos: .userInitiated)
    private let targetFormat: AVAudioFormat

    private var stream: SCStream?
    private var converter: AVAudioConverter?
    private var converterInputFormat: AVAudioFormat?
    private var isStopping = false
    private var pickerObserver: PickerObserver?

    init(targetID: String, targetSampleRate: Int) {
        self.targetID = targetID
        self.targetSampleRate = targetSampleRate
        self.targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: Double(targetSampleRate),
            channels: 1,
            interleaved: false
        )!
    }

    func start() async throws {
        if !CGPreflightScreenCaptureAccess() {
            _ = CGRequestScreenCaptureAccess()
            throw ShareableContentCatalogError.permissionRequired
        }

        let resolvedTarget = try await ShareableContentCatalog.resolveTarget(id: targetID)
        let configuration = buildStreamConfiguration()

        let stream = SCStream(filter: resolvedTarget.filter, configuration: configuration, delegate: self)
        self.stream = stream

        try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: outputQueue)

        do {
            try await stream.startCapture()
        } catch {
            // On macOS 15+, programmatic capture can fail if the user
            // previously stopped sharing.  Fall back to the system
            // content sharing picker to re-authorize.
            fputs("[system-audio-capture] programmatic capture failed (\(error)), presenting system sharing picker…\n", stderr)

            try? stream.removeStreamOutput(self, type: .audio)
            self.stream = nil

            let filter = try await requestFilterViaPicker()

            let retryStream = SCStream(filter: filter, configuration: configuration, delegate: self)
            self.stream = retryStream
            try retryStream.addStreamOutput(self, type: .audio, sampleHandlerQueue: outputQueue)
            try await retryStream.startCapture()
        }

        fputs("[system-audio-capture] streaming \(resolvedTarget.id) -> stdout at \(targetSampleRate) Hz\n", stderr)
    }

    func stop() async {
        isStopping = true

        guard let stream else {
            return
        }

        do {
            try stream.removeStreamOutput(self, type: .audio)
        } catch {
            // Ignore teardown failures during shutdown.
        }

        try? await stream.stopCapture()
        self.stream = nil
        self.converter = nil
        self.converterInputFormat = nil
        fputs("[system-audio-capture] stopped\n", stderr)
    }

    func stream(_ stream: SCStream, didStopWithError error: any Error) {
        guard !isStopping else {
            return
        }

        fputs("Error: \(error)\n", stderr)
        exit(1)
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of outputType: SCStreamOutputType) {
        guard outputType == .audio, sampleBuffer.isValid else {
            return
        }

        do {
            try handleAudioSampleBuffer(sampleBuffer)
        } catch {
            fputs("Error: \(error)\n", stderr)
        }
    }

    // MARK: - Private

    private func buildStreamConfiguration() -> SCStreamConfiguration {
        let configuration = SCStreamConfiguration()
        configuration.capturesAudio = true
        configuration.sampleRate = targetSampleRate
        configuration.channelCount = 1
        configuration.excludesCurrentProcessAudio = true

        // Audio-only: we don't consume video frames but SCK requires a
        // display-based content filter.  Use a small but valid size and
        // near-zero frame rate to minimize overhead.  1×1 is rejected on
        // macOS 15+, so use 16×16 as a safe minimum.
        configuration.width = 16
        configuration.height = 16
        configuration.minimumFrameInterval = CMTime(value: 10, timescale: 1)

        return configuration
    }

    private func requestFilterViaPicker() async throws -> SCContentFilter {
        try await withCheckedThrowingContinuation { continuation in
            let observer = PickerObserver(continuation: continuation)
            self.pickerObserver = observer

            let picker = SCContentSharingPicker.shared
            picker.isActive = true
            picker.add(observer)
            picker.present()
        }
    }

    private func handleAudioSampleBuffer(_ sampleBuffer: CMSampleBuffer) throws {
        try sampleBuffer.withAudioBufferList { audioBufferList, _ in
            guard let formatDescription = CMSampleBufferGetFormatDescription(sampleBuffer),
                  let streamDescription = CMAudioFormatDescriptionGetStreamBasicDescription(formatDescription),
                  let inputFormat = AVAudioFormat(streamDescription: streamDescription),
                  let inputBuffer = AVAudioPCMBuffer(
                    pcmFormat: inputFormat,
                    bufferListNoCopy: audioBufferList.unsafePointer
                  )
            else {
                throw ScreenCaptureKitCaptureError.unsupportedAudioFormat
            }

            guard inputBuffer.frameLength > 0 else {
                return
            }

            let outputBuffer = try convertBufferIfNeeded(inputBuffer, inputFormat: inputFormat)
            guard outputBuffer.frameLength > 0,
                  let channelData = outputBuffer.floatChannelData
            else {
                return
            }

            let byteCount = Int(outputBuffer.frameLength) * MemoryLayout<Float>.size
            let data = Data(bytes: channelData[0], count: byteCount)
            stdout.write(data)
        }
    }

    private func convertBufferIfNeeded(
        _ inputBuffer: AVAudioPCMBuffer,
        inputFormat: AVAudioFormat
    ) throws -> AVAudioPCMBuffer {
        if matchesTargetFormat(inputFormat) {
            return inputBuffer
        }

        if converterInputFormat != inputFormat {
            converter = AVAudioConverter(from: inputFormat, to: targetFormat)
            converterInputFormat = inputFormat
        }

        guard let converter else {
            throw ScreenCaptureKitCaptureError.conversionFailed
        }

        let frameRatio = targetFormat.sampleRate / inputFormat.sampleRate
        let outputCapacity = max(
            AVAudioFrameCount(ceil(Double(inputBuffer.frameLength) * frameRatio)),
            1
        )
        guard let outputBuffer = AVAudioPCMBuffer(
            pcmFormat: targetFormat,
            frameCapacity: outputCapacity
        ) else {
            throw ScreenCaptureKitCaptureError.conversionFailed
        }

        var converterError: NSError?
        var consumedInput = false
        let status = converter.convert(to: outputBuffer, error: &converterError) { _, status in
            if consumedInput {
                status.pointee = .noDataNow
                return nil
            }

            consumedInput = true
            status.pointee = .haveData
            return inputBuffer
        }

        if let converterError {
            throw converterError
        }

        guard status != .error else {
            throw ScreenCaptureKitCaptureError.conversionFailed
        }

        return outputBuffer
    }

    private func matchesTargetFormat(_ inputFormat: AVAudioFormat) -> Bool {
        inputFormat.sampleRate == targetFormat.sampleRate &&
            inputFormat.channelCount == targetFormat.channelCount &&
            inputFormat.commonFormat == targetFormat.commonFormat &&
            inputFormat.isInterleaved == targetFormat.isInterleaved
    }
}

// MARK: - Content Sharing Picker Observer

@available(macOS 14.0, *)
private final class PickerObserver: NSObject, SCContentSharingPickerObserver {
    private var continuation: CheckedContinuation<SCContentFilter, Error>?

    init(continuation: CheckedContinuation<SCContentFilter, Error>) {
        self.continuation = continuation
    }

    func contentSharingPicker(_ picker: SCContentSharingPicker, didCancelFor stream: SCStream?) {
        continuation?.resume(throwing: ScreenCaptureKitCaptureError.sharingCancelled)
        continuation = nil
        picker.remove(self)
        picker.isActive = false
    }

    func contentSharingPicker(_ picker: SCContentSharingPicker, didUpdateWith filter: SCContentFilter, for stream: SCStream?) {
        continuation?.resume(returning: filter)
        continuation = nil
        picker.remove(self)
        picker.isActive = false
    }

    func contentSharingPickerStartDidFailWithError(_ error: any Error) {
        continuation?.resume(throwing: error)
        continuation = nil
        SCContentSharingPicker.shared.remove(self)
        SCContentSharingPicker.shared.isActive = false
    }
}
