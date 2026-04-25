import CoreGraphics
import Foundation
import ScreenCaptureKit

let systemAudioProviderID = "screen_capture_kit"

enum ShareableContentCatalogError: Error, CustomStringConvertible {
    case permissionRequired
    case invalidTarget(String)
    case unavailableTarget(String)

    var description: String {
        switch self {
        case .permissionRequired:
            return "Screen Recording permission is required. Enable it in System Settings and relaunch the app."
        case .invalidTarget(let targetID):
            return "Invalid target id: \(targetID)"
        case .unavailableTarget(let targetID):
            return "Selected target is no longer available: \(targetID)"
        }
    }
}

struct ResolvedTarget {
    let id: String
    let application: SCRunningApplication
    let display: SCDisplay
}

struct TargetDescriptor {
    let id: String
    let name: String
    let kind: String
    let iconHint: String?
    let metadata: [String: Any]

    var jsonObject: [String: Any] {
        [
            "id": id,
            "name": name,
            "kind": kind,
            "icon_hint": iconHint as Any,
            "metadata": metadata,
        ]
    }
}

@available(macOS 14.0, *)
enum ShareableContentCatalog {
    static func statusObject() -> [String: Any] {
        if CGPreflightScreenCaptureAccess() {
            return [
                "provider": systemAudioProviderID,
                "state": "available",
                "message": "Ready to capture system audio.",
            ]
        }

        return [
            "provider": systemAudioProviderID,
            "state": "permission_required",
            "message": "Screen Recording permission is required before system audio capture can start.",
        ]
    }

    static func listTargetObjects() async throws -> [[String: Any]] {
        guard CGPreflightScreenCaptureAccess() else {
            return []
        }

        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        return buildTargets(from: content).map(\.jsonObject)
    }

    static func resolveTarget(id: String) async throws -> ResolvedTarget {
        guard CGPreflightScreenCaptureAccess() else {
            throw ShareableContentCatalogError.permissionRequired
        }

        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        guard let pid = parseTargetID(id) else {
            throw ShareableContentCatalogError.invalidTarget(id)
        }

        guard let application = content.applications.first(where: { Int($0.processID) == pid }) else {
            throw ShareableContentCatalogError.unavailableTarget(id)
        }

        let windows = visibleWindows(for: application, in: content)
        guard !windows.isEmpty else {
            throw ShareableContentCatalogError.unavailableTarget(id)
        }

        guard let display = preferredDisplay(for: windows, in: content.displays) ?? content.displays.first else {
            throw ShareableContentCatalogError.unavailableTarget(id)
        }

        return ResolvedTarget(id: id, application: application, display: display)
    }

    private static func buildTargets(from content: SCShareableContent) -> [TargetDescriptor] {
        let sortedApplications = content.applications.sorted {
            $0.applicationName.localizedCaseInsensitiveCompare($1.applicationName) == .orderedAscending
        }

        return sortedApplications.compactMap { application in
            let windows = visibleWindows(for: application, in: content)
            guard !windows.isEmpty else {
                return nil
            }

            return TargetDescriptor(
                id: "\(systemAudioProviderID):\(application.processID)",
                name: application.applicationName,
                kind: "application",
                iconHint: nil,
                metadata: [
                    "pid": Int(application.processID),
                    "bundle_id": application.bundleIdentifier,
                ]
            )
        }
    }

    private static func visibleWindows(
        for application: SCRunningApplication,
        in content: SCShareableContent
    ) -> [SCWindow] {
        content.windows.filter {
            $0.isOnScreen && $0.owningApplication?.processID == application.processID
        }
    }

    private static func preferredDisplay(
        for windows: [SCWindow],
        in displays: [SCDisplay]
    ) -> SCDisplay? {
        displays.max { lhs, rhs in
            overlapArea(for: windows, on: lhs) < overlapArea(for: windows, on: rhs)
        }
    }

    private static func overlapArea(for windows: [SCWindow], on display: SCDisplay) -> CGFloat {
        windows.reduce(0) { partialResult, window in
            partialResult + window.frame.intersection(display.frame).area
        }
    }

    private static func parseTargetID(_ targetID: String) -> Int? {
        let parts = targetID.split(separator: ":", omittingEmptySubsequences: false)
        guard parts.count == 2, parts[0] == Substring(systemAudioProviderID) else {
            return nil
        }

        return Int(parts[1])
    }
}

private extension CGRect {
    var area: CGFloat {
        guard !isNull, !isEmpty else {
            return 0
        }

        return width * height
    }
}
