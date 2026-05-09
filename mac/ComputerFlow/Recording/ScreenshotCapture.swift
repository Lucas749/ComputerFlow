import AppKit
import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

// MARK: - ScreenshotCapture
enum ScreenshotCapture {

    @discardableResult
    static func captureJPEG(to url: URL, displayID: CGDirectDisplayID? = nil, quality: CGFloat = 0.85) -> CGSize? {
        // Prefer CGDisplayCreateImage — much more reliable than CGWindowListCreateImage
        // which fails intermittently during fast event streams (keystrokes, modifiers).
        let targetID: CGDirectDisplayID = displayID ?? CGMainDisplayID()
        var image: CGImage? = CGDisplayCreateImage(targetID)

        // Fallback to CGWindowListCreateImage if display capture returns nil
        if image == nil {
            let bounds = CGDisplayBounds(targetID)
            image = CGWindowListCreateImage(
                bounds,
                .optionOnScreenOnly,
                kCGNullWindowID,
                [.bestResolution, .boundsIgnoreFraming]
            )
        }

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
