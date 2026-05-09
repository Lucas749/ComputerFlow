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
        let view = RecordingReviewView(workflow: workflow, store: WorkflowStore.shared)
        let hosting = NSHostingView(rootView: view)

        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 900, height: 580),
            styleMask: [.titled, .closable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = workflow.name
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.isMovableByWindowBackground = true
        window.backgroundColor = NSColor(Theme.winBg)
        window.contentView = hosting
        window.center()
        window.isReleasedWhenClosed = false
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        self.window = window
    }

    func close() {
        window?.close()
        window = nil
    }
}

// MARK: - RecordingReviewView
struct RecordingReviewView: View {
    @State var workflow: WorkflowModel
    let store: WorkflowStore
    @State private var selectedStepId: String?
    @State private var saved = false

    var selectedStep: WorkflowStep? {
        workflow.steps.first { $0.id == selectedStepId }
    }

    var approvedCount: Int { workflow.steps.filter { $0.approved }.count }

    var body: some View {
        VStack(spacing: 0) {
            titleBar
            Divider().opacity(0.07)
            HStack(spacing: 0) {
                stepList
                Divider().opacity(0.07)
                detailPane
            }
            .frame(maxHeight: .infinity)
            Divider().opacity(0.07)
            footer
        }
        .background(Theme.winBg)
        .onAppear {
            selectedStepId = workflow.steps.first?.id
        }
    }

    // MARK: - Title bar
    var titleBar: some View {
        HStack(spacing: 10) {
            // Traffic lights spacer
            HStack(spacing: 5) {
                ForEach([Theme.red, Theme.amb, Theme.grn], id: \.self) { c in
                    Circle().fill(c).frame(width: 11, height: 11)
                }
            }
            .padding(.leading, 14)

            Spacer()

            TextField("Workflow name", text: $workflow.name)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Theme.t1)
                .multilineTextAlignment(.center)
                .textFieldStyle(.plain)
                .frame(maxWidth: 280)

            Spacer()

            // Export JSON
            Button(action: exportJSON) {
                Text("Export")
                    .font(.system(size: 12))
                    .foregroundColor(Theme.t3)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(Theme.ctrl)
                    .cornerRadius(5)
                    .overlay(RoundedRectangle(cornerRadius: 5).stroke(Theme.bdiv, lineWidth: 1))
            }
            .buttonStyle(PlainButtonStyle())
            .padding(.trailing, 14)
        }
        .frame(height: 48)
        .background(Theme.winBg)
    }

    // MARK: - Step list (left rail)
    var stepList: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Steps")
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(Theme.t3)
                .padding(.horizontal, 14)
                .padding(.top, 14)
                .padding(.bottom, 8)

            ScrollView {
                VStack(spacing: 2) {
                    ForEach(workflow.steps) { step in
                        ReviewStepRow(
                            step: step,
                            isSelected: selectedStepId == step.id,
                            workflowDir: workflowDataDir()
                        ) {
                            selectedStepId = step.id
                        }
                    }
                }
                .padding(.horizontal, 8)
                .padding(.bottom, 12)
            }
        }
        .frame(width: 230)
        .background(Theme.surf.opacity(0.25))
    }

    // MARK: - Detail pane (right)
    @ViewBuilder
    var detailPane: some View {
        if let step = selectedStep {
            ReviewDetailPane(
                step: step,
                workflowDir: workflowDataDir(),
                onApprove: { approveStep(step) },
                onRemove: { removeStep(step) }
            )
        } else {
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
    }

    // MARK: - Footer
    var footer: some View {
        HStack {
            Button("Remove Step") {
                if let step = selectedStep { removeStep(step) }
            }
            .font(.system(size: 12))
            .foregroundColor(Theme.red)
            .buttonStyle(PlainButtonStyle())
            .disabled(selectedStep == nil)

            Spacer()

            Text("\(approvedCount) of \(workflow.steps.count) approved")
                .font(.system(size: 12))
                .foregroundColor(Theme.t2)

            Button("Approve All") {
                approveAll()
            }
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(Theme.t2)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Theme.ctrl)
            .cornerRadius(6)
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(Theme.bdiv, lineWidth: 1))
            .buttonStyle(PlainButtonStyle())

            Button(action: saveAndClose) {
                HStack(spacing: 6) {
                    if saved {
                        Image(systemName: "checkmark")
                    } else {
                        Image(systemName: "square.and.arrow.down")
                    }
                    Text(saved ? "Saved!" : "Save Workflow")
                        .fontWeight(.semibold)
                }
                .font(.system(size: 13))
                .foregroundColor(.white)
                .padding(.horizontal, 16)
                .padding(.vertical, 7)
                .background(saved ? Theme.grn : Theme.blue)
                .cornerRadius(7)
            }
            .buttonStyle(PlainButtonStyle())
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 11)
        .background(Theme.winBg)
    }

    // MARK: - Actions
    func approveStep(_ step: WorkflowStep) {
        guard let idx = workflow.steps.firstIndex(where: { $0.id == step.id }) else { return }
        workflow.steps[idx].approved = true
        workflow.steps[idx].needsReview = false
        // Auto-advance to next step
        if idx + 1 < workflow.steps.count {
            selectedStepId = workflow.steps[idx + 1].id
        }
    }

    func removeStep(_ step: WorkflowStep) {
        workflow.steps.removeAll { $0.id == step.id }
        // Renumber
        for i in workflow.steps.indices { workflow.steps[i].n = i + 1 }
        selectedStepId = workflow.steps.first?.id
    }

    func approveAll() {
        for i in workflow.steps.indices {
            workflow.steps[i].approved = true
            workflow.steps[i].needsReview = false
        }
    }

    func saveAndClose() {
        store.addOrUpdate(workflow)
        Task { try? await BackendClient.shared.updateWorkflow(workflow) }
        saved = true
        Task {
            try? await Task.sleep(nanoseconds: 1_200_000_000)
            await MainActor.run {
                AppState.shared.confirmationWindowController?.close()
                AppState.shared.confirmationWindowController = nil
            }
        }
    }

    func exportJSON() {
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

    // Base path where the backend stores screenshots for this workflow
    func workflowDataDir() -> URL? {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        return appSupport.appendingPathComponent("ComputerFlow/tmp", isDirectory: true)
    }
}

