import Foundation
import Combine

// MARK: - WorkflowStore
class WorkflowStore: ObservableObject {
    static let shared = WorkflowStore()

    @Published var recentWorkflows: [WorkflowModel] = []

    private let fileURL: URL = {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let dir = appSupport.appendingPathComponent("ComputerFlow", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("workflows.json")
    }()

    private init() {
        load()
    }

    func load() {
        guard let data = try? Data(contentsOf: fileURL) else { return }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        if let workflows = try? decoder.decode([WorkflowModel].self, from: data) {
            recentWorkflows = workflows
        }
    }

    func save() {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        if let data = try? encoder.encode(recentWorkflows) {
            try? data.write(to: fileURL)
        }
    }

    func addOrUpdate(_ workflow: WorkflowModel) {
        DispatchQueue.main.async {
            if let idx = self.recentWorkflows.firstIndex(where: { $0.id == workflow.id }) {
                self.recentWorkflows[idx] = workflow
            } else {
                self.recentWorkflows.insert(workflow, at: 0)
                if self.recentWorkflows.count > 20 {
                    self.recentWorkflows = Array(self.recentWorkflows.prefix(20))
                }
            }
            self.save()
        }
    }

    func remove(id: String) {
        recentWorkflows.removeAll { $0.id == id }
        save()
    }
}
