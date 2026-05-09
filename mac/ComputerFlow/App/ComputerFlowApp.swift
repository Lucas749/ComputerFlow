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
        MenuBarExtra(menuBarLabel, systemImage: menuBarIcon) {
            MenuBarView()
                .environmentObject(AppState.shared)
                .environmentObject(WorkflowStore.shared)
        }
        .menuBarExtraStyle(.window)
    }
}
