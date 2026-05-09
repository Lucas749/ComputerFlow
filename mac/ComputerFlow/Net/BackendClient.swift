import Foundation

// MARK: - BackendClient
class BackendClient {
    static let shared = BackendClient()

    var baseURL: URL {
        let stored = UserDefaults.standard.string(forKey: "backendBaseURL") ?? "http://localhost:8000"
        return URL(string: stored)!
    }

    private init() {}

    // MARK: - Upload Recording
    func uploadRecording(
        videoURL: URL,
        eventsURL: URL,
        screenshotsDir: URL? = nil
    ) async throws -> String {
        let url = baseURL.appendingPathComponent("workflows/upload")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        let boundary = "Boundary-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()

        // Video part
        let videoData = try Data(contentsOf: videoURL)
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"video\"; filename=\"recording.mp4\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: video/mp4\r\n\r\n".data(using: .utf8)!)
        body.append(videoData)
        body.append("\r\n".data(using: .utf8)!)

        // Events part
        let eventsData = try Data(contentsOf: eventsURL)
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"events\"; filename=\"events.json\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: application/json\r\n\r\n".data(using: .utf8)!)
        body.append(eventsData)
        body.append("\r\n".data(using: .utf8)!)

        // Each event-screenshot as its own part.  The backend indexes them by
        // filename (ev_XXXX.jpg) and matches each to events.json entries.
        if let shotDir = screenshotsDir,
           let items = try? FileManager.default.contentsOfDirectory(
               at: shotDir, includingPropertiesForKeys: nil) {
            for file in items.sorted(by: { $0.lastPathComponent < $1.lastPathComponent })
                where file.pathExtension.lowercased() == "jpg" {
                guard let data = try? Data(contentsOf: file) else { continue }
                let name = file.lastPathComponent
                body.append("--\(boundary)\r\n".data(using: .utf8)!)
                body.append(
                    "Content-Disposition: form-data; name=\"screenshots\"; filename=\"\(name)\"\r\n"
                        .data(using: .utf8)!)
                body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
                body.append(data)
                body.append("\r\n".data(using: .utf8)!)
            }
        }

        body.append("--\(boundary)--\r\n".data(using: .utf8)!)

        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        try checkResponse(response)

        let json = try JSONDecoder().decode([String: String].self, from: data)
        guard let workflowId = json["id"] ?? json["workflow_id"] else {
            throw BackendError.missingField("id")
        }
        return workflowId
    }

    // MARK: - Compile Stream (SSE)
    func compileStream(workflowId: String) -> AsyncStream<CompileEvent> {
        AsyncStream { continuation in
            Task {
                let url = baseURL.appendingPathComponent("workflows/\(workflowId)/compile/stream")
                guard let (bytes, response) = try? await URLSession.shared.bytes(from: url) else {
                    continuation.finish()
                    return
                }
                guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                    continuation.finish()
                    return
                }

                var buffer = ""
                for try await byte in bytes {
                    let char = String(bytes: [byte], encoding: .utf8) ?? ""
                    buffer += char
                    while let range = buffer.range(of: "\n\n") {
                        let chunk = String(buffer[buffer.startIndex..<range.lowerBound])
                        buffer = String(buffer[range.upperBound...])
                        // Parse SSE
                        for line in chunk.components(separatedBy: "\n") {
                            if line.hasPrefix("data: ") {
                                let jsonStr = String(line.dropFirst(6))
                                if let data = jsonStr.data(using: .utf8),
                                   let event = try? JSONDecoder().decode(CompileEvent.self, from: data) {
                                    continuation.yield(event)
                                }
                            }
                        }
                    }
                }
                continuation.finish()
            }
        }
    }

    // MARK: - Get Workflow
    func getWorkflow(id: String) async throws -> WorkflowModel {
        let url = baseURL.appendingPathComponent("workflows/\(id)")
        let (data, response) = try await URLSession.shared.data(from: url)
        try checkResponse(response)
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { dec in
            let str = try dec.singleValueContainer().decode(String.self)
            return Self.flexibleISO8601(str) ?? Date()
        }
        return try decoder.decode(WorkflowModel.self, from: data)
    }

    /// Handle ISO8601 with or without fractional seconds (backend sends microseconds).
    private static func flexibleISO8601(_ s: String) -> Date? {
        let withFrac = ISO8601DateFormatter()
        withFrac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = withFrac.date(from: s) { return d }
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        if let d = plain.date(from: s) { return d }
        // Fallback: strip fractional seconds manually
        if let dotIdx = s.firstIndex(of: "."),
           let tzIdx = s[dotIdx...].firstIndex(where: { $0 == "+" || $0 == "-" || $0 == "Z" }) {
            let stripped = String(s[..<dotIdx]) + String(s[tzIdx...])
            return plain.date(from: stripped)
        }
        return nil
    }

    // MARK: - Delete Workflow
    func deleteWorkflow(id: String) async throws {
        let url = baseURL.appendingPathComponent("workflows/\(id)")
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        let (_, response) = try await URLSession.shared.data(for: request)
        try checkResponse(response)
    }

    // MARK: - Update Workflow
    func updateWorkflow(_ workflow: WorkflowModel) async throws {
        let url = baseURL.appendingPathComponent("workflows/\(workflow.id)")
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        request.httpBody = try encoder.encode(workflow)
        let (_, response) = try await URLSession.shared.data(for: request)
        try checkResponse(response)
    }

    // MARK: - Start Run
    func startRun(workflowId: String, inputs: [[String: String]]?) async throws -> RunResult {
        let url = baseURL.appendingPathComponent("workflows/\(workflowId)/run")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let inputs = inputs {
            request.httpBody = try JSONEncoder().encode(["inputs": inputs])
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        try checkResponse(response)
        return try JSONDecoder().decode(RunResult.self, from: data)
    }

    // MARK: - Run Stream (WebSocket)
    func runStream(runId: String) -> AsyncStream<RunEvent> {
        AsyncStream { continuation in
            var wsURLComponents = URLComponents(url: self.baseURL.appendingPathComponent("runs/\(runId)/stream"), resolvingAgainstBaseURL: false)!
            wsURLComponents.scheme = self.baseURL.scheme == "https" ? "wss" : "ws"
            guard let wsURL = wsURLComponents.url else {
                continuation.finish()
                return
            }
            let task = URLSession.shared.webSocketTask(with: wsURL)
            task.resume()

            func receive() {
                task.receive { result in
                    switch result {
                    case .success(let message):
                        switch message {
                        case .string(let text):
                            if let data = text.data(using: .utf8),
                               let event = try? JSONDecoder().decode(RunEvent.self, from: data) {
                                continuation.yield(event)
                            }
                        case .data(let data):
                            if let event = try? JSONDecoder().decode(RunEvent.self, from: data) {
                                continuation.yield(event)
                            }
                        @unknown default:
                            break
                        }
                        receive()
                    case .failure:
                        continuation.finish()
                    }
                }
            }
            receive()

            continuation.onTermination = { _ in
                task.cancel(with: .goingAway, reason: nil)
            }
        }
    }

    // MARK: - Control Run
    func controlRun(runId: String, action: String) async throws {
        let url = baseURL.appendingPathComponent("runs/\(runId)/control")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["action": action])
        let (_, response) = try await URLSession.shared.data(for: request)
        try checkResponse(response)
    }

    // MARK: - Helpers
    private func checkResponse(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let code = (response as? HTTPURLResponse)?.statusCode ?? -1
            throw BackendError.httpError(code)
        }
    }
}

// MARK: - BackendError
enum BackendError: Error, LocalizedError {
    case httpError(Int)
    case missingField(String)

    var errorDescription: String? {
        switch self {
        case .httpError(let code): return "HTTP error \(code)"
        case .missingField(let field): return "Missing field: \(field)"
        }
    }
}
