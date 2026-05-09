import Foundation

// MARK: - WorkflowModel
struct WorkflowModel: Codable, Identifiable {
    var id: String
    var name: String
    var createdAt: Date
    var updatedAt: Date
    var steps: [WorkflowStep]
    var variables: [WorkflowVariable]
}

// MARK: - WorkflowStep
struct WorkflowStep: Codable, Identifiable {
    var id: String
    var n: Int
    var action: StepAction
    var target: StepTarget
    var value: StepValue?
    var screenshot: String?
    var approved: Bool
    var needsReview: Bool
    var notes: String

    var actionLabel: String { action.rawValue.capitalized }
}

// MARK: - StepAction
enum StepAction: String, Codable, CaseIterable {
    case navigate
    case click
    case type
    case press_key
    case scroll
    case wait
    case extract
    case assert
}

// MARK: - StepTarget
struct StepTarget: Codable {
    var selector: String?
    var label: String?
    var url: String?

    var displayString: String {
        if let url = url { return url }
        if let label = label { return "\"\(label)\"" }
        if let selector = selector { return selector }
        return ""
    }
}

// MARK: - StepValue
struct StepValue: Codable {
    var raw: String?
    var variableRef: String?

    var isVariable: Bool { variableRef != nil }
    var displayString: String {
        if let v = variableRef { return "[\(v)]" }
        return raw ?? ""
    }
}

// MARK: - WorkflowVariable
struct WorkflowVariable: Codable, Identifiable {
    var id: String
    var name: String
    var defaultValue: String?
}

// MARK: - CompileEvent
struct CompileEvent: Codable {
    var stage: Int       // 0-3
    var progress: Double // 0-100
    var subline: String
}

// MARK: - RunResult
struct RunResult: Codable {
    var runId: String
    var liveViewUrl: String?
    var status: String
}

// MARK: - RunEvent
struct RunEvent: Codable {
    var stepIndex: Int?
    var totalSteps: Int?
    var logLine: String?
    var status: String?
}

// MARK: - Sample Data
extension WorkflowModel {
    static func sample() -> WorkflowModel {
        WorkflowModel(
            id: UUID().uuidString,
            name: "Extract CRM Data",
            createdAt: Date(),
            updatedAt: Date(),
            steps: [
                WorkflowStep(
                    id: UUID().uuidString, n: 1,
                    action: .navigate,
                    target: StepTarget(selector: nil, label: nil, url: "https://crm.example.com/search"),
                    value: nil, screenshot: nil, approved: true, needsReview: false, notes: ""
                ),
                WorkflowStep(
                    id: UUID().uuidString, n: 2,
                    action: .click,
                    target: StepTarget(selector: nil, label: "Search Bar", url: nil),
                    value: nil, screenshot: nil, approved: true, needsReview: false, notes: ""
                ),
                WorkflowStep(
                    id: UUID().uuidString, n: 3,
                    action: .type,
                    target: StepTarget(selector: nil, label: "Search Bar", url: nil),
                    value: StepValue(raw: nil, variableRef: "Input"),
                    screenshot: nil, approved: false, needsReview: true, notes: "Review input value"
                ),
                WorkflowStep(
                    id: UUID().uuidString, n: 4,
                    action: .click,
                    target: StepTarget(selector: nil, label: "Submit", url: nil),
                    value: nil, screenshot: nil, approved: false, needsReview: false, notes: ""
                ),
                WorkflowStep(
                    id: UUID().uuidString, n: 5,
                    action: .extract,
                    target: StepTarget(selector: "table", label: nil, url: nil),
                    value: StepValue(raw: "Table→csv", variableRef: nil),
                    screenshot: nil, approved: false, needsReview: false, notes: ""
                )
            ],
            variables: [
                WorkflowVariable(id: UUID().uuidString, name: "Input", defaultValue: "")
            ]
        )
    }
}
