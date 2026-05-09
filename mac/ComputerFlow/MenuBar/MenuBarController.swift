import AppKit
import SwiftUI

// MenuBarController is kept minimal — the MenuBarExtra in the App struct
// handles the menu bar button. This controller can be used for imperative
// updates (icon badge, tooltip, etc.) if needed in the future.
class MenuBarController {
    static let shared = MenuBarController()
    private init() {}
}
