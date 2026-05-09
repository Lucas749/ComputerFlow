import SwiftUI
import AppKit

@main
struct ComputerFlowApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        MenuBarExtra("CF", systemImage: "record.circle") {
            MenuBarView()
                .environmentObject(AppState.shared)
                .environmentObject(WorkflowStore.shared)
        }
        .menuBarExtraStyle(.window)
    }
}
