import SwiftUI
import AppKit

// MARK: - CompilingWindowController
class CompilingWindowController {
    private var window: NSWindow?
    var workflowId: String = ""
    private var streamTask: Task<Void, Never>?

    func show() {
        let view = CompilingView(workflowId: workflowId)
        let hosting = NSHostingView(rootView: view)
        hosting.frame = NSRect(x: 0, y: 0, width: 376, height: 220)

        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 376, height: 220),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        window.backgroundColor = .clear
        window.isOpaque = false
        window.hasShadow = true
        window.contentView = hosting
        window.center()
        window.level = .floating
        window.isReleasedWhenClosed = false
        window.orderFront(nil)
        self.window = window
    }

    func startStreaming() {
        streamTask?.cancel()
        streamTask = Task { @MainActor in
            for await event in BackendClient.shared.compileStream(workflowId: workflowId) {
                NotificationCenter.default.post(
                    name: .compileEventReceived,
                    object: nil,
                    userInfo: ["event": event]
                )
                if event.stage == 3 && event.progress >= 100 {
                    AppState.shared.compileComplete(workflowId: workflowId)
                    break
                }
            }
        }
    }

    func close() {
        streamTask?.cancel()
        window?.close()
        window = nil
    }
}

extension Notification.Name {
    static let compileEventReceived = Notification.Name("compileEventReceived")
}

// MARK: - CompilingView (Screen 3)
struct CompilingView: View {
    let workflowId: String

    @State private var stage: Int = 0
    @State private var progress: Double = 0
    @State private var sublineIndex: Int = 0
    @State private var shimmerOffset: CGFloat = -1
    @State private var spinRotation: Double = 0
    @State private var sublineTimer: Timer?

    let sublines = [
        "Parsing frames…",
        "Identifying UI elements…",
        "Writing agentic script…",
        "Optimising execution…"
    ]

    let stageDots = 4

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 14)
                .fill(Theme.winBg)

            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)

            VStack(spacing: 0) {
                Spacer()

                // Spinner
                spinnerView
                    .padding(.bottom, 16)

                // Title
                Text("Translating visual intent")
                    .font(.system(size: 15.5, weight: .semibold))
                    .foregroundColor(Theme.t1)
                    .padding(.bottom, 6)

                // Animated subline
                Text(sublines[min(sublineIndex, sublines.count - 1)])
                    .font(.system(size: 12))
                    .foregroundColor(Theme.t2)
                    .id(sublineIndex)
                    .transition(.asymmetric(
                        insertion: .opacity.combined(with: .move(edge: .bottom)),
                        removal: .opacity.combined(with: .move(edge: .top))
                    ))
                    .animation(.easeInOut(duration: 0.4), value: sublineIndex)
                    .padding(.bottom, 20)

                // Progress Bar
                progressBar
                    .padding(.horizontal, 28)
                    .padding(.bottom, 20)

                // Stage dots
                stageDotRow
                    .padding(.bottom, 0)

                Spacer()
            }
            .padding(.vertical, 20)
        }
        .frame(width: 376, height: 220)
        .shadow(color: .black.opacity(0.6), radius: 28, x: 0, y: 20)
        .onAppear {
            startAnimations()
            subscribeToEvents()
        }
        .onDisappear {
            sublineTimer?.invalidate()
        }
    }

    // MARK: - Spinner
    var spinnerView: some View {
        Circle()
            .trim(from: 0.15, to: 0.85)
            .stroke(
                AngularGradient(
                    gradient: Gradient(colors: [Theme.t3, Theme.t2]),
                    center: .center
                ),
                style: StrokeStyle(lineWidth: 2.5, lineCap: .round)
            )
            .frame(width: 28, height: 28)
            .rotationEffect(.degrees(spinRotation))
            .onAppear {
                withAnimation(.linear(duration: 0.88).repeatForever(autoreverses: false)) {
                    spinRotation = 360
                }
            }
    }

    // MARK: - Progress Bar
    var progressBar: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                // Track
                Capsule().fill(Theme.surf).frame(height: 2)

                // Fill with shimmer
                Capsule()
                    .fill(Color.white.opacity(0.52))
                    .frame(width: geo.size.width * (progress / 100), height: 2)
                    .overlay(
                        shimmerOverlay(width: geo.size.width)
                    )
                    .clipped()
            }
        }
        .frame(height: 2)
    }

    func shimmerOverlay(width: CGFloat) -> some View {
        Rectangle()
            .fill(
                LinearGradient(
                    gradient: Gradient(stops: [
                        .init(color: .clear, location: 0),
                        .init(color: Color.white.opacity(0.45), location: 0.5),
                        .init(color: .clear, location: 1)
                    ]),
                    startPoint: .leading,
                    endPoint: .trailing
                )
            )
            .frame(width: 60)
            .offset(x: shimmerOffset * width)
            .onAppear {
                withAnimation(.linear(duration: 1.5).repeatForever(autoreverses: false)) {
                    shimmerOffset = 1.2
                }
            }
    }

    // MARK: - Stage Dots
    var stageDotRow: some View {
        HStack(spacing: 6) {
            ForEach(0..<stageDots, id: \.self) { i in
                Capsule()
                    .fill(i <= stage ? Theme.t1 : Theme.t3)
                    .frame(width: i == stage ? 20 : 12, height: 4)
                    .animation(.spring(response: 0.3), value: stage)
            }
        }
    }

    // MARK: - Animations
    func startAnimations() {
        sublineTimer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { _ in
            withAnimation(.easeInOut(duration: 0.4)) {
                sublineIndex = (sublineIndex + 1) % sublines.count
            }
        }

        // Simulate progress if no SSE (fallback)
        Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { t in
            if progress < 85 {
                progress = min(85, progress + Double.random(in: 0.5...2))
            } else {
                t.invalidate()
            }
        }
    }

    func subscribeToEvents() {
        NotificationCenter.default.addObserver(
            forName: .compileEventReceived,
            object: nil,
            queue: .main
        ) { notification in
            if let event = notification.userInfo?["event"] as? CompileEvent {
                withAnimation(.easeInOut(duration: 0.5)) {
                    stage = event.stage
                    progress = event.progress
                }
                if let idx = sublines.firstIndex(of: event.subline) {
                    withAnimation { sublineIndex = idx }
                }
            }
        }
    }
}
