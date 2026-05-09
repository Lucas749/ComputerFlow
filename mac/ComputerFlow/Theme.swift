import SwiftUI

// MARK: - Color Hex Init
extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3:
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6:
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8:
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}

// MARK: - Theme
struct Theme {
    // Dark mode surfaces
    static let winBg  = Color(hex: "#252527")
    static let surf   = Color(hex: "#2e2e31")
    static let ctrl   = Color(hex: "#363639")
    static let hov    = Color(hex: "#3e3e42")
    static let bdiv   = Color.white.opacity(0.09)
    static let soft   = Color.white.opacity(0.07)

    // Text
    static let t1     = Color.white.opacity(0.92)
    static let t2     = Color.white.opacity(0.52)
    static let t3     = Color.white.opacity(0.28)

    // Accent
    static let blue   = Color(hex: "#2997FF")
    static let grn    = Color(hex: "#32D74B")
    static let red    = Color(hex: "#FF453A")
    static let amb    = Color(hex: "#FF9F0A")

    // Desktop background
    static let deskBg = Color(hex: "#0a0a0e")

    // Typography helpers
    static func mono(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .custom("SF Mono", size: size).weight(weight)
    }

    // Consistent window shadow
    static func windowShadow() -> some ViewModifier {
        WindowShadowModifier()
    }
}

struct WindowShadowModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .shadow(color: Color.black.opacity(0.6), radius: 28, x: 0, y: 20)
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .stroke(Color.white.opacity(0.08), lineWidth: 1)
            )
    }
}
