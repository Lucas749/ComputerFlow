import AppKit
import SwiftUI

class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Register global hotkey ⌘⇧R
        HotkeyManager.shared.onHotKeyPressed = {
            Task { @MainActor in
                AppState.shared.toggleRecording()
            }
        }
        HotkeyManager.shared.register()

        // Check permissions on launch
        Task { @MainActor in
            await checkPermissions()
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        HotkeyManager.shared.unregister()
    }

    @MainActor
    private func checkPermissions() async {
        let screenOK = CGPreflightScreenCaptureAccess()
        let accessOK = AXIsProcessTrusted()

        if !screenOK || !accessOK {
            showPermissionsWindow()
        } else {
            AppState.shared.permissionsGranted = true
        }
    }

    private func showPermissionsWindow() {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 420, height: 340),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        window.title = "ComputerFlow — Permissions Required"
        window.center()
        window.isReleasedWhenClosed = false
        window.contentView = NSHostingView(rootView: PermissionsView())
        window.makeKeyAndOrderFront(nil)
    }
}
