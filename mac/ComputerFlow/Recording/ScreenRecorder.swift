import ScreenCaptureKit
import AVFoundation
import Foundation

// MARK: - ScreenRecorder
class ScreenRecorder: NSObject, ObservableObject {
    private var stream: SCStream?
    private let encoder = VideoEncoder()

    private(set) var outputURL: URL?

    func startRecording() async throws {
        // Generate output URL
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let tmpDir = appSupport.appendingPathComponent("ComputerFlow/tmp", isDirectory: true)
        try FileManager.default.createDirectory(at: tmpDir, withIntermediateDirectories: true)
        let url = tmpDir.appendingPathComponent("\(UUID().uuidString).mp4")
        outputURL = url

        try encoder.setup(outputURL: url)

        let config = SCStreamConfiguration()
        config.minimumFrameInterval = CMTime(value: 1, timescale: 10) // 10 fps
        config.width = 1920
        config.height = 1080

        // Get available content
        let availableContent = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        guard let display = availableContent.displays.first else {
            throw RecorderError.noDisplay
        }

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
        case .noOutput: return "No output URL available"
        }
    }
}
