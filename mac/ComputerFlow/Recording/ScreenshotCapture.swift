import AppKit
import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

// MARK: - ScreenshotCapture
enum ScreenshotCapture {

    @discardableResult
    static func captureJPEG(to url: URL, displayID: CGDirectDisplayID? = nil, quality: CGFloat = 0.85) -> CGSize? {
        // Determine the bounds of the target display so we only capture that screen.
        // CGWindowListCreateImage with a specific rect crops to that display.
        let bounds: CGRect
        if let id = displayID {
            bounds = CGDisplayBounds(id)
        } else if let screen = NSScreen.main {
            // Convert NSScreen frame (bottom-left origin) to CG coordinates (top-left origin).
            let screenHeight = NSScreen.screens.map { $0.frame.maxY }.max() ?? screen.frame.maxY
            bounds = CGRect(
                x: screen.frame.minX,
                y: screenHeight - screen.frame.maxY,
                width: screen.frame.width,
                height: screen.frame.height
            )
        } else {
            bounds = .null
        }

        let image = CGWindowListCreateImage(
            bounds,
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
