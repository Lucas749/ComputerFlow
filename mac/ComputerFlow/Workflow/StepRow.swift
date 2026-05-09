import SwiftUI

// MARK: - StepRow (used in WorkflowConfirmation)
struct StepRow: View {
    let step: WorkflowStep
    var showThumbnail: Bool = false

    var body: some View {
        HStack(spacing: 10) {
            // Number circle
            ZStack {
                Circle()
                    .fill(Theme.surf)
                    .overlay(Circle().stroke(Theme.bdiv, lineWidth: 1))
                    .frame(width: 24, height: 24)
                Text("\(step.n)")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(Theme.t2)
            }

            // Action label
            Text(step.actionLabel)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(Theme.t2)
                .frame(width: 60, alignment: .leading)
                .lineLimit(1)

            // Value chip
            if let value = step.value {
                valueChip(value)
            } else {
                Text(step.target.displayString)
                    .font(Theme.mono(11))
                    .foregroundColor(Theme.t1)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(Theme.surf)
                    .cornerRadius(5)
                    .lineLimit(1)
            }

            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 7)
    }

    @ViewBuilder
    func valueChip(_ value: StepValue) -> some View {
        Text(value.displayString)
            .font(Theme.mono(11))
            .foregroundColor(value.isVariable ? Theme.blue : Theme.t1)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(value.isVariable ? Theme.blue.opacity(0.12) : Theme.surf)
            .cornerRadius(5)
            .lineLimit(1)
    }
}

// MARK: - StepRowWithThumbnail (used in Editor)
struct StepRowWithThumbnail: View {
    let step: WorkflowStep
    var isSelected: Bool = false
    var onTap: (() -> Void)? = nil

    var body: some View {
        HStack(spacing: 10) {
            // Thumbnail placeholder
            RoundedRectangle(cornerRadius: 4)
                .fill(thumbnailGradient)
                .frame(width: 44, height: 30)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Theme.bdiv, lineWidth: 1)
                )

            VStack(alignment: .leading, spacing: 2) {
                Text(step.actionLabel)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(Theme.t1)
                    .lineLimit(1)

                let display = step.value?.displayString ?? step.target.displayString
                Text(display)
                    .font(Theme.mono(10))
                    .foregroundColor(Theme.t2)
                    .lineLimit(1)
            }

            Spacer()

            statusDot
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(isSelected ? Theme.surf.opacity(0.8) : Color.clear)
        .overlay(
            RoundedRectangle(cornerRadius: 7)
                .stroke(isSelected ? Theme.bdiv : Color.clear, lineWidth: 1)
        )
        .cornerRadius(7)
        .contentShape(Rectangle())
        .onTapGesture { onTap?() }
    }

    var thumbnailGradient: LinearGradient {
        let colors: [[Color]] = [
            [Color(hex: "#1a1a2e"), Color(hex: "#16213e")],
            [Color(hex: "#0f3460"), Color(hex: "#533483")],
            [Color(hex: "#1b1b2f"), Color(hex: "#2b2d42")],
            [Color(hex: "#16213e"), Color(hex: "#0f3460")],
            [Color(hex: "#1a1a2e"), Color(hex: "#533483")]
        ]
        let pair = colors[step.n % colors.count]
        return LinearGradient(colors: pair, startPoint: .topLeading, endPoint: .bottomTrailing)
    }

    @ViewBuilder
    var statusDot: some View {
        if step.needsReview {
            Circle().fill(Theme.amb).frame(width: 7, height: 7)
        } else if step.approved {
            Circle().fill(Theme.grn).frame(width: 7, height: 7)
        } else {
            Circle().stroke(Theme.t3, lineWidth: 1).frame(width: 7, height: 7)
        }
    }
}
