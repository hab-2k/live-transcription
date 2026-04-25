import AVFoundation
import CoreGraphics
import CoreMedia
import Foundation
import ScreenCaptureKit

enum ScreenCaptureKitCaptureError: Error, CustomStringConvertible {
    case conversionFailed
    case unsupportedAudioFormat

    var description: String {
        switch self {
        case .conversionFailed:
            return "Failed to convert ScreenCaptureKit audio to float32 PCM."
        case .unsupportedAudioFormat:
            return "ScreenCaptureKit returned an unsupported audio buffer format."
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
        let configuration = SCStreamConfiguration()
        configuration.capturesAudio = true
        configuration.sampleRate = targetSampleRate
        configuration.channelCount = 1
        configuration.excludesCurrentProcessAudio = true

        let filter = SCContentFilter(
            display: resolvedTarget.display,
            including: [resolvedTarget.application],
            exceptingWindows: []
        )
        let stream = SCStream(filter: filter, configuration: configuration, delegate: self)
        self.stream = stream

        try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: outputQueue)
        try await startCapture(stream)
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

        await stopCapture(stream)
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

    private func startCapture(_ stream: SCStream) async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            stream.startCapture { error in
                if let error {
                    continuation.resume(throwing: error)
                } else {
                    continuation.resume()
                }
            }
        }
    }

    private func stopCapture(_ stream: SCStream) async {
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            stream.stopCapture { _ in
                continuation.resume()
            }
        }
    }
}
