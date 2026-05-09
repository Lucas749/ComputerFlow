import Carbon
import AppKit

// MARK: - HotkeyManager
class HotkeyManager {
    static let shared = HotkeyManager()

    private var hotKeyRef: EventHotKeyRef?
    private var eventHandler: EventHandlerRef?

    var onHotKeyPressed: (() -> Void)?

    private init() {}

    func register() {
        // Build the hotkey ID
        var hotKeyID = EventHotKeyID()
        hotKeyID.signature = fourCharCode("CFRK")
        hotKeyID.id = 1

        // Register ⌘⇧R
        let status = RegisterEventHotKey(
            UInt32(kVK_ANSI_R),
            UInt32(cmdKey | shiftKey),
            hotKeyID,
            GetApplicationEventTarget(),
            0,
            &hotKeyRef
        )

        if status != noErr {
            print("HotkeyManager: Failed to register hotkey, status=\(status)")
            return
        }

        // Install Carbon event handler
        // Note: InstallApplicationEventHandler is a macro → use InstallEventHandler directly
        var eventType = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(
            GetApplicationEventTarget(),
            { (_, _, userData) -> OSStatus in
                guard let userData = userData else { return noErr }
                let manager = Unmanaged<HotkeyManager>.fromOpaque(userData).takeUnretainedValue()
                DispatchQueue.main.async { manager.onHotKeyPressed?() }
                return noErr
            },
            1,
            &eventType,
            Unmanaged.passUnretained(self).toOpaque(),
            &eventHandler
        )
    }

    func unregister() {
        if let ref = hotKeyRef {
            UnregisterEventHotKey(ref)
            hotKeyRef = nil
        }
    }
}

// MARK: - Helpers
private func fourCharCode(_ string: String) -> FourCharCode {
    var result: FourCharCode = 0
    for char in string.unicodeScalars.prefix(4) {
        result = result << 8 + FourCharCode(char.value)
    }
    return result
}
