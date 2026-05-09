import SwiftUI
import AppKit

// MARK: - WorkflowScreenshotView
// Loads a per-step screenshot using the workflow id + relative path
// (e.g. "screenshots/ev_0003.jpg") from the backend. Cached in memory.
struct WorkflowScreenshotView<Placeholder: View>: View {
    let workflowId: String
    let screenshotRel: String?
    let placeholder: () -> Placeholder

    @State private var image: NSImage?

    init(workflowId: String, screenshotRel: String?, @ViewBuilder placeholder: @escaping () -> Placeholder) {
        self.workflowId = workflowId
        self.screenshotRel = screenshotRel
        self.placeholder = placeholder
    }

    var body: some View {
        Group {
            if let img = image {
                Image(nsImage: img)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .background(Color.black)
            } else {
                placeholder()
            }
        }
        .task(id: cacheKey) { await load() }
    }

    var cacheKey: String { "\(workflowId)/\(screenshotRel ?? "")" }

    @MainActor
    private func load() async {
        guard let rel = screenshotRel, !rel.isEmpty else { image = nil; return }
        let filename = URL(fileURLWithPath: rel).lastPathComponent
        let key = "\(workflowId)/\(filename)"

        if let cached = ScreenshotCache.shared.get(key) {
            image = cached
            return
        }
        if let img = await ScreenshotCache.shared.fetch(workflowId: workflowId, filename: filename) {
            image = img
        }
    }
}

// MARK: - ScreenshotCache
actor ScreenshotCacheStore {
    private var cache: [String: NSImage] = [:]
    func get(_ key: String) -> NSImage? { cache[key] }
    func set(_ key: String, _ img: NSImage) { cache[key] = img }
}

final class ScreenshotCache {
    static let shared = ScreenshotCache()
    private var cache: [String: NSImage] = [:]
    private let queue = DispatchQueue(label: "computerflow.screenshot-cache")

    func get(_ key: String) -> NSImage? {
        queue.sync { cache[key] }
    }

    func set(_ key: String, _ img: NSImage) {
        queue.sync { cache[key] = img }
    }

    /// Fetch from backend; on success store in cache.
    func fetch(workflowId: String, filename: String) async -> NSImage? {
        let key = "\(workflowId)/\(filename)"
        if let cached = get(key) { return cached }

        let baseURL = BackendClient.shared.baseURL
        let url = baseURL.appendingPathComponent("workflows/\(workflowId)/screenshot/\(filename)")
        do {
            let (data, response) = try await URLSession.shared.data(from: url)
            guard (response as? HTTPURLResponse)?.statusCode == 200,
                  let img = NSImage(data: data) else { return nil }
            set(key, img)
            return img
        } catch {
            return nil
        }
    }
}
