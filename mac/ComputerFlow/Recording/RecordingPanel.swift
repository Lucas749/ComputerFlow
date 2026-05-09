import SwiftUI
import AppKit
import ScreenCaptureKit

// MARK: - ClickablePanel
private class ClickablePanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}

// MARK: - ClickableHostingView
// Accepts first-mouse so clicks land on SwiftUI buttons without
// requiring the user to click twice (once to focus, once to act).
private class ClickableHostingView<V: View>: NSHostingView<V> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

// MARK: - RecordingPanelController
class RecordingPanelController {
    private var panel: ClickablePanel?
    private var hostingView: ClickableHostingView<AnyView>?

    static let panelW: CGFloat = 500
    static let panelH: CGFloat = 220

    func show() {
        let view = AnyView(
            RecordingPillView()
                .environmentObject(AppState.shared)
        )
        let hosting = ClickableHostingView(rootView: view)
        hosting.frame = NSRect(x: 0, y: 0, width: Self.panelW, height: Self.panelH)

        let panel = ClickablePanel(
            contentRect: NSRect(x: 0, y: 0, width: Self.panelW, height: Self.panelH),
            styleMask: [.nonactivatingPanel, .borderless],
            backing: .buffered,
            defer: false
        )
        panel.level = .statusBar
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = false
        panel.contentView = hosting
        panel.isMovableByWindowBackground = true
        panel.acceptsMouseMovedEvents = true
        panel.ignoresMouseEvents = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

        if let screen = NSScreen.main {
            let sf = screen.visibleFrame
            let x = sf.minX + (sf.width - Self.panelW) / 2
            let y = sf.minY + 16
            panel.setFrameOrigin(NSPoint(x: x, y: y))
        }

        panel.makeKeyAndOrderFront(nil)
        self.panel = panel
        self.hostingView = hosting
    }

    func close() {
        panel?.close()
        panel = nil
    }
}

// MARK: - RecordingPillView
struct RecordingPillView: View {
    @EnvironmentObject var appState: AppState
    @State private var elapsed: TimeInterval = 0
    @State private var timer: Timer?
    @State private var showTimer = false
    @State private var showScreenPicker = false
    @State private var displays: [SCDisplay] = []
    @State private var spinDeg: Double = 0

    var body: some View {
        VStack(spacing: 8) {
            Spacer(minLength: 0)

            // Pill morphs between recording and compiling states
            if appState.status == .compiling {
                compilingPill
            } else {
                mainPill
            }
        }
        .frame(width: 480, height: 140, alignment: .bottom)
        .padding(.bottom, 4)
        .onAppear {
            startTimer()
            Task { displays = await ScreenRecorder.availableDisplays() }
        }
        .onDisappear { timer?.invalidate() }
    }

