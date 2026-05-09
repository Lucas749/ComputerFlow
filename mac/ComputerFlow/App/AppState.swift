import Foundation
import Combine
import SwiftUI

private extension URL {
    var creationDate: Date? {
        (try? resourceValues(forKeys: [.creationDateKey]))?.creationDate
    }
}

// MARK: - DisplayInfo
struct DisplayInfo: Identifiable {
    let id: CGDirectDisplayID
    let index: Int
    let width: Int
    let height: Int
    var label: String { "Display \(index)  \(width)×\(height)" }
}

// MARK: - AppStatus
enum AppStatus {
    case ready, recording, compiling, running
}

@MainActor
class AppState: ObservableObject {
    static let shared = AppState()

    @Published var status: AppStatus = .ready
    @Published var currentWorkflowId: String?
    @Published var currentRunId: String?
    @Published var permissionsGranted: Bool = false
    @Published var selectedDisplayID: CGDirectDisplayID? = nil
    @Published var isDarkMode: Bool = true {
        didSet { NSApp.appearance = NSAppearance(named: isDarkMode ? .darkAqua : .aqua) }
    }
    @Published var compileSubline: String = "Preparing…"
    @Published var compileProgress: Double = 0
    @Published var availableDisplays: [DisplayInfo] = []

    var recordingPanelController: RecordingPanelController?
    var confirmationWindowController: WorkflowConfirmationWindowController?
    var pipWindowController: PipWindowController?
    var editorWindowController: WorkflowEditorWindowController?

    private let recorder = ScreenRecorder()
    private let telemetry = EventTelemetry()
    private var streamTask: Task<Void, Never>?

    private init() {
        Task { await loadDisplays() }
    }

    func loadDisplays() async {
        let displays = await ScreenRecorder.availableDisplays()
        let infos = displays.enumerated().map { i, d in
            DisplayInfo(id: d.displayID, index: i + 1, width: d.width, height: d.height)
        }
        availableDisplays = infos
        if selectedDisplayID == nil, let first = infos.first {
            selectedDisplayID = first.id
        }
    }

    // MARK: - Toggle Recording
    func toggleRecording() {
        switch status {
        case .ready:     startRecording()
        case .recording: Task { await stopAndUpload() }
        default: break
        }
    }

    // MARK: - Start Recording
    func startRecording() {
        guard status == .ready else {
            print("[CF] startRecording blocked — status=\(status)")
            return
        }
        status = .recording
        recordingPanelController?.close()
        recordingPanelController = RecordingPanelController(displayID: selectedDisplayID)
        recordingPanelController?.show()

        let recID = UUID().uuidString
        print("[CF] Starting recording id=\(recID)")
        do { try telemetry.start(recordingID: recID, displayID: selectedDisplayID) }
        catch { print("[CF] Telemetry start failed: \(error)") }

        recorder.selectedDisplayID = selectedDisplayID
        recorder.recordingRootDir = telemetry.rootDir
        Task {
            do {
                try await recorder.startRecording()
                print("[CF] SCStream started OK")
            } catch {
                self.status = .ready
                print("[CF] Recording failed to start: \(error)")
            }
        }
    }

    // MARK: - Abort Recording
    func abortRecording() async {
        print("[CF] Aborting recording")
        telemetry.stop()
        recordingPanelController?.close()
        recordingPanelController = nil
        status = .ready
        _ = try? await recorder.stopRecording()
    }

