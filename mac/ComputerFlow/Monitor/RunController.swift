import Foundation
import Combine

// MARK: - RunController
@MainActor
class RunController: ObservableObject {
    @Published var stepIndex: Int = 0
    @Published var totalSteps: Int = 0
    @Published var logLines: [String] = []
    @Published var status: String = "running"

    private var streamTask: Task<Void, Never>?
    let runId: String

    init(runId: String, totalSteps: Int = 0) {
        self.runId = runId
        self.totalSteps = totalSteps
    }

    func start() {
        streamTask?.cancel()
        streamTask = Task { @MainActor in
            for await event in BackendClient.shared.runStream(runId: runId) {
                if let idx = event.stepIndex { stepIndex = idx }
                if let total = event.totalSteps { totalSteps = total }
                if let line = event.logLine {
                    logLines.append(line)
                    if logLines.count > 50 { logLines.removeFirst() }
                }
                if let s = event.status {
                    status = s
                    if s == "completed" || s == "failed" || s == "stopped" {
                        AppState.shared.runFinished()
                        break
                    }
                }
            }
        }
    }

    func pause() {
        Task { try? await BackendClient.shared.controlRun(runId: runId, action: "pause") }
    }

    func stop() {
        Task {
            try? await BackendClient.shared.controlRun(runId: runId, action: "stop")
            streamTask?.cancel()
            AppState.shared.runFinished()
        }
    }

    func takeControl() {
        Task { try? await BackendClient.shared.controlRun(runId: runId, action: "take_control") }
    }

    deinit {
        streamTask?.cancel()
    }
}
