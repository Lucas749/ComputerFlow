import Foundation

// MARK: - WorkflowModel
struct WorkflowModel: Codable, Identifiable {
    var id: String
    var name: String
    var summary: String?
    var createdAt: Date
    var updatedAt: Date
    var steps: [WorkflowStep]
    var variables: [WorkflowVariable]

    enum CodingKeys: String, CodingKey {
        case id, name, summary, createdAt, updatedAt, steps, variables
    }
}

// MARK: - StepExecutor
struct StepExecutor: Codable {
    var kind: String   // "kernel" | "computer_use" | "northstar" | "local"
    var entryFn: String?
}

// MARK: - WorkflowStep
struct WorkflowStep: Codable, Identifiable {
    var id: String
    var n: Int
    var action: String
    var intent: String?
    var target: StepTarget
    var value: StepValue?
    var executor: StepExecutor?
    var screenshot: String?
    var approved: Bool
    var needsReview: Bool
    var notes: String

    var actionLabel: String { action.replacingOccurrences(of: "_", with: " ").capitalized }

    var displayIntent: String {
        if let i = intent, !i.isEmpty { return i }
        return actionLabel
    }
}

// MARK: - StepTarget
struct StepTarget: Codable {
    var kind: String?
    var description: String?
    var selector: String?
    var url: String?
    var x: Double?
    var y: Double?
    var screenW: Double?
    var screenH: Double?

    var displayString: String {
        if let url = url { return url }
        if let d = description, !d.isEmpty { return d }
        if let s = selector { return s }
        return ""
    }
}

// MARK: - StepValue
// Backend sends value as: null | string | {"kind":"var","ref":"Name"} | {"kind":"keys","keys":[...]}
struct StepValue: Codable {
    var raw: String?
    var variableRef: String?
    var keys: [String]?

    var isVariable: Bool { variableRef != nil }
    var displayString: String {
        if let v = variableRef { return "[\(v)]" }
        if let k = keys { return k.joined(separator: "+") }
        return raw ?? ""
    }

    init(raw: String? = nil, variableRef: String? = nil, keys: [String]? = nil) {
        self.raw = raw
        self.variableRef = variableRef
        self.keys = keys
    }

    init(from decoder: Decoder) throws {
        // Try plain string first
        if let str = try? decoder.singleValueContainer().decode(String.self) {
            self.raw = str; self.variableRef = nil; self.keys = nil
            return
        }
        // Try object
        let c = try decoder.container(keyedBy: DynKey.self)
        let kind = try? c.decode(String.self, forKey: DynKey("kind"))
        if kind == "var" {
            self.variableRef = try? c.decode(String.self, forKey: DynKey("ref"))
            self.raw = nil; self.keys = nil
        } else if kind == "keys" {
            self.keys = try? c.decode([String].self, forKey: DynKey("keys"))
            self.raw = nil; self.variableRef = nil
        } else {
            self.raw = try? c.decode(String.self, forKey: DynKey("text"))
            self.variableRef = nil; self.keys = nil
        }
    }

    func encode(to encoder: Encoder) throws {
        if let v = variableRef {
            var c = encoder.container(keyedBy: DynKey.self)
            try c.encode("var", forKey: DynKey("kind"))
            try c.encode(v, forKey: DynKey("ref"))
        } else if let k = keys {
            var c = encoder.container(keyedBy: DynKey.self)
            try c.encode("keys", forKey: DynKey("kind"))
            try c.encode(k, forKey: DynKey("keys"))
        } else if let r = raw {
            var c = encoder.singleValueContainer()
            try c.encode(r)
        } else {
            var c = encoder.singleValueContainer()
            try c.encodeNil()
        }
    }
}

// MARK: - WorkflowVariable
struct WorkflowVariable: Codable, Identifiable {
    var id: String
    var name: String
    var type: String?
    var defaultValue: String?

    enum CodingKeys: String, CodingKey {
        case id, name, type
        case defaultValue = "default"
    }

