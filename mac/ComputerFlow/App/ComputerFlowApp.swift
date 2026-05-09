import SwiftUI
import AppKit

@main
struct ComputerFlowApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var appState = AppState.shared

    var menuBarIcon: String {
        switch appState.status {
        case .ready:     return "record.circle"
        case .recording: return "record.circle.fill"
        case .compiling: return "cpu"
        case .running:   return "play.circle.fill"
        }
    }

    var menuBarLabel: String {
        switch appState.status {
        case .ready:     return "ComputerFlow"
        case .recording: return "● REC"
        case .compiling: return "Compiling…"
        case .running:   return "▶ Running"
        }
    }

    var body: some Scene {
        MenuBarExtra {
            MenuBarView()
                .environmentObject(AppState.shared)
                .environmentObject(WorkflowStore.shared)
        } label: {
            MenuBarIconLabel(status: appState.status)
        }
        .menuBarExtraStyle(.window)
    }
}

// MARK: - MenuBarIconLabel
struct MenuBarIconLabel: View {
    let status: AppStatus

    var body: some View {
        HStack(spacing: 4) {
            Image(nsImage: appIconImage())
                .resizable()
                .interpolation(.high)
                .frame(width: 18, height: 18)
            if status != .ready {
                Text(badge)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(badgeColor)
            }
        }
    }

    var badge: String {
        switch status {
        case .ready:     return ""
        case .recording: return "REC"
        case .compiling: return "…"
        case .running:   return "▶"
        }
    }

    var badgeColor: Color {
        switch status {
        case .ready:     return .primary
        case .recording: return .red
        case .compiling: return .orange
        case .running:   return .blue
        }
    }

    /// Loads the actual app icon (works in SwiftPM bundles where Asset Catalog may not be compiled).
    func appIconImage() -> NSImage {
        let img = NSWorkspace.shared.icon(forFile: Bundle.main.bundlePath)
        img.size = NSSize(width: 18, height: 18)
        return img
    }
}
