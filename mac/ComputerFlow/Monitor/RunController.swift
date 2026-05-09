import Foundation
import Combine
import AppKit

// MARK: - RunController
@MainActor
class RunController: ObservableObject {
    @Published var stepIndex: Int = 0
    @Published var totalSteps: Int = 0
    @Published var logLines: [String] = []
    @Published var status: String = "running"
    @Published var liveViewUrl: String?         // Set when WS delivers {"type":"live_view"}
    @Published var environment: String = ""     // "browser" or "desktop"
    @Published var currentScreenshot: NSImage?  // Latest desktop CUA frame
    @Published var currentAction: String = ""
    @Published var answer: String?

    private var streamTask: Task<Void, Never>?
    let runId: String

    init(runId: String, liveViewUrl: String? = nil, totalSteps: Int = 0) {
        self.runId = runId
        self.liveViewUrl = liveViewUrl
        self.totalSteps = totalSteps
    }

    var isBrowserRun: Bool { environment == "browser" || (liveViewUrl?.contains("onkernel") ?? false) }

    func start() {
        streamTask?.cancel()
        streamTask = Task { @MainActor in
            for await event in BackendClient.shared.runStream(runId: runId) {
                handle(event)
            }
        }
    }

    private func handle(_ event: RunEvent) {
        switch event.type {
        case "run_started":
            logLines.append("Run started")

        case "live_view":
            if let urls = event.urls {
                let kernel = urls["kernel_browser"]
                let desktop = urls["lightcone_os"]
                // Prefer kernel browser URL if present
                liveViewUrl = kernel ?? desktop
                environment = kernel != nil ? "browser" : "desktop"
                if let url = liveViewUrl {
                    logLines.append("🖥 Live view: \(url.prefix(80))")
                }
            }

        case "step":
            if let i = event.stepIndex { stepIndex = i + 1 }
            if let t = event.totalSteps { totalSteps = t }
            if let env = event.environment { environment = env }
            if let intent = event.intent, !intent.isEmpty {
                logLines.append("▶ \(intent)")
                currentAction = intent
            }

        case "action":
            if let a = event.action {
                currentAction = a
                logLines.append("• \(a)")
            }

        case "screenshot":
            // Desktop CUA frame — render as current screenshot
            if let b64 = event.b64,
               let data = Data(base64Encoded: b64),
               let img = NSImage(data: data) {
                currentScreenshot = img
            }

        case "run_finished":
            status = event.status ?? "completed"
            if let ans = event.answer { answer = ans; logLines.append("✓ \(ans)") }
            if let err = event.error  { logLines.append("✗ \(err)") }
            Task { @MainActor in
                try? await Task.sleep(nanoseconds: 1_500_000_000)
                AppState.shared.runFinished()
            }

        default:
            // Legacy flat-field events (stepIndex/logLine/status)
            if let idx = event.stepIndex { stepIndex = idx }
            if let total = event.totalSteps { totalSteps = total }
            if let s = event.status, !s.isEmpty {
                status = s
                if ["completed", "failed", "stopped", "error"].contains(s) {
                    AppState.shared.runFinished()
                }
            }
        }

        if logLines.count > 100 { logLines.removeFirst(logLines.count - 100) }
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
