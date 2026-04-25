// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "SystemAudioCapture",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "system-audio-capture",
            path: "Sources"
        )
    ]
)
