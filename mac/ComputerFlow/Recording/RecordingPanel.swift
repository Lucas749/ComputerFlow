import SwiftUI
import AppKit

// MARK: - RecordingPanelController
class RecordingPanelController {
    private var panel: NSPanel?
    private var hostingView: NSHostingView<RecordingPillView>?

    func show() {
        let view = RecordingPillView()
        let hosting = NSHostingView(rootView: view)
        hosting.frame = NSRect(x: 0, y: 0, width: 380, height: 56)

        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 380, height: 56),
            styleMask: [.nonactivatingPanel, .borderless],
            backing: .buffered,
            defer: false
        )
        panel.level = .floating
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = false
        panel.contentView = hosting
        panel.isMovableByWindowBackground = true

        // Position at top center
        if let screen = NSScreen.main {
            let screenFrame = screen.frame
            let x = (screenFrame.width - 380) / 2 + screenFrame.minX
            let y = screenFrame.maxY - 80
            panel.setFrameOrigin(NSPoint(x: x, y: y))
        }

        panel.orderFront(nil)
        self.panel = panel
        self.hostingView = hosting
    }

    func close() {
        panel?.close()
        panel = nil
    }
}

// MARK: - RecordingPillView (Screen 2)
struct RecordingPillView: View {
    @State private var expanded = true
    @State private var showTimer = false
    @State private var elapsed: TimeInterval = 0
    @State private var timer: Timer?
    @State private var pillState: PillState = .dots

    enum PillState { case minimised, dots, timer }

    var body: some View {
        ZStack {
            if expanded {
                expandedPill
            } else {
                minimisedPill
            }
        }
        .onAppear { startTimer() }
        .onDisappear { timer?.invalidate() }
    }

    // MARK: - Minimised Pill
    var minimisedPill: some View {
        Capsule()
            .fill(Color.white.opacity(0.08))
            .overlay(
                Capsule().stroke(Color.white.opacity(0.21), lineWidth: 1)
            )
            .frame(width: 182, height: 35)
            .onTapGesture { withAnimation(.spring(response: 0.4)) { expanded = true } }
    }

    // MARK: - Expanded Pill
    var expandedPill: some View {
        HStack(spacing: 12) {
            // Abort button
            Button(action: { Task { @MainActor in AppState.shared.abortRecording() } }) {
                Image(systemName: "xmark")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(Theme.t2)
                    .frame(width: 28, height: 28)
                    .background(Color.white.opacity(0.08))
                    .clipShape(Circle())
            }
            .buttonStyle(PlainButtonStyle())

            Spacer()

            // Center — dots or timer
            if pillState == .dots {
                DotWaveView()
            } else {
                timerView
            }

            Spacer()

            // Confirm button
            Button(action: confirmStop) {
                Image(systemName: "checkmark")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.white)
                    .frame(width: 28, height: 28)
                    .background(Theme.grn)
                    .clipShape(Circle())
            }
            .buttonStyle(PlainButtonStyle())
        }
        .padding(.horizontal, 14)
        .frame(width: 340, height: 52)
        .background(
            Capsule()
                .fill(Color(red: 10/255, green: 10/255, blue: 12/255, opacity: 0.91))
                .overlay(
                    Capsule().stroke(Color.white.opacity(0.12), lineWidth: 1)
                )
        )
        .shadow(color: .black.opacity(0.5), radius: 20, x: 0, y: 8)
        .onTapGesture {
            withAnimation { pillState = pillState == .dots ? .timer : .dots }
        }
        .transition(.asymmetric(
            insertion: .scale(scale: 0.8).combined(with: .opacity),
            removal: .scale(scale: 0.8).combined(with: .opacity)
        ))
    }

    // MARK: - Timer View
    var timerView: some View {
        HStack(spacing: 7) {
            Circle()
                .fill(Theme.red)
                .frame(width: 8, height: 8)
                .modifier(RecBlinkModifier())
            Text(timeString(elapsed))
                .font(Theme.mono(15, weight: .semibold))
                .foregroundColor(Theme.t1)
        }
    }

    func timeString(_ t: TimeInterval) -> String {
        let m = Int(t) / 60
        let s = Int(t) % 60
        return String(format: "%02d:%02d", m, s)
    }

    func startTimer() {
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
            elapsed += 1
        }
    }

    func confirmStop() {
        timer?.invalidate()
        Task { await AppState.shared.stopAndUpload() }
    }
}

// MARK: - DotWaveView
struct DotWaveView: View {
    @State private var animating = false
    let dotCount = 7
    let delays: [Double] = [0, 0.13, 0.26, 0.39, 0.52, 0.65, 0.78]

    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<dotCount, id: \.self) { i in
                DotView(delay: delays[i])
            }
        }
    }
}

struct DotView: View {
    let delay: Double
    @State private var scale: CGFloat = 0.74
    @State private var opacity: Double = 0.2

    var body: some View {
        Circle()
            .fill(Color.white)
            .frame(width: 6, height: 6)
            .scaleEffect(scale)
            .opacity(opacity)
            .onAppear {
                withAnimation(
                    .easeInOut(duration: 1.5)
                    .repeatForever(autoreverses: true)
                    .delay(delay)
                ) {
                    scale = 1.0
                    opacity = 0.86
                }
            }
    }
}

// MARK: - RecBlinkModifier
struct RecBlinkModifier: ViewModifier {
    @State private var opacity: Double = 1
    func body(content: Content) -> some View {
        content
            .opacity(opacity)
            .onAppear {
                withAnimation(.easeInOut(duration: 1.3).repeatForever(autoreverses: true)) {
                    opacity = 0.25
                }
            }
    }
}
