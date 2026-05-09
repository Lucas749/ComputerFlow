import AppKit
import Foundation

// MARK: - EventTelemetry
// Captures every click and keystroke globally.  BEFORE each event the
// current screen is captured to a JPEG so the compiler has lossless,
// precisely-timed reference frames instead of approximate video frames.
//
// Output layout (per recording, rooted under Application Support/ComputerFlow/tmp/{uuid}/):
//   events.json
//   screenshots/
//     ev_0000.jpg        ← snapshot taken ~0 ms BEFORE event 0
//     ev_0001.jpg
//     …
//
// events.json entry shape:
//   { "i": 0, "t": 1715253720123.4, "kind": "click"|"key"|"keymod",
//     "x": 512, "y": 330,            (click only, in screen points)
//     "key": "a", "keyCode": 0, "modifiers": 1048840,
//     "screenshot": "screenshots/ev_0000.jpg",
//     "screenW": 1920, "screenH": 1080 }
class EventTelemetry: ObservableObject {

    private(set) var events: [[String: Any]] = []
    private var mouseMonitor: Any?
    private var keyMonitor: Any?
    private var flagMonitor: Any?

    private(set) var rootDir: URL?
    private(set) var screenshotsDir: URL?
    private var captureDisplayID: CGDirectDisplayID?
    private var lastKeyTimestamp: TimeInterval = 0
    private var burstScreenshotPath: String = ""
    private var lastSuccessfulPath: String = ""   // fallback if capture fails
    private static let keyBurstThresholdMs: TimeInterval = 600  // ms between keystrokes to count as same word

    private let captureQueue = DispatchQueue(
        label: "computerflow.screenshot-capture",
        qos: .userInitiated
    )

    // MARK: - Lifecycle

    /// Begin capturing.  Creates a fresh directory under `Application Support`
    /// keyed by the given recordingID so every recording is isolated.
    func start(recordingID: String, displayID: CGDirectDisplayID? = nil) throws {
        events = []
        captureDisplayID = displayID
        lastKeyTimestamp = 0
        burstScreenshotPath = ""
        lastSuccessfulPath = ""

        let appSupport = FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let root = appSupport
            .appendingPathComponent("ComputerFlow/tmp/\(recordingID)", isDirectory: true)
        let shots = root.appendingPathComponent("screenshots", isDirectory: true)
        try FileManager.default.createDirectory(at: shots, withIntermediateDirectories: true)
        rootDir = root
        screenshotsDir = shots

        mouseMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] event in
            self?.handleMouse(event)
        }
        keyMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.keyDown]) { [weak self] event in
            self?.handleKey(event)
        }
        // Capture modifier-only chords (⌘⇧, ⌘⌥…) too
        flagMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.flagsChanged]) { [weak self] event in
            self?.handleFlags(event)
        }
    }

    func stop() {
        [mouseMonitor, keyMonitor, flagMonitor].forEach { m in
            if let m = m { NSEvent.removeMonitor(m) }
        }
        mouseMonitor = nil; keyMonitor = nil; flagMonitor = nil
    }

    // MARK: - Persistence

    /// Write `events.json` to the recording's root directory.
    /// Returns the events.json URL.
    func saveEventsJSON() throws -> URL {
        guard let root = rootDir else {
            throw NSError(domain: "EventTelemetry", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "start() was not called"])
        }
        let url = root.appendingPathComponent("events.json")
        let data = try JSONSerialization.data(withJSONObject: events, options: .prettyPrinted)
        try data.write(to: url)
        return url
    }

    // MARK: - Handlers (run on the event-monitor queue, typically main)

    private func handleMouse(_ event: NSEvent) {
        let idx = events.count
        let screenshotRelPath = captureBefore(index: idx)

        let mouseLoc = NSEvent.mouseLocation   // screen-space (bottom-left origin)
        let screen = NSScreen.main?.frame ?? .zero
        // Convert to top-left-origin screen pixels for consistency with CGImage.
        let y = screen.height - mouseLoc.y

        let entry: [String: Any] = [
            "i": idx,
            "t": Date().timeIntervalSince1970 * 1000,
            "kind": event.type == .leftMouseDown ? "click" : "right_click",
            "x": mouseLoc.x,
            "y": y,
            "screenshot": screenshotRelPath,
            "screenW": screen.width,
            "screenH": screen.height
        ]
        events.append(entry)
    }

    private func handleKey(_ event: NSEvent) {
        let idx = events.count
        let now = Date().timeIntervalSince1970 * 1000

        // Only capture a new screenshot if this key starts a fresh burst
        let inBurst = (now - lastKeyTimestamp) < EventTelemetry.keyBurstThresholdMs
        let screenshotRelPath: String
        if inBurst {
            screenshotRelPath = burstScreenshotPath  // reuse first-key screenshot
        } else {
            screenshotRelPath = captureBefore(index: idx)
            burstScreenshotPath = screenshotRelPath
        }
        lastKeyTimestamp = now

        let entry: [String: Any] = [
            "i": idx,
            "t": now,
            "kind": "key",
            "key": event.charactersIgnoringModifiers ?? "",
            "keyCode": event.keyCode,
            "modifiers": event.modifierFlags.rawValue,
            "screenshot": screenshotRelPath
        ]
        events.append(entry)
    }

    private func handleFlags(_ event: NSEvent) {
        // Only capture on modifier-press (not release) to avoid duplicates
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        guard !flags.isEmpty else { return }

        let idx = events.count
        let screenshotRelPath = captureBefore(index: idx)
        let entry: [String: Any] = [
            "i": idx,
            "t": Date().timeIntervalSince1970 * 1000,
            "kind": "keymod",
            "modifiers": flags.rawValue,
            "screenshot": screenshotRelPath
        ]
        events.append(entry)
    }

    // MARK: - Screenshot

    /// Capture synchronously so the screenshot reflects the state BEFORE the
    /// action actually lands on the UI. The global NSEvent monitor fires
    /// *before* the target app receives the event, so a sync grab here is
    /// the closest we get to pre-action state.
    private func captureBefore(index: Int) -> String {
        guard let dir = screenshotsDir else { return "" }
        let name = String(format: "ev_%04d.jpg", index)
        let url = dir.appendingPathComponent(name)
        let ok = ScreenshotCapture.captureJPEG(to: url, displayID: captureDisplayID) != nil
               && FileManager.default.fileExists(atPath: url.path)
        if ok {
            lastSuccessfulPath = "screenshots/\(name)"
            return "screenshots/\(name)"
        }
        // Capture failed (can happen mid-keystroke) — fall back to last good path
        return lastSuccessfulPath.isEmpty ? "screenshots/\(name)" : lastSuccessfulPath
    }
}
