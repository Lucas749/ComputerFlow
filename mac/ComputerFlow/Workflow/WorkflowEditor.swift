import SwiftUI
import AppKit

// MARK: - WorkflowEditorWindowController
class WorkflowEditorWindowController {
    private var window: NSWindow?
    let workflow: WorkflowModel

    init(workflow: WorkflowModel) {
        self.workflow = workflow
    }

    func show() {
        let view = WorkflowEditorView(workflow: workflow)
        let hosting = NSHostingView(rootView: view)

        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 830, height: 510),
            styleMask: [.titled, .closable, .miniaturizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = workflow.name
        window.titlebarAppearsTransparent = true
        window.backgroundColor = NSColor(Theme.winBg)
        window.contentView = hosting
        window.center()
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

// MARK: - WorkflowEditorView (Screen 6)
struct WorkflowEditorView: View {
    @State var workflow: WorkflowModel
    @State private var selectedStepId: String?
    @State private var amendValue: String = ""
    @State private var savedFlash = false
    @State private var isSaving = false

    var selectedStep: WorkflowStep? {
        workflow.steps.first { $0.id == selectedStepId }
    }

    var approvedCount: Int {
        workflow.steps.filter { $0.approved }.count
    }

    var body: some View {
        VStack(spacing: 0) {
            // Custom title bar
            editorTitleBar

            Divider().background(Theme.bdiv)

            // Body
            HStack(spacing: 0) {
                // Left rail
                leftRail

                Divider().background(Theme.bdiv)

                // Right pane
                if let step = selectedStep {
                    rightPane(step: step)
                } else {
                    emptyState
                }
            }
            .frame(maxHeight: .infinity)

            Divider().background(Theme.bdiv)

            // Footer
            editorFooter
        }
        .background(Theme.winBg)
        .onAppear {
            if let first = workflow.steps.first {
                selectedStepId = first.id
            }
        }
    }

    // MARK: - Title Bar
    var editorTitleBar: some View {
        HStack {
            Text(workflow.name)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Theme.t1)
                .frame(maxWidth: .infinity, alignment: .center)

            Button("Export") {
                exportWorkflow()
            }
            .font(.system(size: 12))
            .foregroundColor(Theme.t2)
            .buttonStyle(PlainButtonStyle())
            .padding(.trailing, 14)
        }
        .padding(.vertical, 12)
        .background(Theme.winBg)
    }

    // MARK: - Left Rail
    var leftRail: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Steps")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(Theme.t3)
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.top, 12)
            .padding(.bottom, 6)

