import SwiftUI
import AppKit
import WebKit

// MARK: - PipWindowController
class PipWindowController {
    private var panel: NSPanel?
    private let runResult: RunResult

    init(runResult: RunResult) {
        self.runResult = runResult
    }

    @MainActor func show() {
        let runController = RunController(runId: runResult.runId, liveViewUrl: runResult.liveViewUrl)
        let view = PipView(runResult: runResult, runController: runController)
        let hosting = NSHostingView(rootView: view)

        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 330),
            styleMask: [.nonactivatingPanel, .borderless],
            backing: .buffered,
            defer: false
        )
        panel.level = .floating
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = true
        panel.isMovableByWindowBackground = true
        panel.contentView = hosting
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

        if let screen = NSScreen.main {
            let sf = screen.visibleFrame
            let x = sf.maxX - 520 - 20
            let y = sf.minY + 20
            panel.setFrameOrigin(NSPoint(x: x, y: y))
        }

        panel.orderFront(nil)
        self.panel = panel

        runController.start()
    }

    func close() {
        panel?.close()
        panel = nil
    }
}

// MARK: - PipView
struct PipView: View {
    let runResult: RunResult
    @StateObject var runController: RunController
    @State private var isHovering = false

    var body: some View {
        ZStack {
            // Background — kernel webview or desktop screenshot
            liveArea
                .cornerRadius(12)

            // Top overlay
            VStack {
                HStack {
                    agentActiveBadge
                    Spacer()
                    stepCounterBadge
                }
                .padding(.horizontal, 10)
                .padding(.top, 10)

                Spacer()

                // Log lines at the bottom
                logLinesView
                    .padding(.horizontal, 10)
                    .padding(.bottom, 10)
            }

            if isHovering {
                hoverOverlay
            }
        }
        .frame(width: 520, height: 330)
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.6), radius: 20, x: 0, y: 10)
        .onHover { isHovering = $0 }
    }

    // MARK: - Live area
    @ViewBuilder
    var liveArea: some View {
        if runController.isBrowserRun {
            if let urlStr = runController.liveViewUrl, let url = URL(string: urlStr) {
                KernelWebView(url: url)
            } else {
                waitingPlaceholder("Waiting for browser session…")
            }
        } else {
            if let img = runController.currentScreenshot {
                Image(nsImage: img)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
            } else {
                waitingPlaceholder("Waiting for agent screenshots…")
            }
        }
    }

    func waitingPlaceholder(_ msg: String) -> some View {
        ZStack {
            Color(red: 10/255, green: 10/255, blue: 14/255)
            VStack(spacing: 10) {
                ProgressView()
                    .scaleEffect(0.9)
                    .progressViewStyle(CircularProgressViewStyle(tint: .white))
                Text(msg)
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.55))
            }
        }
    }

    // MARK: - Badges
    var agentActiveBadge: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(Theme.grn)
                .frame(width: 7, height: 7)
                .modifier(RecBlinkModifier())
            Text(runController.isBrowserRun ? "Browser Agent" : "Desktop Agent")
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(.white)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(Color.black.opacity(0.6))
        .overlay(Capsule().stroke(Color.white.opacity(0.12), lineWidth: 1))
        .clipShape(Capsule())
    }

    var stepCounterBadge: some View {
        Group {
            if runController.totalSteps > 0 {
                Text("Step \(runController.stepIndex)/\(runController.totalSteps)")
            } else {
                Text("Starting…")
            }
        }
        .font(.system(size: 11, weight: .medium).monospacedDigit())
        .foregroundColor(.white)
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(Color.black.opacity(0.6))
        .overlay(Capsule().stroke(Color.white.opacity(0.12), lineWidth: 1))
        .clipShape(Capsule())
    }

    var logLinesView: some View {
        VStack(alignment: .leading, spacing: 2) {
            let lines = runController.logLines.suffix(3)
            let arr = Array(lines)
            ForEach(0..<arr.count, id: \.self) { i in
                Text(arr[i])
                    .font(.system(size: 10).monospaced())
                    .foregroundColor(i == arr.count - 1 ? Color.white.opacity(0.85) : Color.white.opacity(0.35))
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(Color.black.opacity(0.4))
        .cornerRadius(6)
    }

    // MARK: - Hover overlay
    var hoverOverlay: some View {
        ZStack {
            Color.black.opacity(0.5)

            HStack(spacing: 14) {
                pipControlButton(icon: "pause.fill", label: "Pause") {
                    runController.pause()
                }
                pipControlButton(icon: "stop.fill", label: "Stop") {
                    runController.stop()
                }
                // Take Control — kernel/browser runs only
                if runController.isBrowserRun {
                    Button(action: { runController.takeControl() }) {
                        Text("Take Control")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(.black)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 8)
                            .background(Color.white)
                            .cornerRadius(8)
                    }
                    .buttonStyle(PlainButtonStyle())
                }
            }
        }
        .cornerRadius(12)
    }

    func pipControlButton(icon: String, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 18))
                    .foregroundColor(.white)
                Text(label)
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.7))
            }
            .frame(width: 52, height: 52)
            .background(Color.white.opacity(0.12))
            .cornerRadius(10)
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - KernelWebView
struct KernelWebView: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.mediaTypesRequiringUserActionForPlayback = []
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.allowsMagnification = true
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        if webView.url != url {
            webView.load(URLRequest(url: url))
        }
    }
}
