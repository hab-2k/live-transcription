import CoreGraphics
import Foundation
import ScreenCaptureKit

let systemAudioProviderID = "screen_capture_kit"
let entireSystemTargetID = "\(systemAudioProviderID):system"

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
    let filter: SCContentFilter
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

    static func requestPermissionObject() -> [String: Any] {
        let requestGranted = CGRequestScreenCaptureAccess()
        if CGPreflightScreenCaptureAccess() {
            return statusObject()
        }

        if requestGranted {
            return [
                "provider": systemAudioProviderID,
                "state": "permission_required",
                "message": "Screen Recording permission was granted. Quit and reopen the app if capture is still unavailable.",
            ]
        }

        return statusObject()
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
        guard let selection = parseTargetID(id) else {
            throw ShareableContentCatalogError.invalidTarget(id)
        }

        switch selection {
        case .system:
            guard let display = primaryDisplay(in: content.displays) else {
                throw ShareableContentCatalogError.unavailableTarget(id)
            }

            // Exclude nothing — an empty exclusion list captures audio
            // from all running applications (system-wide).
            return ResolvedTarget(
                id: id,
                filter: SCContentFilter(
                    display: display,
                    excludingApplications: [],
                    exceptingWindows: []
                )
            )
        case .application(let pid):
            guard let application = content.applications.first(where: { Int($0.processID) == pid }) else {
                throw ShareableContentCatalogError.unavailableTarget(id)
            }

            // Include only the target app; all other apps' audio is excluded.
            // The display is required by the API but we configure the stream
            // to not capture any video pixels.
            return ResolvedTarget(
                id: id,
                filter: SCContentFilter(
                    display: content.displays.first(where: { $0.displayID == CGMainDisplayID() }) ?? content.displays.first!,
                    including: [application],
                    exceptingWindows: []
                )
            )
        }
    }

    private static func buildTargets(from content: SCShareableContent) -> [TargetDescriptor] {
        var targets: [TargetDescriptor] = []
        targets.append(
            TargetDescriptor(
                id: entireSystemTargetID,
                name: "Entire system audio",
                kind: "system",
                iconHint: nil,
                metadata: [:]
            )
        )

        let sortedApplications = content.applications.sorted {
            $0.applicationName.localizedCaseInsensitiveCompare($1.applicationName) == .orderedAscending
        }

        // Audio-only: list all running apps regardless of window visibility.
        let appTargets: [TargetDescriptor] = sortedApplications.compactMap { application -> TargetDescriptor? in
            TargetDescriptor(
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

        targets.append(contentsOf: appTargets)
        return targets
    }

    private static func primaryDisplay(in displays: [SCDisplay]) -> SCDisplay? {
        displays.first(where: { $0.displayID == CGMainDisplayID() }) ?? displays.first
    }

    private static func parseTargetID(_ targetID: String) -> TargetSelection? {
        let parts = targetID.split(separator: ":", omittingEmptySubsequences: false)
        guard parts.count == 2, parts[0] == Substring(systemAudioProviderID) else {
            return nil
        }

        if parts[1] == "system" {
            return .system
        }

        guard let pid = Int(parts[1]) else {
            return nil
        }

        return .application(pid: pid)
    }
}

private enum TargetSelection {
    case system
    case application(pid: Int)
}