// MARK: - ReviewStepRow
struct ReviewStepRow: View {
    let step: WorkflowStep
    let isSelected: Bool
    let workflowDir: URL?
    let onTap: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            // Thumbnail
            thumbnailView
                .frame(width: 48, height: 32)
                .cornerRadius(4)
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(Theme.bdiv, lineWidth: 1))

            VStack(alignment: .leading, spacing: 2) {
                Text(step.actionLabel)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(Theme.t1)
                    .lineLimit(1)
                let detail = step.displayIntent
                Text(detail)
                    .font(.system(size: 10.5))
                    .foregroundColor(Theme.t2)
                    .lineLimit(1)
            }

            Spacer()

            statusDot
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(isSelected ? Theme.surf : Color.clear)
        .cornerRadius(7)
        .overlay(RoundedRectangle(cornerRadius: 7).stroke(isSelected ? Theme.bdiv : Color.clear, lineWidth: 1))
        .contentShape(Rectangle())
        .onTapGesture { onTap() }
    }

    @ViewBuilder
    var thumbnailView: some View {
        if let img = loadThumbnail() {
            Image(nsImage: img)
                .resizable()
                .aspectRatio(contentMode: .fill)
        } else {
            LinearGradient(
                colors: stepColors,
                startPoint: .topLeading, endPoint: .bottomTrailing
            )
        }
    }

    var stepColors: [Color] {
        let palette: [[Color]] = [
            [Color(hex: "#1a1a2e"), Color(hex: "#16213e")],
            [Color(hex: "#0f3460"), Color(hex: "#533483")],
            [Color(hex: "#1b1b2f"), Color(hex: "#2b2d42")],
            [Color(hex: "#16213e"), Color(hex: "#0f3460")],
            [Color(hex: "#0a0a1a"), Color(hex: "#1a1a2e")],
        ]
        return palette[step.n % palette.count]
    }

    func loadThumbnail() -> NSImage? {
        guard let rel = step.screenshot, !rel.isEmpty else { return nil }
        // step.screenshot is like "screenshots/ev_0000.jpg" — look in tmp recording dirs
        guard let base = workflowDir else { return nil }
        // Search all recording dirs for this screenshot file
        let name = URL(fileURLWithPath: rel).lastPathComponent
        if let dirs = try? FileManager.default.contentsOfDirectory(at: base, includingPropertiesForKeys: nil) {
            for dir in dirs {
                let candidate = dir.appendingPathComponent("screenshots").appendingPathComponent(name)
                if FileManager.default.fileExists(atPath: candidate.path),
                   let img = NSImage(contentsOf: candidate) {
                    return img
                }
            }
        }
        return nil
    }

    @ViewBuilder
    var statusDot: some View {
        if step.needsReview {
            Circle().fill(Theme.amb).frame(width: 7, height: 7)
        } else if step.approved {
            Circle().fill(Theme.grn).frame(width: 7, height: 7)
        } else {
            Circle().stroke(Theme.t3.opacity(0.5), lineWidth: 1).frame(width: 7, height: 7)
        }
    }
}

