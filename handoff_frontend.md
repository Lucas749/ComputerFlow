# ComputerFlow — Frontend ↔ Backend Handoff

How the frontend (recorder + UI) calls the backend runner based on a recorded flow.

---

## The full pipeline

```
User records actions
       ↓
list[RecordedAction]        ← recorder emits one per user action
       ↓  Claude compiler
FlowRequest                 ← what the backend receives
  steps: list[SOPStep]      ← each step has target + strategy
       ↓  runner.run_flow()
FlowResult
  answer: str
  live_view_urls: dict       ← surface these to the user in the UI
  environment_id: str | None ← save for reuse
```

---

## FlowRequest — the request shape

```python
FlowRequest(
    title="...",                           # display name
    goal="...",                            # one-sentence task goal
    steps=[SOPStep(...)],                  # compiled from recording
    default_target=RunTarget.AUTO,         # override globally or per-step
    default_strategy=ExecutionStrategy.CUA_LOOP,
    start_url="https://...",               # browser tasks: navigate here first
    context="...",                         # extra context for the model
    options=RunOptions(
        environment_id=None,               # pass a saved env_id to reuse it
        viewport_width=1280,
        viewport_height=720,
        stealth=True,
        step_delay_ms=1000,
        max_actions_per_step=15,
        max_total_actions=100,
    ),
)
```

---

## RunTarget — where it runs

| Value | Surface | What spins up |
|-------|---------|---------------|
| `RunTarget.AUTO` | decides from step.surface | BROWSER → kernel_browser, DESKTOP → lightcone_os |
| `RunTarget.KERNEL_BROWSER` | cloud browser | Kernel Chromium (stealth, residential proxy) |
| `RunTarget.LIGHTCONE_OS` | cloud desktop | Lightcone Linux OS (full desktop, any app) |
| `RunTarget.LOCAL` | user's machine | Local CUA agent on localhost:27182 |

---

## ExecutionStrategy — how it runs

| Value | Model calls | Best for |
|-------|------------|---------|
| `ExecutionStrategy.CUA_LOOP` | One Northstar call per step, screenshot + reference image | Most flows — uses recorded screenshots for visual grounding |
| `ExecutionStrategy.AUTONOMOUS` | One Northstar Task API call for the whole group | Simple, self-contained tasks; no screenshots needed |
| `ExecutionStrategy.DIRECT` | Zero — replays coordinates directly | Exact replay of stable UIs; fastest; no LLM cost |

---

## Scenario examples

### 1. Pure web flow (browser only)

The compiler sets `surface=Surface.BROWSER` on all steps. Frontend sends:

```json
{
  "title": "Submit expense report",
  "goal": "Fill and submit the monthly expense form on Concur",
  "default_target": "kernel_browser",
  "default_strategy": "cua_loop",
  "start_url": "https://concur.example.com",
  "steps": [
    {
      "intent": "Click New Expense",
      "action": "click",
      "surface": "browser",
      "target_kind": "description",
      "description": "New Expense button in the top toolbar",
      "screenshot_b64": "iVBORw..."
    },
    {
      "intent": "Enter amount 142.50",
      "action": "type",
      "surface": "browser",
      "text": "142.50",
      "description": "Amount field",
      "screenshot_b64": "iVBORw..."
    }
  ]
}
```

Runner creates one Kernel session, runs CUA loop for each step, surfaces:

```json
{
  "answer": "Expense report #2847 submitted successfully.",
  "steps_taken": 8,
  "live_view_urls": { "kernel_browser": "https://kernel.run/live/abc123" },
  "ok": true
}
```

---

### 2. Pure desktop / legacy software (Lightcone OS)

Compiler detects no browser — all steps on a native app.

```json
{
  "title": "Enter invoice in SAP",
  "goal": "Create vendor invoice for $4,200",
  "default_target": "lightcone_os",
  "default_strategy": "cua_loop",
  "options": { "environment_id": "env_sap_001" },
  "steps": [
    {
      "intent": "Open transaction FB60",
      "action": "type",
      "surface": "desktop",
      "text": "/nFB60",
      "screenshot_b64": "iVBORw..."
    }
  ]
}
```

Pass a saved `environment_id` so the SAP environment (already configured) is reused.

Runner opens the Lightcone computer, surfaces:

```json
{
  "live_view_urls": { "lightcone_os": "https://api.tzafon.ai/debug/comp_xyz" },
  "environment_id": "env_sap_001"
}
```

---

### 3. Mixed flow — browser scrape then desktop process

Steps have different `target` values; the runner detects the target change and
opens a second session automatically (handoff).

