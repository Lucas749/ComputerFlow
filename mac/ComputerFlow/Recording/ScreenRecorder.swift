import ScreenCaptureKit
import AVFoundation
import Foundation

// MARK: - ScreenRecorder
class ScreenRecorder: NSObject, ObservableObject {
    private var stream: SCStream?
    private let encoder = VideoEncoder()

    private(set) var outputURL: URL?

    // Which display to record — nil means "first available"
    var selectedDisplayID: CGDirectDisplayID?

    // Set by AppState before calling startRecording so the video lands in the same
    // tmp folder as events.json and screenshots.
    var recordingRootDir: URL?

    func startRecording() async throws {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let rootDir: URL
        if let dir = recordingRootDir {
            rootDir = dir
        } else {
            let tmpDir = appSupport.appendingPathComponent("ComputerFlow/tmp", isDirectory: true)
            try FileManager.default.createDirectory(at: tmpDir, withIntermediateDirectories: true)
            rootDir = tmpDir
        }
        let url = rootDir.appendingPathComponent("recording.mp4")
        outputURL = url

        let availableContent = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)

        let display: SCDisplay
        if let id = selectedDisplayID,
           let match = availableContent.displays.first(where: { $0.displayID == id }) {
            display = match
        } else if let first = availableContent.displays.first {
            display = first
        } else {
            throw RecorderError.noDisplay
        }

        let w = display.width
        let h = display.height

        let config = SCStreamConfiguration()
        config.minimumFrameInterval = CMTime(value: 1, timescale: 10)
        config.width  = w
        config.height = h

        try encoder.setup(outputURL: url, width: w, height: h)

        let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])
        stream = SCStream(filter: filter, configuration: config, delegate: self)
        try stream?.addStreamOutput(self, type: .screen, sampleHandlerQueue: DispatchQueue.global(qos: .userInteractive))
        try await stream?.startCapture()
    }

    func stopRecording() async throws -> URL {
        try await stream?.stopCapture()
        stream = nil
        guard let url = outputURL else { throw RecorderError.noOutput }
        try await encoder.finishWriting()
        return url
    }

    // Fetch all available displays (call before showing picker)
    static func availableDisplays() async -> [SCDisplay] {
        guard let content = try? await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true) else { return [] }
        return content.displays
    }
}

// MARK: - SCStreamDelegate
extension ScreenRecorder: SCStreamDelegate {
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        print("SCStream stopped: \(error)")
    }
}

// MARK: - SCStreamOutput
extension ScreenRecorder: SCStreamOutput {
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen else { return }
        encoder.encode(sampleBuffer)
    }
}

// MARK: - RecorderError
enum RecorderError: Error, LocalizedError {
    case noDisplay
    case noOutput

    var errorDescription: String? {
        switch self {
        case .noDisplay: return "No display available for capture"
        case .noOutput:  return "No output URL available"
        }
    }
}
