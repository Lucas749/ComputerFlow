import SwiftUI

// MARK: - MenuBarView (Screen 1)
struct MenuBarView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var store: WorkflowStore
    @State private var recHovered = false

    var body: some View {
        VStack(spacing: 0) {
            // ── Header ──────────────────────────────────────────
            HStack {
                Text("ComputerFlow")
                    .font(.system(size: 14, weight: .semibold))
                    .tracking(-0.3)
                    .foregroundColor(Theme.t1)
                Spacer()
                // Status badge
                HStack(spacing: 5) {
                    Circle()
                        .fill(statusColor)
                        .frame(width: 6, height: 6)
                        .shadow(color: statusGlow, radius: 3)
                        .modifier(StatusBlinkModifier(active: appState.status == .recording))
                    Text(statusText)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(statusColor)
                }
            }
            .padding(.horizontal, 15)
            .padding(.vertical, 13)
            .padding(.bottom, 1)

            Divider().opacity(0.07)

            // ── Record button ────────────────────────────────────
            VStack(spacing: 0) {
                Button(action: { appState.toggleRecording() }) {
                    HStack(spacing: 8) {
                        Circle()
                            .fill(Theme.red)
                            .frame(width: 7, height: 7)
                            .shadow(color: Theme.red.opacity(0.45), radius: 3)
                            .modifier(BlinkModifier(active: appState.status == .recording))
                        Text(appState.status == .recording ? "Stop Recording" : "Start Recording")
                            .font(.system(size: 13.5, weight: .medium))
                            .foregroundColor(Theme.t1)
                        Spacer()
                        Text("⌘⇧R")
                            .font(.system(size: 11).monospaced())
                            .foregroundColor(Theme.t3)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.white.opacity(0.07))
                            .cornerRadius(4)
                            .overlay(
                                RoundedRectangle(cornerRadius: 4)
                                    .stroke(Theme.bdiv, lineWidth: 1)
                            )
                    }
                    .padding(.horizontal, 12)
                    .frame(height: 34)
                    .background(recHovered ? Theme.ctrl : Theme.surf)
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Theme.bdiv, lineWidth: 1)
                    )
                }
                .buttonStyle(PlainButtonStyle())
                .onHover { recHovered = $0 }
            }
            .padding(.horizontal, 12)
            .padding(.top, 10)
            .padding(.bottom, 8)

            // ── Display selector ─────────────────────────────────
            DisplaySelectorView()
                .padding(.horizontal, 12)
                .padding(.bottom, 6)
                .opacity(appState.status == .recording || appState.status == .compiling ? 0.4 : 1)
                .disabled(appState.status == .recording || appState.status == .compiling)

            Divider().opacity(0.07)

            // ── Recent workflows ─────────────────────────────────
            recentSection

            // ── Footer ───────────────────────────────────────────
            Divider().opacity(0.07)

            HStack {
                footerButton("Settings") { openSettings() }
                Spacer()
                // Dark / light toggle
                Button(action: { appState.isDarkMode.toggle() }) {
                    Image(systemName: appState.isDarkMode ? "sun.min" : "moon")
                        .font(.system(size: 12))
                        .foregroundColor(Theme.t3)
                        .frame(width: 24, height: 24)
                        .background(Theme.ctrl)
                        .cornerRadius(6)
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(Theme.bdiv, lineWidth: 1))
                }
                .buttonStyle(PlainButtonStyle())
                Spacer()
                footerButton("Quit") { NSApplication.shared.terminate(nil) }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
        }
        .frame(width: 292)
        .background(Theme.winBg)
    }

    // MARK: - Status
    var statusColor: Color {
        switch appState.status {
        case .ready:     return Theme.grn
        case .recording: return Theme.red
        case .compiling: return Theme.amb
        case .running:   return Theme.blue
        }
    }

    var statusGlow: Color {
        switch appState.status {
        case .ready:     return Theme.grn.opacity(0.5)
        case .recording: return Theme.red.opacity(0.5)
        case .compiling: return Theme.amb.opacity(0.5)
        case .running:   return Theme.blue.opacity(0.5)
        }
    }

    var statusText: String {
        switch appState.status {
        case .ready:     return "Ready"
        case .recording: return "Recording"
        case .compiling: return "Compiling"
        case .running:   return "Running"
        }
    }

    // MARK: - Recent Section
    @ViewBuilder
    var recentSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Recent")
                .font(.system(size: 12.5))
                .foregroundColor(Theme.t3)
                .padding(.horizontal, 12)
                .padding(.bottom, 5)
                .padding(.top, 2)

            if store.recentWorkflows.isEmpty {
                Text("No workflows yet")
                    .font(.system(size: 12.5))
                    .foregroundColor(Theme.t3)
                    .padding(.horizontal, 20)
                    .padding(.bottom, 10)
            } else {
                ForEach(store.recentWorkflows.prefix(5)) { workflow in
                    RecentWorkflowRow(workflow: workflow)
                }
            }
        }
        .padding(.bottom, 2)
    }

    // MARK: - Footer button
    func footerButton(_ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 12.5))
                .foregroundColor(Theme.t3)
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
        }
        .buttonStyle(PlainButtonStyle())
        .contentShape(Rectangle())
    }

    func openSettings() {
        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:")!)
    }
}

