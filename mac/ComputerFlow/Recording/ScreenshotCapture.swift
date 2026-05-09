import AppKit
import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

// MARK: - ScreenshotCapture
enum ScreenshotCapture {

    @discardableResult
    static func captureJPEG(to url: URL, quality: CGFloat = 0.85) -> CGSize? {
        // CGWindowListCreateImage works correctly on macOS 14+ with Screen Recording permission.
        // CGDisplayCreateImage is deprecated and returns black on recent macOS.
        let image = CGWindowListCreateImage(
            .null,                          // .null = full screen bounds
            .optionOnScreenOnly,
            kCGNullWindowID,
            [.bestResolution, .boundsIgnoreFraming]
        )

        guard let image else { return nil }

        let size = CGSize(width: image.width, height: image.height)

        guard let dest = CGImageDestinationCreateWithURL(
            url as CFURL,
            UTType.jpeg.identifier as CFString,
            1, nil
        ) else { return nil }

        CGImageDestinationAddImage(dest, image, [
            kCGImageDestinationLossyCompressionQuality: quality
        ] as CFDictionary)

        guard CGImageDestinationFinalize(dest) else { return nil }
        return size
    }
}
