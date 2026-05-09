import SwiftUI
import AppKit

// MARK: - PermissionsView
struct PermissionsView: View {
    @State private var screenGranted = false
    @State private var accessibilityGranted = false

    var allGranted: Bool { screenGranted && accessibilityGranted }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            VStack(spacing: 8) {
                Image(systemName: "shield.lefthalf.filled")
                    .font(.system(size: 36))
                    .foregroundColor(Theme.blue)
                    .padding(.top, 28)

                Text("Permissions Required")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(Theme.t1)

                Text("ComputerFlow needs access to record your screen\nand monitor keyboard/mouse events.")
                    .font(.system(size: 13))
                    .foregroundColor(Theme.t2)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)
            }
            .padding(.bottom, 24)

            // Permission rows
            VStack(spacing: 10) {
                permissionRow(
                    icon: "rectangle.dashed.badge.record",
                    title: "Screen Recording",
                    subtitle: "Required to capture your workflow",
                    granted: screenGranted,
                    action: requestScreen
                )

                permissionRow(
                    icon: "accessibility",
                    title: "Accessibility",
                    subtitle: "Required to monitor events during recording",
                    granted: accessibilityGranted,
                    action: requestAccessibility
                )
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 24)

            // Continue button
            Button(action: continueApp) {
                Text(allGranted ? "Continue to ComputerFlow" : "Open System Settings")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 11)
                    .background(allGranted ? Theme.grn : Theme.blue)
                    .cornerRadius(9)
            }
            .buttonStyle(PlainButtonStyle())
            .padding(.horizontal, 24)
            .padding(.bottom, 24)
        }
        .background(Theme.winBg)
        .onAppear { refreshStatus() }
    }

    func permissionRow(icon: String, title: String, subtitle: String, granted: Bool, action: @escaping () -> Void) -> some View {
        HStack(spacing: 14) {
            Image(systemName: icon)
                .font(.system(size: 20))
                .foregroundColor(granted ? Theme.grn : Theme.t2)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(Theme.t1)
                Text(subtitle)
                    .font(.system(size: 11))
                    .foregroundColor(Theme.t3)
            }

            Spacer()

            if granted {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(Theme.grn)
            } else {
                Button("Grant", action: action)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(Theme.blue)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(Theme.blue.opacity(0.15))
                    .cornerRadius(6)
                    .buttonStyle(PlainButtonStyle())
            }
        }
        .padding(14)
        .background(Theme.surf)
        .cornerRadius(9)
        .overlay(RoundedRectangle(cornerRadius: 9).stroke(Theme.bdiv, lineWidth: 1))
    }

    func requestScreen() {
        CGRequestScreenCaptureAccess()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { refreshStatus() }
        openSystemPreferences(anchor: "Privacy_ScreenCapture")
    }

    func requestAccessibility() {
        let options: [String: Any] = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true]
        AXIsProcessTrustedWithOptions(options as CFDictionary)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { refreshStatus() }
        openSystemPreferences(anchor: "Privacy_Accessibility")
    }

    func openSystemPreferences(anchor: String) {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?\(anchor)") {
            NSWorkspace.shared.open(url)
        }
    }

    func refreshStatus() {
        screenGranted = CGPreflightScreenCaptureAccess()
        accessibilityGranted = AXIsProcessTrusted()
    }

    @MainActor func continueApp() {
        if allGranted {
            AppState.shared.permissionsGranted = true
            // Close permissions window
            NSApp.windows.forEach { w in
                if w.title.contains("Permissions") { w.close() }
            }
        } else {
            openSystemPreferences(anchor: "Privacy")
        }
    }
}