// MARK: - RecentWorkflowRow
struct RecentWorkflowRow: View {
    let workflow: WorkflowModel
    @EnvironmentObject var appState: AppState
    @State private var isHovered = false

    var body: some View {
        HStack(spacing: 9) {
            // Arrow icon tile — matches design
            ZStack {
                RoundedRectangle(cornerRadius: 7)
                    .fill(Theme.surf)
                    .overlay(
                        RoundedRectangle(cornerRadius: 7)
                            .stroke(Theme.bdiv, lineWidth: 1)
                    )
                Text("→")
                    .font(.system(size: 12))
                    .foregroundColor(Theme.t2)
            }
            .frame(width: 28, height: 28)

            VStack(alignment: .leading, spacing: 1) {
                Text(workflow.name)
                    .font(.system(size: 13))
                    .foregroundColor(Theme.t1)
                    .lineLimit(1)
                Text(relativeDate(workflow.updatedAt))
                    .font(.system(size: 11.5))
                    .foregroundColor(Theme.t3)
            }

            Spacer()

            if isHovered {
                Button("Run") {
                    appState.startRun(workflowId: workflow.id)
                }
                .font(.system(size: 11.5))
                .foregroundColor(Theme.t2)
                .padding(.horizontal, 10)
                .padding(.vertical, 3)
                .background(Theme.ctrl)
                .cornerRadius(6)
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Theme.bdiv, lineWidth: 1)
                )
                .buttonStyle(PlainButtonStyle())
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 7)
        .background(isHovered ? Theme.surf : Color.clear)
        .cornerRadius(8)
        .padding(.horizontal, 12)
        .onHover { isHovered = $0 }
        .contentShape(Rectangle())
        .onTapGesture { appState.openEditor(workflow: workflow) }
    }

    func relativeDate(_ date: Date) -> String {
        let diff = Date().timeIntervalSince(date)
        if diff < 3600   { return "\(Int(diff / 60))m ago" }
        if diff < 86400  { return "\(Int(diff / 3600))h ago" }
        if diff < 172800 { return "Yesterday" }
        return "\(Int(diff / 86400))d ago"
    }
}

// MARK: - Blink / status dot modifiers
struct StatusBlinkModifier: ViewModifier {
    let active: Bool
    @State private var opacity: Double = 1

    func body(content: Content) -> some View {
        content
            .opacity(active ? opacity : 1)
            .onAppear { animate() }
            .onChange(of: active) { _, _ in animate() }
    }

    func animate() {
        guard active else { opacity = 1; return }
        withAnimation(.easeInOut(duration: 1.3).repeatForever(autoreverses: true)) {
            opacity = 0.25
        }
    }
}

struct BlinkModifier: ViewModifier {
    let active: Bool
    @State private var opacity: Double = 1

    func body(content: Content) -> some View {
        content
            .opacity(active ? opacity : 1)
            .onAppear { animate() }
            .onChange(of: active) { _, _ in animate() }
    }

    func animate() {
        guard active else { opacity = 1; return }
        withAnimation(.easeInOut(duration: 1.3).repeatForever(autoreverses: true)) {
            opacity = 0.25
        }
    }
}

