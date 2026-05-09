import SwiftUI
import AppKit

// MARK: - WorkflowLibraryWindowController
class WorkflowLibraryWindowController {
    static let shared = WorkflowLibraryWindowController()
    private var window: NSWindow?

    func show() {
        if let w = window {
            NSApp.activate(ignoringOtherApps: true)
            w.makeKeyAndOrderFront(nil)
            return
        }
        let view = WorkflowLibraryView()
            .environmentObject(AppState.shared)
            .environmentObject(WorkflowStore.shared)
        let hosting = NSHostingView(rootView: view)

        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 760, height: 520),
            styleMask: [.titled, .closable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "Workflows"
        window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = true
        window.backgroundColor = NSColor(Theme.winBg)
        window.contentView = hosting
        window.center()
        window.isReleasedWhenClosed = false
        self.window = window

        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
    }
}

// MARK: - WorkflowLibraryView
struct WorkflowLibraryView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var store: WorkflowStore
    @State private var search: String = ""

    var filtered: [WorkflowModel] {
        let q = search.trimmingCharacters(in: .whitespaces).lowercased()
        if q.isEmpty { return store.recentWorkflows }
        return store.recentWorkflows.filter { $0.name.lowercased().contains(q) }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Title bar
            HStack(spacing: 10) {
                Text("All Workflows")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(Theme.t1)
                Spacer()
                HStack(spacing: 6) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 11))
                        .foregroundColor(Theme.t3)
                    TextField("Search", text: $search)
                        .textFieldStyle(.plain)
                        .font(.system(size: 12))
                        .foregroundColor(Theme.t1)
                        .frame(width: 180)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 5)
                .background(Theme.ctrl)
                .cornerRadius(6)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Theme.bdiv, lineWidth: 1))
            }
            .padding(.horizontal, 18)
            .padding(.top, 36)
            .padding(.bottom, 14)

            Divider().opacity(0.07)

            if filtered.isEmpty {
                VStack(spacing: 10) {
                    Spacer()
                    Image(systemName: "square.stack.3d.up")
                        .font(.system(size: 32))
                        .foregroundColor(Theme.t3)
                    Text(search.isEmpty ? "No workflows yet" : "No matches")
                        .font(.system(size: 13))
                        .foregroundColor(Theme.t3)
                    Spacer()
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVGrid(columns: [
                        GridItem(.adaptive(minimum: 220, maximum: 260), spacing: 12)
                    ], spacing: 12) {
                        ForEach(filtered) { wf in
                            WorkflowCard(workflow: wf)
                        }
                    }
                    .padding(18)
                }
            }
        }
        .background(Theme.winBg)
    }
}

// MARK: - WorkflowCard
struct WorkflowCard: View {
    let workflow: WorkflowModel
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var store: WorkflowStore
    @State private var hovered = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Thumbnail strip — uses first step's screenshot if available
            ZStack {
                LinearGradient(
                    colors: [Color(hex: "#1a1a2e"), Color(hex: "#0f3460")],
                    startPoint: .topLeading, endPoint: .bottomTrailing
                )
                Image(systemName: executorIcon)
                    .font(.system(size: 28))
                    .foregroundColor(.white.opacity(0.55))
            }
            .frame(height: 90)
            .clipShape(UnevenRoundedRectangle(topLeadingRadius: 8, topTrailingRadius: 8))

            VStack(alignment: .leading, spacing: 4) {
                Text(workflow.name)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Theme.t1)
                    .lineLimit(1)

                HStack(spacing: 6) {
                    Text("\(workflow.steps.count) steps")
                        .font(.system(size: 11))
                        .foregroundColor(Theme.t3)
                    Text("•")
                        .font(.system(size: 11))
                        .foregroundColor(Theme.t3)
                    Text(relativeDate(workflow.updatedAt))
                        .font(.system(size: 11))
                        .foregroundColor(Theme.t3)
                }

                HStack(spacing: 6) {
                    Button(action: { appState.startRun(workflowId: workflow.id) }) {
                        Text("Run")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(.white)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(Theme.blue)
                            .cornerRadius(5)
                    }
                    .buttonStyle(PlainButtonStyle())

                    Button(action: {
                        let c = WorkflowConfirmationWindowController(workflow: workflow)
                        appState.confirmationWindowController = c
                        c.show()
                    }) {
                        Text("Edit")
                            .font(.system(size: 11))
                            .foregroundColor(Theme.t2)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(Theme.ctrl)
                            .cornerRadius(5)
                            .overlay(RoundedRectangle(cornerRadius: 5).stroke(Theme.bdiv, lineWidth: 1))
                    }
                    .buttonStyle(PlainButtonStyle())

                    Spacer()

                    Button(action: { store.remove(id: workflow.id) }) {
                        Image(systemName: "trash")
                            .font(.system(size: 10))
                            .foregroundColor(Theme.t3)
                            .padding(5)
                    }
                    .buttonStyle(PlainButtonStyle())
                    .opacity(hovered ? 1 : 0.3)
                }
                .padding(.top, 4)
            }
            .padding(12)
        }
        .background(Theme.surf)
        .cornerRadius(8)
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.bdiv, lineWidth: 1))
        .shadow(color: hovered ? .black.opacity(0.25) : .clear, radius: 8, y: 2)
        .onHover { hovered = $0 }
    }

    var executorIcon: String {
        let kinds = Set(workflow.steps.compactMap { $0.executor?.kind })
        if kinds.contains("kernel") && kinds.count == 1 { return "globe" }
        if kinds.isEmpty || kinds.contains("computer_use") { return "desktopcomputer" }
        return "wand.and.stars"
    }

    func relativeDate(_ date: Date) -> String {
        let diff = Date().timeIntervalSince(date)
        if diff < 60     { return "just now" }
        if diff < 3600   { return "\(Int(diff / 60))m ago" }
        if diff < 86400  { return "\(Int(diff / 3600))h ago" }
        return "\(Int(diff / 86400))d ago"
    }
}
