import SwiftUI

// MARK: - MenuBarView (Screen 1)
struct MenuBarView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var store: WorkflowStore

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("ComputerFlow")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Theme.t1)
                Spacer()
                statusBadge
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 11)

            Divider().background(Theme.bdiv)

            // Start Recording Button
            recordingButton
                .padding(.horizontal, 10)
                .padding(.vertical, 8)

            Divider().background(Theme.bdiv)

            // Recent Workflows
            recentSection

            Divider().background(Theme.bdiv)

            // Footer
            HStack {
                Button("Settings") { openSettings() }
                    .buttonStyle(MenuBarTextButtonStyle())
                Spacer()
                Button("Quit") { NSApplication.shared.terminate(nil) }
                    .buttonStyle(MenuBarTextButtonStyle())
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
        }
        .frame(width: 292)
        .background(Theme.winBg)
        .cornerRadius(14)
        .modifier(WindowShadowModifier())
    }

    // MARK: - Status Badge
    @ViewBuilder
    var statusBadge: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(statusColor)
                .frame(width: 7, height: 7)
                .modifier(StatusDotModifier(status: appState.status))
            Text(statusText)
                .font(.system(size: 11))
                .foregroundColor(Theme.t2)
        }
    }

    var statusColor: Color {
        switch appState.status {
        case .ready:     return Theme.grn
        case .recording: return Theme.red
        case .compiling: return Theme.amb
        case .running:   return Theme.blue
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

    // MARK: - Recording Button
    var recordingButton: some View {
        Button(action: { appState.toggleRecording() }) {
            HStack(spacing: 9) {
                Circle()
                    .fill(Theme.red)
                    .frame(width: 8, height: 8)
                    .modifier(BlinkModifier(active: appState.status == .recording))
                Text(appState.status == .recording ? "Stop Recording" : "Start Recording")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(Theme.t1)
                Spacer()
                Text("⌘⇧R")
                    .font(Theme.mono(11))
                    .foregroundColor(Theme.t3)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .background(Theme.ctrl)
            .cornerRadius(8)
        }
        .buttonStyle(PlainButtonStyle())
    }

    // MARK: - Recent Section
    @ViewBuilder
    var recentSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Recent")
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(Theme.t3)
                .padding(.horizontal, 14)
                .padding(.top, 10)
                .padding(.bottom, 5)

            if store.recentWorkflows.isEmpty {
                Text("No workflows yet")
                    .font(.system(size: 12))
                    .foregroundColor(Theme.t3)
                    .padding(.horizontal, 14)
                    .padding(.bottom, 10)
            } else {
                ForEach(store.recentWorkflows.prefix(5)) { workflow in
                    RecentWorkflowRow(workflow: workflow)
                }
            }
        }
    }

    func openSettings() {
        // Open settings window (basic implementation)
        let url = URL(string: "x-apple.systempreferences:")!
        NSWorkspace.shared.open(url)
    }
}

// MARK: - RecentWorkflowRow
struct RecentWorkflowRow: View {
    let workflow: WorkflowModel
    @EnvironmentObject var appState: AppState
    @State private var isHovered = false

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "arrow.right.circle")
                .font(.system(size: 11))
                .foregroundColor(Theme.t3)

            VStack(alignment: .leading, spacing: 1) {
                Text(workflow.name)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(Theme.t1)
                    .lineLimit(1)
                Text(relativeDate(workflow.updatedAt))
                    .font(.system(size: 10))
                    .foregroundColor(Theme.t3)
            }

            Spacer()

            if isHovered {
                Button("Run") {
                    appState.startRun(workflowId: workflow.id)
                }
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(Theme.blue)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(Theme.ctrl)
                .cornerRadius(5)
                .buttonStyle(PlainButtonStyle())
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 6)
        .background(isHovered ? Theme.hov : Color.clear)
        .onHover { isHovered = $0 }
        .contentShape(Rectangle())
        .onTapGesture {
            appState.openEditor(workflow: workflow)
        }
    }

    func relativeDate(_ date: Date) -> String {
        let now = Date()
        let diff = now.timeIntervalSince(date)
        if diff < 3600 { return "\(Int(diff/60))m ago" }
        if diff < 86400 { return "\(Int(diff/3600))h ago" }
        if diff < 172800 { return "Yesterday" }
        return "\(Int(diff/86400))d ago"
    }
}

// MARK: - Status Dot Modifier (blink for recording)
struct StatusDotModifier: ViewModifier {
    let status: AppStatus
    @State private var opacity: Double = 1

    func body(content: Content) -> some View {
        content
            .opacity(status == .recording ? opacity : 1)
            .onAppear {
                if status == .recording {
                    withAnimation(.easeInOut(duration: 1.3).repeatForever()) {
                        opacity = 0.25
                    }
                }
            }
    }
}

// MARK: - Blink Modifier
struct BlinkModifier: ViewModifier {
    let active: Bool
    @State private var opacity: Double = 1

    func body(content: Content) -> some View {
        content
            .opacity(active ? opacity : 1)
            .onAppear { startBlink() }
            .onChange(of: active) { _, _ in startBlink() }
    }

    func startBlink() {
        guard active else { opacity = 1; return }
        withAnimation(.easeInOut(duration: 1.3).repeatForever(autoreverses: true)) {
            opacity = 0.25
        }
    }
}

// MARK: - MenuBarTextButtonStyle
struct MenuBarTextButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12))
            .foregroundColor(configuration.isPressed ? Theme.t1 : Theme.t2)
            .buttonStyle(PlainButtonStyle())
    }
}