    init(id: String, name: String, type: String? = "string", defaultValue: String? = nil) {
        self.id = id; self.name = name; self.type = type; self.defaultValue = defaultValue
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decode(String.self, forKey: .id)) ?? UUID().uuidString
        name = try c.decode(String.self, forKey: .name)
        type = try? c.decode(String.self, forKey: .type)
        defaultValue = try? c.decode(String.self, forKey: .defaultValue)
    }
}

// MARK: - CompileEvent
// stage can be an Int (0-3) or the string "error" from the backend
struct CompileEvent: Codable {
    var stage: Int        // "error" decodes as -1
    var progress: Double
    var subline: String
    var error: Bool?

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        // stage may be Int or String "error"
        if let i = try? c.decode(Int.self, forKey: .stage) {
            stage = i
        } else {
            stage = -1
        }
        progress = (try? c.decode(Double.self, forKey: .progress)) ?? 0
        subline  = (try? c.decode(String.self, forKey: .subline))  ?? ""
        error    = try? c.decode(Bool.self, forKey: .error)
    }

    enum CodingKeys: String, CodingKey {
        case stage, progress, subline, error
    }
}

// MARK: - RunResult
struct RunResult: Codable {
    var runId: String
    var liveViewUrl: String?
    var status: String

    enum CodingKeys: String, CodingKey {
        case runId, liveViewUrl, status
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        runId = try c.decode(String.self, forKey: .runId)
        liveViewUrl = try? c.decode(String.self, forKey: .liveViewUrl)
        status = (try? c.decode(String.self, forKey: .status)) ?? "pending"
    }
}

// MARK: - RunEvent
// Event shapes emitted by backend WS /runs/{id}/stream:
//   {"type":"run_started","runId":"..."}
//   {"type":"live_view","urls":{"kernel_browser":"https://...","lightcone_os":"..."}}
//   {"type":"step","stepIndex":0,"totalSteps":4,"intent":"click button","environment":"browser"}
//   {"type":"action","action":"click","environment":"desktop"}
//   {"type":"screenshot","b64":"...","environment":"desktop"}
//   {"type":"run_finished","status":"completed","answer":"..."}
struct RunEvent: Codable {
    var type: String?
    var runId: String?
    var urls: [String: String]?
    var stepIndex: Int?
    var totalSteps: Int?
    var intent: String?
    var action: String?
    var environment: String?
    var b64: String?
    var status: String?
    var answer: String?
    var error: String?
}

// MARK: - DynKey helper
private struct DynKey: CodingKey {
    var stringValue: String
    var intValue: Int? { nil }
    init(_ s: String) { stringValue = s }
    init?(stringValue: String) { self.stringValue = stringValue }
    init?(intValue: Int) { return nil }
}

// MARK: - Sample Data
extension WorkflowModel {
    static func sample() -> WorkflowModel {
        WorkflowModel(
            id: "wf_sample",
            name: "Extract CRM Data",
            createdAt: Date(),
            updatedAt: Date(),
            steps: [
                WorkflowStep(
                    id: "s1", n: 1, action: "navigate",
                    intent: "Open CRM search page",
                    target: StepTarget(kind: "url", description: nil, selector: nil, url: "https://crm.example.com/search"),
                    value: nil, screenshot: nil, approved: true, needsReview: false, notes: ""
                ),
                WorkflowStep(
                    id: "s2", n: 2, action: "click",
                    intent: "Focus the search field",
                    target: StepTarget(kind: "description", description: "Search bar at top of page", selector: nil, url: nil),
                    value: nil, screenshot: nil, approved: true, needsReview: false, notes: ""
                ),
                WorkflowStep(
                    id: "s3", n: 3, action: "type",
                    intent: "Type search query",
                    target: StepTarget(kind: "description", description: "Search input field", selector: nil, url: nil),
                    value: StepValue(variableRef: "SearchQuery"),
                    screenshot: nil, approved: false, needsReview: true, notes: ""
                ),
            ],
            variables: [
                WorkflowVariable(id: "v1", name: "SearchQuery", type: "string", defaultValue: "")
            ]
        )
    }
}
