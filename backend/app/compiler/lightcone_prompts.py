"""
lightcone_prompts.py — All prompts and structured output for the Lightcone compiler.
"""

SYSTEM_PROMPT = """You are the ComputerFlow action describer.

You are given:
  1. A short prompt describing ONE user action (click, type, right-click, or hotkey).
  2. A screenshot captured IMMEDIATELY BEFORE that action took place.

Return ONLY a JSON object (no prose, no markdown) with these fields:
{
  "intent": "Short imperative phrase describing what the user wanted (<= 12 words)",
  "ui_element": "Description of the exact on-screen element targeted (button label, field placeholder, menu item) — precise enough for a vision model to re-locate it",
  "app_context": "Which app/window/page the user is in (e.g. 'Safari on example.com', 'Finder', 'Excel Sheet1')",
  "executor": "kernel" | "computer_use",
  "confidence": 0.0-1.0
}

Rules:
- Be concrete. Say "Click the blue 'Submit' button in the signup form footer" not "Click a button".
- Use executor="kernel" when the action is inside a web browser. Use executor="computer_use" for native desktop apps.
- If typing, ui_element should describe the input field; intent should quote the typed text if short.
- Set confidence < 0.6 if you cannot identify the element clearly.
- Return ONLY the JSON object, nothing else."""


def build_user_prompt(kind: str, x=None, y=None, screen_w=None, screen_h=None,
                      text=None, keys=None) -> str:
    if kind == "click":
        return (
            f"The user clicked at screen coordinates ({int(x or 0)}, {int(y or 0)}) "
            f"on a {int(screen_w or 0)}×{int(screen_h or 0)} display. "
            "The screenshot was captured immediately before the click. "
            "Describe what UI element the user clicked and what they intended."
        )
    if kind == "right_click":
        return (
            f"The user right-clicked at ({int(x or 0)}, {int(y or 0)}). "
            "Describe the element and what context menu they were opening."
        )
    if kind == "type":
        preview = (text or "").replace("\n", "\\n")[:80]
        return (
            f'The user typed: "{preview}". '
            "The screenshot shows the state before typing began. "
            "Describe which input field they were typing into."
        )
    if kind == "hotkey":
        combo = "+".join(keys or [])
        return (
            f"The user pressed the keyboard shortcut: {combo}. "
            "From the screenshot, describe what app/context they were in "
            "and what this shortcut most likely does."
        )
    return "Describe the user action shown in the screenshot."
