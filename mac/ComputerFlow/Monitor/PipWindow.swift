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
        let runController = RunController(runId: runResult.runId)
        let view = PipView(runResult: runResult, runController: runController)
        let hosting = NSHostingView(rootView: view)

        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 460, height: 259),
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

        // Position bottom-right
        if let screen = NSScreen.main {
            let sf = screen.visibleFrame
            let x = sf.maxX - 460 - 20
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

// MARK: - PipView (Screen 5)
struct PipView: View {
    let runResult: RunResult
    @StateObject var runController: RunController
    @State private var isHovering = false

    var body: some View {
        ZStack {
            // WebView background
            if let urlStr = runResult.liveViewUrl, let url = URL(string: urlStr) {
                WebViewContainer(url: url)
                    .cornerRadius(12)
            } else {
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color(red: 10/255, green: 10/255, blue: 14/255))
            }

            // Overlay
            VStack {
                // Top row
                HStack {
                    agentActiveBadge
                    Spacer()
                    stepCounterBadge
                }
                .padding(.horizontal, 10)
                .padding(.top, 10)

                Spacer()

                // Log lines
                logLinesView
                    .padding(.horizontal, 10)
                    .padding(.bottom, 10)
            }

            // Hover overlay
            if isHovering {
                hoverOverlay
            }
        }
        .frame(width: 460, height: 259)
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.6), radius: 20, x: 0, y: 10)
        .onHover { isHovering = $0 }
    }

    // MARK: - Agent Active Badge
    var agentActiveBadge: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(Theme.grn)
                .frame(width: 7, height: 7)
                .modifier(RecBlinkModifier())
            Text("Agent Active")
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(Theme.t1)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(Color.black.opacity(0.6))
        .overlay(Capsule().stroke(Color.white.opacity(0.12), lineWidth: 1))
        .clipShape(Capsule())
    }

    // MARK: - Step Counter
    var stepCounterBadge: some View {
        Text("Step \(runController.stepIndex)/\(runController.totalSteps)")
            .font(Theme.mono(11))
            .foregroundColor(Theme.t1)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(Color.black.opacity(0.6))
            .overlay(Capsule().stroke(Color.white.opacity(0.12), lineWidth: 1))
            .clipShape(Capsule())
    }

    // MARK: - Log Lines
    var logLinesView: some View {
        VStack(alignment: .leading, spacing: 2) {
            let lines = runController.logLines.suffix(3)
            let arr = Array(lines)
            ForEach(0..<arr.count, id: \.self) { i in
                Text(arr[i])
                    .font(Theme.mono(10))
                    .foregroundColor(i == arr.count - 1 ? Color.white.opacity(0.72) : Color.white.opacity(0.25))
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Hover Overlay
    var hoverOverlay: some View {
        ZStack {
            Color.black.opacity(0.46)

            HStack(spacing: 14) {
                // Pause
                pipControlButton(icon: "pause.fill", label: "Pause") {
                    runController.pause()
                }

                // Stop
                pipControlButton(icon: "stop.fill", label: "Stop") {
                    runController.stop()
                }

                // Take Control
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
        .cornerRadius(12)
    }

    func pipControlButton(icon: String, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 18))
                    .foregroundColor(Theme.t1)
                Text(label)
                    .font(.system(size: 10))
                    .foregroundColor(Theme.t2)
            }
            .frame(width: 52, height: 52)
            .background(Color.white.opacity(0.1))
            .cornerRadius(10)
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - WebViewContainer
struct WebViewContainer: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {}
}
