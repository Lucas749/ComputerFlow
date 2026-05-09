import SwiftUI
import AppKit
import UniformTypeIdentifiers

// MARK: - WorkflowConfirmationWindowController
class WorkflowConfirmationWindowController {
    private var window: NSWindow?
    let workflow: WorkflowModel

    init(workflow: WorkflowModel) {
        self.workflow = workflow
    }

    func show() {
        let view = WorkflowConfirmationView(workflow: workflow)
        let hosting = NSHostingView(rootView: view)

        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 618, height: 520),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        window.backgroundColor = .clear
        window.isOpaque = false
        window.hasShadow = true
        window.contentView = hosting
        window.center()
        window.level = .normal
        window.isReleasedWhenClosed = false
        window.orderFront(nil)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        self.window = window
    }

    func close() {
        window?.close()
        window = nil
    }
}

// MARK: - WorkflowConfirmationView (Screen 4)
struct WorkflowConfirmationView: View {
    @State var workflow: WorkflowModel
    @State private var backgroundRun = false
    @State private var droppedInputs: URL? = nil
    @State private var isDragOver = false
    @State private var deployFlash = false
    @State private var isDeploying = false
    @State private var deploySuccess = false

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 14)
                .fill(Theme.winBg)

            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)

            VStack(spacing: 0) {
                // Title Bar
                titleBar

                Divider().background(Theme.bdiv)

                // Body
                HStack(spacing: 0) {
                    // Left pane — steps
                    leftPane

                    Divider().background(Theme.bdiv)

                    // Right pane — execution
                    rightPane
                }
            }
        }
        .frame(width: 618)
        .fixedSize(horizontal: false, vertical: true)
        .shadow(color: .black.opacity(0.6), radius: 28, x: 0, y: 20)
    }

    // MARK: - Title Bar
    var titleBar: some View {
        HStack(spacing: 8) {
            // Traffic lights
            HStack(spacing: 5) {
                ForEach([Theme.red, Theme.amb, Theme.grn], id: \.self) { color in
                    Circle().fill(color).frame(width: 11, height: 11)
                }
            }
            .padding(.leading, 14)

            Spacer()

            // Editable title
            TextField("Workflow name", text: $workflow.name)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Theme.t1)
                .multilineTextAlignment(.center)
                .textFieldStyle(.plain)
                .frame(maxWidth: 260)
                .onChange(of: workflow.name) { _, _ in
                    Task { try? await BackendClient.shared.updateWorkflow(workflow) }
                }

            Spacer()
            // Spacer to balance traffic lights
            Color.clear.frame(width: 14 + 33)
        }
        .padding(.vertical, 12)
        .background(Theme.winBg)
    }

    // MARK: - Left Pane
    var leftPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Extracted Steps")
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(Theme.t3)
                .padding(.horizontal, 16)
                .padding(.top, 14)
                .padding(.bottom, 8)

            ScrollView {
                VStack(spacing: 2) {
                    ForEach(workflow.steps) { step in
                        StepRow(step: step)
                    }
                }
            }
            .frame(maxHeight: 360)

            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Right Pane
    var rightPane: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Execution")
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(Theme.t3)
                .padding(.top, 14)

            // Background Run toggle
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Background Run")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(Theme.t1)
                    Text("KERNEL headless")
                        .font(Theme.mono(10))
                        .foregroundColor(Theme.t3)
                }
                Spacer()
                CFToggle(isOn: $backgroundRun)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(Theme.ctrl)
            .cornerRadius(8)

            // Drop Zone
            dropZone

            Spacer()

            // Deploy button
            deployButton

            // Open in Editor
            Button(action: openEditor) {
                HStack {
                    Text("Open in Editor")
                    Image(systemName: "arrow.right")
                }
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(Theme.t2)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 9)
                .background(Theme.ctrl)
                .cornerRadius(8)
            }
            .buttonStyle(PlainButtonStyle())
        }
        .padding(.horizontal, 14)
        .padding(.bottom, 16)
        .frame(width: 196)
    }

    // MARK: - Drop Zone
    var dropZone: some View {
        VStack(spacing: 6) {
            Image(systemName: "arrow.down.circle")
                .font(.system(size: 20))
                .foregroundColor(isDragOver ? Theme.blue : Theme.t3)
            Text("Drop inputs.json")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(isDragOver ? Theme.blue : Theme.t2)
            Text("to loop this task")
                .font(.system(size: 11))
                .foregroundColor(Theme.t3)

            if let url = droppedInputs {
                Text("✓ \(url.lastPathComponent)")
                    .font(Theme.mono(10))
                    .foregroundColor(Theme.grn)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 18)
        .background(Theme.surf.opacity(0.5))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isDragOver ? Theme.blue : Theme.bdiv, style: StrokeStyle(lineWidth: 1, dash: [5]))
        )
        .cornerRadius(8)
        .onDrop(of: [UTType.json, UTType.fileURL], isTargeted: $isDragOver) { providers in
            handleDrop(providers)
        }
    }

    // MARK: - Deploy Button
    var deployButton: some View {
        Button(action: deploy) {
            HStack(spacing: 6) {
                if isDeploying {
                    ProgressView().scaleEffect(0.7).tint(.white)
                } else if deploySuccess {
                    Image(systemName: "checkmark")
                } else {
                    Image(systemName: "arrow.up.circle.fill")
                }
                Text(deploySuccess ? "Deployed!" : "Deploy Agent")
                    .font(.system(size: 13, weight: .semibold))
            }
            .foregroundColor(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(deploySuccess ? Theme.grn : Theme.ctrl)
                    .shadow(color: deploySuccess ? Theme.grn.opacity(0.4) : .clear, radius: 8)
            )
        }
        .buttonStyle(PlainButtonStyle())
        .disabled(isDeploying)
    }

    // MARK: - Actions
    func deploy() {
        isDeploying = true
        var inputs: [[String: String]]? = nil

        if let url = droppedInputs,
           let data = try? Data(contentsOf: url),
           let parsed = try? JSONDecoder().decode([[String: String]].self, from: data) {
            inputs = parsed
        }

        let capturedInputs = inputs
        Task {
            await MainActor.run {
                AppState.shared.startRun(workflowId: workflow.id, inputs: capturedInputs)
                isDeploying = false
                deploySuccess = true
            }
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            await MainActor.run {
                deploySuccess = false
                AppState.shared.confirmationWindowController?.close()
                AppState.shared.confirmationWindowController = nil
            }
        }
    }

    @MainActor func openEditor() {
        AppState.shared.openEditor(workflow: workflow)
    }

    func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first else { return false }
        provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
            if let data = item as? Data,
               let url = URL(dataRepresentation: data, relativeTo: nil) {
                DispatchQueue.main.async { droppedInputs = url }
            }
        }
        return true
    }
}

// MARK: - CFToggle
struct CFToggle: View {
    @Binding var isOn: Bool

    var body: some View {
        Button(action: { withAnimation(.spring(response: 0.25)) { isOn.toggle() } }) {
            ZStack(alignment: isOn ? .trailing : .leading) {
                Capsule()
                    .fill(isOn ? Theme.grn : Theme.ctrl)
                    .shadow(color: isOn ? Theme.grn.opacity(0.35) : .clear, radius: 5)
                    .frame(width: 38, height: 22)

                Circle()
                    .fill(Color.white)
                    .frame(width: 16, height: 16)
                    .padding(3)
                    .shadow(radius: 2)
            }
        }
        .buttonStyle(PlainButtonStyle())
    }
}
