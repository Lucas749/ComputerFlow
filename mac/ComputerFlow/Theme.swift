import SwiftUI
import AppKit

// MARK: - Color Hex Init
extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3:  (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6:  (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8:  (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default: (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(.sRGB, red: Double(r)/255, green: Double(g)/255, blue: Double(b)/255, opacity: Double(a)/255)
    }
}

// MARK: - Adaptive color helper
// Creates a Color that switches between dark/light values automatically.
private func adaptive(dark: String, light: String) -> Color {
    Color(NSColor(name: nil) { appearance in
        let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        let hex = isDark ? dark : light
        let h = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: h).scanHexInt64(&int)
        let r = CGFloat((int >> 16) & 0xFF) / 255
        let g = CGFloat((int >>  8) & 0xFF) / 255
        let b = CGFloat( int        & 0xFF) / 255
        return NSColor(calibratedRed: r, green: g, blue: b, alpha: 1)
    })
}

private func adaptiveAlpha(darkColor: NSColor, lightColor: NSColor) -> Color {
    Color(NSColor(name: nil) { appearance in
        appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? darkColor : lightColor
    })
}

// MARK: - Theme
// All colors adapt automatically when NSApp.appearance changes.
struct Theme {
    // Surfaces
    static let winBg = adaptive(dark: "#252527", light: "#f5f5f7")
    static let surf  = adaptive(dark: "#2e2e31", light: "#ebebee")
    static let ctrl  = adaptive(dark: "#363639", light: "#e1e1e5")
    static let hov   = adaptive(dark: "#3e3e42", light: "#d8d8dc")

    // Borders
    static let bdiv  = adaptiveAlpha(
        darkColor:  NSColor.white.withAlphaComponent(0.09),
        lightColor: NSColor.black.withAlphaComponent(0.12)
    )
    static let soft  = adaptiveAlpha(
        darkColor:  NSColor.white.withAlphaComponent(0.07),
        lightColor: NSColor.black.withAlphaComponent(0.08)
    )

    // Text
    static let t1 = adaptiveAlpha(
        darkColor:  NSColor.white.withAlphaComponent(0.92),
        lightColor: NSColor.black.withAlphaComponent(0.88)
    )
    static let t2 = adaptiveAlpha(
        darkColor:  NSColor.white.withAlphaComponent(0.52),
        lightColor: NSColor.black.withAlphaComponent(0.50)
    )
    static let t3 = adaptiveAlpha(
        darkColor:  NSColor.white.withAlphaComponent(0.28),
        lightColor: NSColor.black.withAlphaComponent(0.28)
    )

    // Pill (floating recording panel)
    static let pillBg = adaptiveAlpha(
        darkColor:  NSColor(calibratedRed: 10/255, green: 10/255, blue: 12/255, alpha: 0.94),
        lightColor: NSColor(calibratedRed: 245/255, green: 245/255, blue: 247/255, alpha: 0.96)
    )
    static let pillBorder = adaptiveAlpha(
        darkColor:  NSColor.white.withAlphaComponent(0.11),
        lightColor: NSColor.black.withAlphaComponent(0.12)
    )

    // Accents (slightly different hues between dark/light per design)
    static let blue = adaptive(dark: "#2997FF", light: "#007AFF")
    static let grn  = adaptive(dark: "#32D74B", light: "#34C759")
    static let red  = adaptive(dark: "#FF453A", light: "#FF3B30")
    static let amb  = adaptive(dark: "#FF9F0A", light: "#FF9500")

    // Typography
    static func mono(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .custom("SF Mono", size: size).weight(weight)
    }
}

struct WindowShadowModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .shadow(color: Color.black.opacity(0.6), radius: 28, x: 0, y: 20)
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.white.opacity(0.08), lineWidth: 1))
    }
}
