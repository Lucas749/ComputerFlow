import AppKit
import SwiftUI

class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Apply saved appearance (default dark)
        NSApp.appearance = NSAppearance(named: AppState.shared.isDarkMode ? .darkAqua : .aqua)

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
            contentRect: NSRect(x: 0, y: 0, width: 480, height: 420),
            styleMask: [.titled, .closable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        // Hide the native title bar — content extends under it
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.isMovableByWindowBackground = true
        window.backgroundColor = NSColor(red: 37/255, green: 37/255, blue: 39/255, alpha: 1)
        window.title = "ComputerFlow — Permissions Required"
        window.center()
        window.isReleasedWhenClosed = false
        window.contentView = NSHostingView(rootView: PermissionsView())
        window.makeKeyAndOrderFront(nil)
    }
}
