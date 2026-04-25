import Foundation

enum Command {
    case status
    case requestPermission
    case listTargets
    case capture(targetID: String, sampleRate: Int)
}

enum CommandLineError: Error, CustomStringConvertible {
    case usage
    case missingTargetID
    case invalidSampleRate(String)

    var description: String {
        switch self {
        case .usage:
            return """
            Usage: system-audio-capture --status
                   system-audio-capture --request-permission
                   system-audio-capture --list-targets
                   system-audio-capture --capture --target-id <id> [--sample-rate <rate>]
            """
        case .missingTargetID:
            return "Missing required --target-id argument."
        case .invalidSampleRate(let value):
            return "Invalid sample rate: \(value)"
        }
    }
}

@available(macOS 14.0, *)
enum RuntimeState {
    static var activeCapture: ScreenCaptureKitAudioCapture?
    static var signalSources: [DispatchSourceSignal] = []
}

@available(macOS 14.0, *)
private func runCommand(_ command: Command) async throws {
    switch command {
    case .status:
        try printJSONObject(ShareableContentCatalog.statusObject())
        exit(0)
    case .requestPermission:
        try printJSONObject(ShareableContentCatalog.requestPermissionObject())
        exit(0)
    case .listTargets:
        try printJSONObject(try await ShareableContentCatalog.listTargetObjects())
        exit(0)
    case let .capture(targetID, sampleRate):
        let capture = ScreenCaptureKitAudioCapture(
            targetID: targetID,
            targetSampleRate: sampleRate
        )
        RuntimeState.activeCapture = capture
        installSignalHandlers()
        try await capture.start()
    }
}

private func parseCommand(arguments: [String]) throws -> Command {
    let args = Array(arguments.dropFirst())

    if args.contains("--status") {
        return .status
    }

    if args.contains("--request-permission") {
        return .requestPermission
    }

    if args.contains("--list-targets") {
        return .listTargets
    }

    guard args.contains("--capture") else {
        throw CommandLineError.usage
    }

    guard let targetIndex = args.firstIndex(of: "--target-id"),
          targetIndex + 1 < args.count else {
        throw CommandLineError.missingTargetID
    }
    let targetID = args[targetIndex + 1]

    let sampleRate: Int
    if let sampleRateIndex = args.firstIndex(of: "--sample-rate") {
        guard sampleRateIndex + 1 < args.count else {
            throw CommandLineError.usage
        }

        let sampleRateValue = args[sampleRateIndex + 1]
        guard let parsedSampleRate = Int(sampleRateValue) else {
            throw CommandLineError.invalidSampleRate(sampleRateValue)
        }
        sampleRate = parsedSampleRate
    } else {
        sampleRate = 16_000
    }

    return .capture(targetID: targetID, sampleRate: sampleRate)
}

private func printJSONObject(_ object: Any) throws {
    let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data([0x0A]))
}

@available(macOS 14.0, *)
private func installSignalHandlers() {
    signal(SIGTERM, SIG_IGN)
    signal(SIGINT, SIG_IGN)

    let terminateSource = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
    terminateSource.setEventHandler {
        Task {
            await stopActiveCaptureAndExit(code: 0)
        }
    }
    terminateSource.resume()

    let interruptSource = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
    interruptSource.setEventHandler {
        Task {
            await stopActiveCaptureAndExit(code: 0)
        }
    }
    interruptSource.resume()

    RuntimeState.signalSources = [terminateSource, interruptSource]
}

@available(macOS 14.0, *)
private func stopActiveCaptureAndExit(code: Int32) async {
    if let activeCapture = RuntimeState.activeCapture {
        await activeCapture.stop()
    }

    exit(code)
}

if #available(macOS 14.0, *) {
    let command: Command
    do {
        command = try parseCommand(arguments: CommandLine.arguments)
    } catch {
        fputs("Error: \(error)\n", stderr)
        exit(1)
    }

    Task {
        do {
            try await runCommand(command)
        } catch {
            fputs("Error: \(error)\n", stderr)
            exit(1)
        }
    }

    dispatchMain()
} else {
    fputs("Error: macOS 14.0 or newer is required for ScreenCaptureKit system audio capture.\n", stderr)
    exit(1)
}