            ScrollView {
                VStack(spacing: 3) {
                    ForEach(workflow.steps) { step in
                        StepRowWithThumbnail(
                            step: step,
                            isSelected: selectedStepId == step.id
                        ) {
                            selectedStepId = step.id
                            if let sv = step.value?.raw {
                                amendValue = sv
                            } else {
                                amendValue = ""
                            }
                        }
                    }
                }
                .padding(.horizontal, 8)
                .padding(.bottom, 8)
            }
        }
        .frame(width: 202)
        .background(Theme.surf.opacity(0.3))
    }

    // MARK: - Right Pane
    func rightPane(step: WorkflowStep) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            // Step header
            HStack(spacing: 8) {
                ZStack {
                    Circle()
                        .fill(Theme.surf)
                        .overlay(Circle().stroke(Theme.bdiv, lineWidth: 1))
                        .frame(width: 26, height: 26)
                    Text("\(step.n)")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(Theme.t2)
                }
                Text(step.actionLabel)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(Theme.t1)

                if let val = step.value {
                    Text(val.displayString)
                        .font(Theme.mono(12))
                        .foregroundColor(val.isVariable ? Theme.blue : Theme.t2)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .background(val.isVariable ? Theme.blue.opacity(0.12) : Theme.surf)
                        .cornerRadius(5)
                }

                Spacer()

                if step.needsReview {
                    HStack(spacing: 4) {
                        Circle().fill(Theme.amb).frame(width: 6, height: 6)
                        Text("Needs review")
                            .font(.system(size: 11))
                            .foregroundColor(Theme.amb)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Theme.amb.opacity(0.1))
                    .cornerRadius(5)
                }
            }
            .padding(.horizontal, 20)
            .padding(.top, 18)
            .padding(.bottom, 14)

            // Screenshot
            ScreenshotPanel(step: step)
                .frame(height: 240)
                .padding(.horizontal, 20)
                .padding(.bottom, 14)

            // Amendment panel
            amendPanel(step: step)
                .padding(.horizontal, 20)
                .padding(.bottom, 16)

            Spacer()
        }
    }

    // MARK: - Amendment Panel
    func amendPanel(step: WorkflowStep) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Amendment")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(Theme.t3)
                Spacer()
            }

            HStack(spacing: 10) {
                Text("Input Value")
                    .font(.system(size: 12))
                    .foregroundColor(Theme.t2)
                    .frame(width: 80, alignment: .leading)

                TextField("Enter value…", text: $amendValue)
                    .textFieldStyle(.plain)
                    .font(Theme.mono(12))
                    .foregroundColor(Theme.t1)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .background(Theme.surf)
                    .cornerRadius(6)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(Theme.bdiv, lineWidth: 1))

                // Save button
                Button(action: { saveAmendment(step: step) }) {
                    HStack(spacing: 4) {
                        if isSaving {
                            ProgressView().scaleEffect(0.6).tint(.white)
                        } else if savedFlash {
                            Image(systemName: "checkmark")
                        } else {
                            Image(systemName: "arrow.up.circle")
                        }
                        Text(savedFlash ? "Saved" : "Save")
                    }
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 7)
                    .background(savedFlash ? Theme.grn : Theme.blue)
                    .cornerRadius(6)
                }
                .buttonStyle(PlainButtonStyle())
                .disabled(isSaving)
            }
        }
        .padding(14)
        .background(Theme.surf.opacity(0.5))
        .overlay(RoundedRectangle(cornerRadius: 9).stroke(Theme.bdiv, lineWidth: 1))
        .cornerRadius(9)
    }

    // MARK: - Empty State
    var emptyState: some View {
        VStack {
            Spacer()
            Image(systemName: "cursorarrow.click.2")
                .font(.system(size: 32))
                .foregroundColor(Theme.t3)
            Text("Select a step to review")
                .font(.system(size: 13))
                .foregroundColor(Theme.t3)
                .padding(.top, 8)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Footer
    var editorFooter: some View {
        HStack {
            Button("Remove Step") {
                if let id = selectedStepId {
                    workflow.steps.removeAll { $0.id == id }
                    selectedStepId = workflow.steps.first?.id
                    saveWorkflow()
                }
            }
            .font(.system(size: 12))
            .foregroundColor(Theme.red)
            .buttonStyle(PlainButtonStyle())

            Spacer()

            Text("\(approvedCount) of \(workflow.steps.count) approved")
                .font(.system(size: 12))
                .foregroundColor(Theme.t2)

            Button("Approve All →") {
                approveAll()
            }
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(.white)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Theme.blue)
            .cornerRadius(6)
            .buttonStyle(PlainButtonStyle())
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Theme.winBg)
    }

    // MARK: - Actions
    func saveAmendment(step: WorkflowStep) {
        guard let idx = workflow.steps.firstIndex(where: { $0.id == step.id }) else { return }
        workflow.steps[idx].value = StepValue(raw: amendValue, variableRef: nil)
        workflow.steps[idx].approved = true
        workflow.steps[idx].needsReview = false
        isSaving = true
        Task {
            try? await BackendClient.shared.updateWorkflow(workflow)
            await MainActor.run {
                isSaving = false
                savedFlash = true
            }
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            await MainActor.run { savedFlash = false }
        }
    }

    func approveAll() {
        for i in workflow.steps.indices {
            workflow.steps[i].approved = true
            workflow.steps[i].needsReview = false
        }
        saveWorkflow()
    }

    func saveWorkflow() {
        WorkflowStore.shared.addOrUpdate(workflow)
        Task { try? await BackendClient.shared.updateWorkflow(workflow) }
    }

    func exportWorkflow() {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .prettyPrinted
        encoder.dateEncodingStrategy = .iso8601
        guard let data = try? encoder.encode(workflow) else { return }

        let panel = NSSavePanel()
        panel.allowedContentTypes = [.json]
        panel.nameFieldStringValue = "\(workflow.name).json"
        if panel.runModal() == .OK, let url = panel.url {
            try? data.write(to: url)
        }
    }
}
