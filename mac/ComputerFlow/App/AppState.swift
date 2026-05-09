import Foundation
import Combine
import SwiftUI

// MARK: - AppState
enum AppStatus {
    case ready
    case recording
    case compiling
    case running
}

@MainActor
class AppState: ObservableObject {
    static let shared = AppState()

    @Published var status: AppStatus = .ready
    @Published var currentWorkflowId: String?
    @Published var currentRunId: String?
    @Published var permissionsGranted: Bool = false

    // Window controllers
    var recordingPanelController: RecordingPanelController?
    var compilingWindowController: CompilingWindowController?
    var confirmationWindowController: WorkflowConfirmationWindowController?
    var pipWindowController: PipWindowController?
    var editorWindowController: WorkflowEditorWindowController?

    private let recorder = ScreenRecorder()
    private let telemetry = EventTelemetry()
    private var recordingStartTime: Date?
    private var currentRecordingID: String?

    private init() {}

    // MARK: - Toggle Recording
    func toggleRecording() {
        switch status {
        case .ready:
            startRecording()
        case .recording:
            Task { await stopAndUpload() }
        default:
            break
        }
    }

    // MARK: - Start Recording
    func startRecording() {
        status = .recording

        // Show recording pill
        if recordingPanelController == nil {
            recordingPanelController = RecordingPanelController()
        }
        recordingPanelController?.show()

        recordingStartTime = Date()
        let recID = UUID().uuidString
        currentRecordingID = recID
        do {
            try telemetry.start(recordingID: recID)
        } catch {
            print("Telemetry start failed: \(error)")
        }

        Task {
            do {
                try await recorder.startRecording()
            } catch {
                await MainActor.run {
                    self.status = .ready
                    print("Recording start failed: \(error)")
                }
            }
        }
    }

    // MARK: - Abort Recording
    func abortRecording() {
        telemetry.stop()
        recordingPanelController?.close()
        recordingPanelController = nil
        status = .ready

        Task {
            _ = try? await recorder.stopRecording()
        }
    }

    // MARK: - Stop + Upload
    func stopAndUpload() async {
        telemetry.stop()
        recordingPanelController?.close()
        recordingPanelController = nil
        status = .compiling

        // Show compiling window
        let compilingController = CompilingWindowController()
        compilingWindowController = compilingController
        compilingController.show()

        do {
            let videoURL = try await recorder.stopRecording()
            let eventsURL = try telemetry.saveEventsJSON()
            let screenshotsDir = telemetry.screenshotsDir
            let workflowId = try await BackendClient.shared.uploadRecording(
                videoURL: videoURL,
                eventsURL: eventsURL,
                screenshotsDir: screenshotsDir
            )

            currentWorkflowId = workflowId
            compilingController.workflowId = workflowId
            compilingController.startStreaming()
        } catch {
            compilingController.close()
            compilingWindowController = nil
            status = .ready
            print("Upload failed: \(error)")
        }
    }

    // MARK: - Compile Complete
    func compileComplete(workflowId: String) {
        compilingWindowController?.close()
        compilingWindowController = nil

        Task {
            do {
                let workflow = try await BackendClient.shared.getWorkflow(id: workflowId)
                WorkflowStore.shared.addOrUpdate(workflow)

                await MainActor.run {
                    let controller = WorkflowConfirmationWindowController(workflow: workflow)
                    self.confirmationWindowController = controller
                    controller.show()
                }
            } catch {
                print("Failed to load workflow: \(error)")
                status = .ready
            }
        }
    }

    // MARK: - Start Run
    func startRun(workflowId: String, inputs: [[String: String]]? = nil) {
        Task {
            do {
                let result = try await BackendClient.shared.startRun(workflowId: workflowId, inputs: inputs)
                currentRunId = result.runId
                status = .running

                let pipController = PipWindowController(runResult: result)
                pipWindowController = pipController
                pipController.show()
            } catch {
                print("Failed to start run: \(error)")
            }
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
