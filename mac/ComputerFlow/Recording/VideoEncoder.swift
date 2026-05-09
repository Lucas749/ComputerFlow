import AVFoundation
import Foundation

// MARK: - VideoEncoder
class VideoEncoder {
    private var assetWriter: AVAssetWriter?
    private var videoInput: AVAssetWriterInput?
    private var sessionStarted = false

    func setup(outputURL: URL) throws {
        // Remove existing file
        try? FileManager.default.removeItem(at: outputURL)

        assetWriter = try AVAssetWriter(outputURL: outputURL, fileType: .mp4)

        let settings: [String: Any] = [
            AVVideoCodecKey: AVVideoCodecType.h264,
            AVVideoWidthKey: 1920,
            AVVideoHeightKey: 1080,
            AVVideoCompressionPropertiesKey: [
                AVVideoAverageBitRateKey: 4_000_000
            ]
        ]

        videoInput = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
        videoInput?.expectsMediaDataInRealTime = true

        if let input = videoInput {
            assetWriter?.add(input)
        }

        assetWriter?.startWriting()
    }

    func encode(_ sampleBuffer: CMSampleBuffer) {
        guard let writer = assetWriter, writer.status == .writing,
              let input = videoInput, input.isReadyForMoreMediaData else { return }

        if !sessionStarted {
            let pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
            writer.startSession(atSourceTime: pts)
            sessionStarted = true
        }

        input.append(sampleBuffer)
    }

    func finishWriting() async throws {
        guard let writer = assetWriter else { return }
        videoInput?.markAsFinished()
        await withCheckedContinuation { continuation in
            writer.finishWriting {
                continuation.resume()
            }
        }
        if writer.status == .failed {
            throw writer.error ?? VideoEncoderError.writeFailed
        }
    }
}

// MARK: - VideoEncoderError
enum VideoEncoderError: Error {
    case writeFailed
}