    // MARK: - Compiling pill
    var compilingPill: some View {
        HStack(spacing: 14) {
            // Spinning ring
            Circle()
                .trim(from: 0.15, to: 0.85)
                .stroke(
                    AngularGradient(colors: [Theme.t3, Theme.t2], center: .center),
                    style: StrokeStyle(lineWidth: 2.5, lineCap: .round)
                )
                .frame(width: 22, height: 22)
                .rotationEffect(.degrees(spinDeg))
                .onAppear {
                    withAnimation(.linear(duration: 0.88).repeatForever(autoreverses: false)) {
                        spinDeg = 360
                    }
                }

            VStack(alignment: .leading, spacing: 3) {
                Text(appState.compileSubline)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(Theme.t1)
                    .lineLimit(1)
                    .id(appState.compileSubline)
                    .transition(.asymmetric(
                        insertion: .opacity.combined(with: .move(edge: .bottom)),
                        removal:   .opacity.combined(with: .move(edge: .top))
                    ))
                    .animation(.easeInOut(duration: 0.3), value: appState.compileSubline)

                // Progress bar
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule().fill(Color.white.opacity(0.10)).frame(height: 2)
                        Capsule()
                            .fill(Color.white.opacity(0.55))
                            .frame(width: geo.size.width * (appState.compileProgress / 100), height: 2)
                            .animation(.easeInOut(duration: 0.4), value: appState.compileProgress)
                    }
                }
                .frame(height: 2)
            }
        }
        .padding(.horizontal, 20)
        .frame(width: 360, height: 58)
        .background(
            Capsule()
                .fill(Color(red: 10/255, green: 10/255, blue: 12/255, opacity: 0.94))
                .overlay(Capsule().stroke(Color.white.opacity(0.11), lineWidth: 1))
        )
        .shadow(color: .black.opacity(0.55), radius: 24, x: 0, y: 8)
        .transition(.asymmetric(
            insertion: .scale(scale: 0.9).combined(with: .opacity),
            removal:   .scale(scale: 0.9).combined(with: .opacity)
        ))
    }

    // MARK: - Main pill
    var mainPill: some View {
        HStack(spacing: 10) {
            // Abort
            circleButton(icon: "xmark", bg: Color.white.opacity(0.08)) {
                Task { @MainActor in await AppState.shared.abortRecording() }
            }

            Spacer()

            // Center — screen label + dots/timer (tap to toggle)
            VStack(spacing: 4) {
                HStack(spacing: 5) {
                    Circle()
                        .fill(Theme.red)
                        .frame(width: 6, height: 6)
                        .modifier(RecBlinkModifier())
                    Text(currentScreenLabel)
                        .font(.system(size: 10.5, weight: .medium))
                        .foregroundColor(Theme.t2)
                }

                Group {
                    if showTimer { timerView } else { DotWaveView() }
                }
                .contentShape(Rectangle())
                .onTapGesture { withAnimation { showTimer.toggle() } }
            }

            Spacer()

            // Confirm stop — standalone button, no tap gesture competition
            circleButton(icon: "checkmark", bg: Theme.grn) {
                confirmStop()
            }
        }
        .padding(.horizontal, 14)
        .frame(width: 420, height: 66)
        .background(
            Capsule()
                .fill(Color(red: 10/255, green: 10/255, blue: 12/255, opacity: 0.94))
                .overlay(Capsule().stroke(Color.white.opacity(0.11), lineWidth: 1))
        )
        .shadow(color: .black.opacity(0.55), radius: 24, x: 0, y: 8)
    }

    // MARK: - Helpers
    func circleButton(icon: String, bg: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.white)
                .frame(width: 34, height: 34)
                .background(bg)
                .clipShape(Circle())
        }
        .buttonStyle(PlainButtonStyle())
    }

    var timerView: some View {
        HStack(spacing: 6) {
            Circle().fill(Theme.red).frame(width: 7, height: 7).modifier(RecBlinkModifier())
            Text(timeString(elapsed))
                .font(.system(size: 15).monospaced().weight(.semibold))
                .foregroundColor(Theme.t1)
        }
    }

    var currentScreenLabel: String {
        if let id = appState.selectedDisplayID,
           let d = displays.first(where: { $0.displayID == id }) {
            return labelFor(d)
        }
        if let d = displays.first { return labelFor(d) }
        if let s = NSScreen.main {
            return "\(s.localizedName)  \(Int(s.frame.width))×\(Int(s.frame.height))"
        }
        return "Main Display"
    }

    func labelFor(_ d: SCDisplay) -> String {
        let w = d.width, h = d.height
        if let s = NSScreen.screens.first(where: { Int($0.frame.width) == w && Int($0.frame.height) == h }) {
            return "\(s.localizedName)  \(w)×\(h)"
        }
        return "Display \(w)×\(h)"
    }

    func timeString(_ t: TimeInterval) -> String {
        String(format: "%02d:%02d", Int(t) / 60, Int(t) % 60)
    }

    func startTimer() {
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in elapsed += 1 }
    }

    func confirmStop() {
        timer?.invalidate()
        Task { @MainActor in
            await AppState.shared.stopAndUpload()
        }
    }
}

// MARK: - DotWaveView
struct DotWaveView: View {
    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<7, id: \.self) { i in
                DotView(delay: Double(i) * 0.13)
            }
        }
    }
}

struct DotView: View {
    let delay: Double
    @State private var scale: CGFloat = 0.74
    @State private var opacity: Double = 0.20

    var body: some View {
        Circle()
            .fill(Color.white)
            .frame(width: 5, height: 5)
            .scaleEffect(scale)
            .opacity(opacity)
            .onAppear {
                withAnimation(.easeInOut(duration: 1.5).repeatForever(autoreverses: true).delay(delay)) {
                    scale = 1.0; opacity = 0.86
                }
            }
    }
}

// MARK: - RecBlinkModifier
struct RecBlinkModifier: ViewModifier {
    @State private var opacity: Double = 1
    func body(content: Content) -> some View {
        content.opacity(opacity).onAppear {
            withAnimation(.easeInOut(duration: 1.3).repeatForever(autoreverses: true)) { opacity = 0.25 }
        }
    }
}