```json
{
  "title": "Scrape leads → CRM → local spreadsheet",
  "goal": "Export new leads from LinkedIn and paste into local Excel",
  "default_strategy": "cua_loop",
  "steps": [
    {
      "intent": "Open LinkedIn Sales Navigator",
      "action": "navigate",
      "target": "kernel_browser",
      "surface": "browser",
      "text": "https://www.linkedin.com/sales/search/people"
    },
    {
      "intent": "Export leads list",
      "action": "click",
      "target": "kernel_browser",
      "surface": "browser",
      "description": "Export button",
      "screenshot_b64": "iVBORw..."
    },
    {
      "intent": "Open Excel and paste data",
      "action": "click",
      "target": "lightcone_os",
      "surface": "desktop",
      "description": "Excel icon on desktop",
      "screenshot_b64": "iVBORw..."
    },
    {
      "intent": "Paste and save",
      "action": "hotkey",
      "target": "lightcone_os",
      "surface": "desktop",
      "keys": ["ctrl", "v"]
    }
  ]
}
```

Runner flow:
1. Steps 1–2: Kernel browser session opens → LinkedIn scrape
2. **Handoff** detected at step 3 (target changes to `lightcone_os`)
3. Steps 3–4: Lightcone OS session opens → Excel paste
4. Both sessions clean up at the end

Response includes live view URLs for both surfaces:

```json
{
  "live_view_urls": {
    "kernel_browser": "https://kernel.run/live/abc123",
    "lightcone_os":   "https://api.tzafon.ai/debug/comp_xyz"
  }
}
```

---

### 4. Autonomous (no step-by-step control needed)

For simple, self-contained tasks where you trust Northstar to figure it out.

```json
{
  "title": "Check weather",
  "goal": "Go to weather.com and tell me the 5-day forecast for NYC",
  "default_target": "kernel_browser",
  "default_strategy": "autonomous",
  "steps": [
    { "intent": "Go to weather.com and find NYC 5-day forecast", "action": "navigate", "surface": "browser" }
  ]
}
```

One Task API call instead of a per-step loop. Faster, fewer round trips.

---

### 5. Local machine (user's own computer)

User wants to run the flow on their own Mac without any cloud session.

```json
{
  "title": "Reorganise Downloads folder",
  "goal": "Move PDF files to ~/Documents/Invoices",
  "default_target": "local",
  "default_strategy": "cua_loop",
  "steps": [
    {
      "intent": "Open Finder and navigate to Downloads",
      "action": "hotkey",
      "surface": "desktop",
      "keys": ["cmd", "shift", "h"]
    }
  ]
}
```

Requires the ComputerFlow local agent running (desktop app starts it automatically).
No `live_view_url` is returned for LOCAL — the user can see their own screen.

---

## How the frontend decides target + strategy

The compiler (Claude) resolves these after recording. The rules:

```
surface == browser AND user wants full control    → kernel_browser + cua_loop
surface == browser AND simple task               → kernel_browser + autonomous
surface == desktop AND cloud preferred           → lightcone_os + cua_loop
surface == desktop AND user wants local          → local + cua_loop
surface == desktop AND environment_id saved      → lightcone_os + cua_loop (reuse env)
mixed steps in same recording                   → per-step target override
```

The frontend can also let the user override at run time via a dropdown:
- "Cloud Browser" → `kernel_browser`
- "Cloud Computer" → `lightcone_os`
- "My Computer" → `local`

---

## Saving and reusing environments

For flows that install software (LibreOffice, SAP GUI, etc.) save the
`environment_id` from the first FlowResult and pass it back in `options`:

```
Run 1:  options.environment_id = null
        → FlowResult.environment_id = "comp_xyz"   ← save this

Run 2:  options.environment_id = "comp_xyz"
        → Lightcone reuses the existing env (no reinstall)
```

---

## Live view URL usage

Every FlowResult includes `live_view_urls` — open these in an `<iframe>` or
`<webview>` in the app so the user can watch progress in real time.

```ts
// Frontend pseudocode
const result = await runFlow(flowRequest);

if (result.live_view_urls.kernel_browser) {
  showPiP(result.live_view_urls.kernel_browser);      // browser PiP panel
}
if (result.live_view_urls.lightcone_os) {
  showPiP(result.live_view_urls.lightcone_os);        // desktop PiP panel
}
```

Both panels can be open simultaneously during a mixed flow.

---

## API surface (Python, called from the backend route)

```python
from app.infra import ComputerFlowRunner, FlowRequest, SOPStep, RunTarget, ExecutionStrategy, RunOptions

runner = ComputerFlowRunner()   # reads KERNEL_API_KEY + TZAFON_API_KEY from env

result = await runner.run_flow(FlowRequest(
    title=...,
    goal=...,
    steps=[...],
    default_target=RunTarget.AUTO,
    default_strategy=ExecutionStrategy.CUA_LOOP,
    options=RunOptions(environment_id=saved_env_id),
))

# result.answer          → final agent answer
# result.live_view_urls  → {"kernel_browser": "...", "lightcone_os": "..."}
# result.environment_id  → save this for the next run
# result.ok              → False if unhandled error
# result.error           → error message when ok=False
```