// MARK: - ReviewDetailPane
struct ReviewDetailPane: View {
    let step: WorkflowStep
    let workflowDir: URL?
    let onApprove: () -> Void
    let onRemove: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Step header
            HStack(spacing: 10) {
                ZStack {
                    Circle()
                        .fill(Theme.surf)
                        .overlay(Circle().stroke(Theme.bdiv, lineWidth: 1))
                        .frame(width: 28, height: 28)
                    Text("\(step.n)")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(Theme.t2)
                }
                VStack(alignment: .leading, spacing: 1) {
                    HStack(spacing: 8) {
                        Text(step.actionLabel)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(Theme.t1)
                        executorBadge
                        if step.needsReview {
                            needsReviewBadge
                        }
                    }
                    Text(step.displayIntent)
                        .font(.system(size: 12))
                        .foregroundColor(Theme.t2)
                        .lineLimit(2)
                }
                Spacer()
            }
            .padding(.horizontal, 22)
            .padding(.top, 20)
            .padding(.bottom, 14)

            // Screenshot
            screenshotView
                .frame(maxWidth: .infinity)
                .frame(height: 280)
                .cornerRadius(10)
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.bdiv, lineWidth: 1))
                .padding(.horizontal, 22)
                .padding(.bottom, 16)

            // Target description
            if let desc = step.target.description, !desc.isEmpty {
                HStack(alignment: .top, spacing: 8) {
                    Text("Target")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(Theme.t3)
                        .frame(width: 48, alignment: .leading)
                    Text(desc)
                        .font(Theme.mono(11))
                        .foregroundColor(Theme.t2)
                        .lineLimit(3)
                }
                .padding(.horizontal, 22)
                .padding(.bottom, 12)
            }

            // Value chip
            if let val = step.value {
                HStack(spacing: 8) {
                    Text("Value")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(Theme.t3)
                        .frame(width: 48, alignment: .leading)
                    Text(val.displayString)
                        .font(Theme.mono(11))
                        .foregroundColor(val.isVariable ? Theme.blue : Theme.t1)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(val.isVariable ? Theme.blue.opacity(0.12) : Theme.surf)
                        .cornerRadius(5)
                }
                .padding(.horizontal, 22)
                .padding(.bottom, 12)
            }

            Spacer()

            // Approve button
            HStack(spacing: 10) {
                Button(action: onApprove) {
                    HStack(spacing: 6) {
                        Image(systemName: step.approved ? "checkmark.circle.fill" : "checkmark.circle")
                        Text(step.approved ? "Approved" : "Approve Step")
                            .fontWeight(.medium)
                    }
                    .font(.system(size: 13))
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 9)
                    .background(step.approved ? Theme.grn : Theme.blue)
                    .cornerRadius(8)
                }
                .buttonStyle(PlainButtonStyle())
            }
            .padding(.horizontal, 22)
            .padding(.bottom, 16)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    var screenshotView: some View {
        if let img = loadScreenshot() {
            Image(nsImage: img)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .background(Color.black)
        } else {
            ZStack {
                LinearGradient(
                    colors: [Color(hex: "#0d1117"), Color(hex: "#161b22")],
                    startPoint: .topLeading, endPoint: .bottomTrailing
                )
                VStack(spacing: 8) {
                    Image(systemName: "photo")
                        .font(.system(size: 28))
                        .foregroundColor(Color.white.opacity(0.2))
                    Text("No screenshot")
                        .font(.system(size: 12))
                        .foregroundColor(Color.white.opacity(0.2))
                }
            }
        }
    }

    var executorBadge: some View {
        let isKernel = step.executor?.kind == "kernel"
        return Text(isKernel ? "Browser" : "Desktop")
            .font(.system(size: 10, weight: .medium))
            .foregroundColor(isKernel ? Theme.blue : Theme.amb)
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .background((isKernel ? Theme.blue : Theme.amb).opacity(0.12))
            .cornerRadius(4)
    }

    var needsReviewBadge: some View {
        Text("Needs review")
            .font(.system(size: 10, weight: .medium))
            .foregroundColor(Theme.amb)
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .background(Theme.amb.opacity(0.12))
            .cornerRadius(4)
    }

    func loadScreenshot() -> NSImage? {
        guard let rel = step.screenshot, !rel.isEmpty else { return nil }
        guard let base = workflowDir else { return nil }
        let name = URL(fileURLWithPath: rel).lastPathComponent
        if let dirs = try? FileManager.default.contentsOfDirectory(at: base, includingPropertiesForKeys: nil) {
            for dir in dirs.sorted(by: { $0.lastPathComponent > $1.lastPathComponent }) {
                let candidate = dir.appendingPathComponent("screenshots").appendingPathComponent(name)
                if FileManager.default.fileExists(atPath: candidate.path),
                   let img = NSImage(contentsOf: candidate) {
                    return img
                }
            }
        }
        return nil
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
