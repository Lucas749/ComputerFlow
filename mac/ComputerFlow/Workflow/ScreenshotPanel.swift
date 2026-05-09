import SwiftUI

// MARK: - ScreenshotPanel
// Used inside WorkflowEditor to display step screenshots or gradient placeholders
struct ScreenshotPanel: View {
    let step: WorkflowStep

    var body: some View {
        ZStack {
            // Gradient background placeholder
            RoundedRectangle(cornerRadius: 10)
                .fill(backgroundGradient)

            // Chrome bar at top
            VStack(spacing: 0) {
                chromeBar
                Spacer()
                stepPreview
                    .padding()
            }
        }
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Theme.bdiv, lineWidth: 1)
        )
    }

    // MARK: - Chrome Bar
    var chromeBar: some View {
        HStack(spacing: 6) {
            // Traffic lights
            ForEach([Theme.red, Theme.amb, Theme.grn], id: \.self) { color in
                Circle().fill(color).frame(width: 10, height: 10)
            }
            Spacer()
            if let url = step.target.url {
                Text(truncatedURL(url))
                    .font(Theme.mono(10))
                    .foregroundColor(Theme.t3)
                    .lineLimit(1)
            }
            Spacer()
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(Color.black.opacity(0.35))
    }

    // MARK: - Step preview content
    @ViewBuilder
    var stepPreview: some View {
        VStack(spacing: 8) {
            Image(systemName: actionIcon)
                .font(.system(size: 24))
                .foregroundColor(Color.white.opacity(0.3))
            Text(step.actionLabel)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(Color.white.opacity(0.4))
            let display = step.value?.displayString ?? step.target.displayString
            if !display.isEmpty {
                Text(display)
                    .font(Theme.mono(11))
                    .foregroundColor(Color.white.opacity(0.25))
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
            }
        }
    }

    var backgroundGradient: LinearGradient {
        let pairs: [(Color, Color)] = [
            (Color(hex: "#0d1117"), Color(hex: "#161b22")),
            (Color(hex: "#0a0a1a"), Color(hex: "#1a1a2e")),
            (Color(hex: "#0d1117"), Color(hex: "#0f3460")),
            (Color(hex: "#1a1a2e"), Color(hex: "#16213e")),
            (Color(hex: "#0a0a0e"), Color(hex: "#1b1b2f"))
        ]
        let pair = pairs[step.n % pairs.count]
        return LinearGradient(colors: [pair.0, pair.1], startPoint: .topLeading, endPoint: .bottomTrailing)
    }

    var actionIcon: String {
        switch step.action {
        case "navigate":             return "globe"
        case "click", "double_click": return "cursorarrow.click"
        case "right_click":          return "cursorarrow.click.2"
        case "type":                 return "keyboard"
        case "hotkey", "press_key":  return "command"
        case "scroll", "hscroll":    return "arrow.up.and.down"
        case "wait":                 return "clock"
        case "extract":              return "doc.text.magnifyingglass"
        default:                     return "checkmark.circle"
        }
    }

    func truncatedURL(_ url: String) -> String {
        let maxLen = 40
        if url.count <= maxLen { return url }
        return "..." + url.suffix(maxLen - 3)
    }
}
