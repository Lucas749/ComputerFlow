import SwiftUI

// MARK: - DisplaySelectorView
struct DisplaySelectorView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "display")
                .font(.system(size: 11))
                .foregroundColor(Theme.t3)

            if appState.availableDisplays.isEmpty {
                Text("No displays")
                    .font(.system(size: 12))
                    .foregroundColor(Theme.t3)
            } else {
                Button(action: { step(by: -1) }) {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(Theme.t3)
                        .frame(width: 22, height: 22)
                        .background(Theme.ctrl)
                        .cornerRadius(5)
                        .overlay(RoundedRectangle(cornerRadius: 5).stroke(Theme.bdiv, lineWidth: 1))
                }
                .buttonStyle(PlainButtonStyle())

                Text(currentLabel)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(Theme.t2)
                    .frame(minWidth: 120)
                    .multilineTextAlignment(.center)

                Button(action: { step(by: 1) }) {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(Theme.t3)
                        .frame(width: 22, height: 22)
                        .background(Theme.ctrl)
                        .cornerRadius(5)
                        .overlay(RoundedRectangle(cornerRadius: 5).stroke(Theme.bdiv, lineWidth: 1))
                }
                .buttonStyle(PlainButtonStyle())
            }

            Spacer()
        }
        .onAppear {
            guard appState.availableDisplays.isEmpty else { return }
            Task { await appState.loadDisplays() }
        }
    }

    var currentLabel: String {
        guard !appState.availableDisplays.isEmpty else { return "—" }
        let id = appState.selectedDisplayID
        return appState.availableDisplays.first(where: { $0.id == id })?.label
            ?? appState.availableDisplays[0].label
    }

    func step(by delta: Int) {
        let displays = appState.availableDisplays
        guard !displays.isEmpty else { return }
        let cur = displays.firstIndex(where: { $0.id == appState.selectedDisplayID }) ?? 0
        let next = (cur + delta + displays.count) % displays.count
        appState.selectedDisplayID = displays[next].id
    }
}
