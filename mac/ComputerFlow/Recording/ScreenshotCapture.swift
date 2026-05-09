import AppKit
import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

// MARK: - ScreenshotCapture
// Synchronous CGImage grab of the main display, JPEG-encoded to disk.
// Used by EventTelemetry to snapshot BEFORE each click / keystroke.
enum ScreenshotCapture {

    /// Capture the main display as JPEG and write it to `url`. Returns the
    /// pixel size of the captured image (useful for downstream coordinate
    /// normalisation).  Thread-safe — call from any queue.
    @discardableResult
    static func captureJPEG(to url: URL, quality: CGFloat = 0.72) -> CGSize? {
        let displayID = CGMainDisplayID()
        guard let image = CGDisplayCreateImage(displayID) else { return nil }

        let size = CGSize(width: image.width, height: image.height)

        guard let dest = CGImageDestinationCreateWithURL(
            url as CFURL,
            UTType.jpeg.identifier as CFString,
            1,
            nil
        ) else { return nil }

        let options: [CFString: Any] = [
            kCGImageDestinationLossyCompressionQuality: quality
        ]
        CGImageDestinationAddImage(dest, image, options as CFDictionary)
        guard CGImageDestinationFinalize(dest) else { return nil }

        return size
    }
}
