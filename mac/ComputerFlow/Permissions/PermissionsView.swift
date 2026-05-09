import SwiftUI
import AppKit

// MARK: - PermissionsView
struct PermissionsView: View {
    @State private var screenGranted = false
    @State private var accessibilityGranted = false

    var allGranted: Bool { screenGranted && accessibilityGranted }

    var body: some View {
        VStack(spacing: 0) {

            // ── Traffic-light spacer (titlebar is transparent) ───
            HStack {
                Spacer()
            }
            .frame(height: 28)

            // ── Header ───────────────────────────────────────────
            VStack(spacing: 10) {
                Image(systemName: "shield.lefthalf.filled")
                    .font(.system(size: 40, weight: .medium))
                    .foregroundStyle(Theme.blue)
                    .padding(.top, 16)

                Text("Permissions Required")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(Theme.t1)

                Text("ComputerFlow needs access to record your screen\nand monitor keyboard/mouse events.")
                    .font(.system(size: 13))
                    .foregroundColor(Theme.t2)
                    .multilineTextAlignment(.center)
                    .lineSpacing(2)
            }
            .padding(.horizontal, 28)
            .padding(.bottom, 24)

            // ── Permission rows ──────────────────────────────────
            VStack(spacing: 8) {
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
            .padding(.horizontal, 20)
            .padding(.bottom, 20)

            // ── CTA button ───────────────────────────────────────
            Button(action: continueApp) {
                Text(allGranted ? "Continue to ComputerFlow →" : "Open System Settings")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .frame(height: 44)
                    .background(allGranted ? Theme.grn : Theme.blue)
                    .cornerRadius(10)
            }
            .buttonStyle(PlainButtonStyle())
            .padding(.horizontal, 20)
            .padding(.bottom, 24)
        }
        .frame(width: 480)
        .background(Theme.winBg)
        .onAppear {
            refreshStatus()
            // Poll every second — auto-close as soon as both permissions are granted
            Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { t in
                refreshStatus()
                if screenGranted && accessibilityGranted {
                    t.invalidate()
                    Task { @MainActor in continueApp() }
                }
            }
        }
    }

    // MARK: - Row
    func permissionRow(
        icon: String,
        title: String,
        subtitle: String,
        granted: Bool,
        action: @escaping () -> Void
    ) -> some View {
        HStack(spacing: 14) {
            Image(systemName: icon)
                .font(.system(size: 22))
                .foregroundColor(granted ? Theme.grn : Theme.t2)
                .frame(width: 36)

            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 13.5, weight: .semibold))
                    .foregroundColor(Theme.t1)
                Text(subtitle)
                    .font(.system(size: 12))
                    .foregroundColor(Theme.t3)
                    .lineLimit(1)
            }

            Spacer()

            if granted {
                HStack(spacing: 5) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 14))
                        .foregroundColor(Theme.grn)
                    Text("Granted")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(Theme.grn)
                }
            } else {
                Button(action: action) {
                    Text("Grant")
                        .font(.system(size: 12.5, weight: .semibold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 6)
                        .background(Theme.blue)
                        .cornerRadius(7)
                }
                .buttonStyle(PlainButtonStyle())
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(Theme.surf)
        .cornerRadius(10)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Theme.bdiv, lineWidth: 1)
        )
    }

    // MARK: - Actions
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
            NSApp.windows.forEach { w in
                if w.title.contains("Permissions") { w.close() }
            }
        } else {
            openSystemPreferences(anchor: "Privacy")
        }
    }
}