    // MARK: - Stop + Upload
    func stopAndUpload() async {
        print("[CF] stopAndUpload called, status=\(status)")
        guard status == .recording else {
            print("[CF] stopAndUpload blocked — not recording")
            return
        }
        telemetry.stop()
        status = .compiling
        compileSubline = "Saving recording…"
        compileProgress = 0

        do {
            print("[CF] Stopping SCStream…")
            let videoURL = try await recorder.stopRecording()
            let videoSize = (try? FileManager.default.attributesOfItem(atPath: videoURL.path)[.size] as? Int) ?? 0
            print("[CF] Video saved: \(videoURL.lastPathComponent) (\(videoSize) bytes)")

            let eventsURL = try telemetry.saveEventsJSON()
            let screenshotsDir = telemetry.screenshotsDir
            let shotCount = (try? FileManager.default.contentsOfDirectory(atPath: screenshotsDir?.path ?? "").count) ?? 0
            print("[CF] Events saved: \(eventsURL.lastPathComponent), screenshots: \(shotCount)")

            compileSubline = "Uploading…"
            compileProgress = 10

            let workflowId = try await BackendClient.shared.uploadRecording(
                videoURL: videoURL,
                eventsURL: eventsURL,
                screenshotsDir: screenshotsDir
            )
            print("[CF] Uploaded → workflowId=\(workflowId)")
            currentWorkflowId = workflowId
            compileSubline = "Translating visual intent…"
            compileProgress = 20

            streamTask = Task {
                for await event in BackendClient.shared.compileStream(workflowId: workflowId) {
                    compileSubline = event.subline
                    compileProgress = event.progress
                    print("[CF] Compile event: stage=\(event.stage) progress=\(event.progress) subline=\(event.subline)")
                    if event.error == true || event.stage == -1 {
                        print("[CF] Compile error: \(event.subline)")
                        recordingPanelController?.close()
                        recordingPanelController = nil
                        status = .ready
                        break
                    }
                    if event.stage == 3 && event.progress >= 100 {
                        compileComplete(workflowId: workflowId)
                        break
                    }
                }
            }
        } catch {
            print("[CF] stopAndUpload ERROR: \(error)")
            recordingPanelController?.close()
            recordingPanelController = nil
            status = .ready
        }
    }

    // MARK: - Compile Complete
    func compileComplete(workflowId: String) {
        print("[CF] ✅ compileComplete ENTERED for \(workflowId)")
        streamTask?.cancel()
        recordingPanelController?.close()
        recordingPanelController = nil

        Task { @MainActor in
            print("[CF] ⏳ Fetching workflow JSON…")
            do {
                let workflow = try await BackendClient.shared.getWorkflow(id: workflowId)
                print("[CF] ✅ Got workflow: \(workflow.name) with \(workflow.steps.count) steps")

                saveDebugWorkflow(workflow, workflowId: workflowId)

                WorkflowStore.shared.addOrUpdate(workflow)
                print("[CF] ✅ Saved to WorkflowStore")
                status = .ready

                print("[CF] 🪟 Creating review window controller…")
                let controller = WorkflowConfirmationWindowController(workflow: workflow)
                confirmationWindowController = controller
                print("[CF] 🪟 Calling controller.show()…")
                controller.show()
                print("[CF] ✅ Window shown.")
            } catch {
                print("[CF] ❌ compileComplete ERROR: \(error)")
                if let decodingError = error as? DecodingError {
                    print("[CF] ❌ Decoding detail: \(decodingError)")
                }
                status = .ready
            }
        }
    }

    private func saveDebugWorkflow(_ workflow: WorkflowModel, workflowId: String) {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        guard let data = try? encoder.encode(workflow) else { return }
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        // Find most recent tmp recording dir
        let tmpDir = appSupport.appendingPathComponent("ComputerFlow/tmp", isDirectory: true)
        let debugFile: URL
        if let dirs = try? FileManager.default.contentsOfDirectory(at: tmpDir, includingPropertiesForKeys: [.creationDateKey]),
           let latest = dirs.sorted(by: { ($0.creationDate ?? .distantPast) > ($1.creationDate ?? .distantPast) }).first {
            debugFile = latest.appendingPathComponent("workflow_response.json")
        } else {
            debugFile = tmpDir.appendingPathComponent("\(workflowId)_workflow_response.json")
        }
        try? data.write(to: debugFile)
        print("[CF] Debug workflow JSON saved to \(debugFile.path)")
    }

    // MARK: - Start Run
    func startRun(workflowId: String, inputs: [[String: String]]? = nil) {
        Task {
            do {
                let result = try await BackendClient.shared.startRun(workflowId: workflowId, inputs: inputs)
                currentRunId = result.runId
                status = .running
                let pip = PipWindowController(runResult: result)
                pipWindowController = pip
                pip.show()
            } catch { print("[CF] startRun ERROR: \(error)") }
        }
    }

    // MARK: - Open Editor
    func openEditor(workflow: WorkflowModel) {
        let controller = WorkflowEditorWindowController(workflow: workflow)
        editorWindowController = controller
        controller.show()
    }

    // MARK: - Run Finished
    func runFinished() {
        pipWindowController?.close()
        pipWindowController = nil
        status = .ready
    }
}
