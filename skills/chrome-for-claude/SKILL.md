---
name: chrome-for-claude
description: Chrome browser integration for Claude Code — live debugging, authenticated app testing, and video recording via the Claude in Chrome extension.
---

# Chrome Browser Integration

Claude Code integrates with the Claude in Chrome extension for browser automation directly from the CLI or VS Code.

## Prerequisites

- Google Chrome browser
- [Claude in Chrome extension](https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn) v1.0.36+
- Claude Code v2.0.73+
- Direct Anthropic plan (Pro, Max, Team, or Enterprise)

## Quick Start

```bash
# Launch with Chrome integration
claude --chrome

# Or enable in existing session
/chrome
```

Enable by default: run `/chrome` and select "Enabled by default".

## Capabilities

- **Live debugging** — Read console errors and DOM state, then fix the code
- **Design verification** — Build UI then open in browser to verify
- **Web app testing** — Test form validation, visual regressions, user flows
- **Authenticated apps** — Interact with Google Docs, Gmail, Notion (uses your login state)
- **Data extraction** — Pull structured information from web pages
- **Task automation** — Data entry, form filling, multi-site workflows
- **Session recording** — Record interactions as videos

## When to Use Chrome vs Other Tools

| Tool | When to Use |
|------|-------------|
| `chrome` | Live debugging, authenticated apps, visual verification, recording videos |
| `playwright` | Writing test SPECs, CI/CD, review phase, regression testing |

## Example Workflows

### Test Local Web App

```text
I just updated the login form validation. Can you open localhost:3000,
try submitting the form with invalid data, and check if the error
messages appear correctly?
```

### Debug with Console Logs

```text
Open the dashboard page and check the console for any errors when
the page loads.
```

### Extract Data

```text
Go to the product listings page and extract the name, price, and
availability for each item. Save the results as a CSV file.
```

### Record a Demo Video

```text
Record a video showing how to complete the checkout flow, from adding
an item to the cart through to the confirmation page.
```

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| "Browser extension is not connected" | Native messaging host issue | Restart Chrome + Claude Code, run `/chrome` |
| "Extension not detected" | Extension not installed/enabled | Install in `chrome://extensions` |
| "No tab available" | Tab not ready | Ask Claude to create a new tab |
| "Receiving end does not exist" | Service worker went idle | Run `/chrome` → "Reconnect extension" |

If connection drops during long sessions, run `/chrome` and select "Reconnect extension".

## Connection Recovery

When a Chrome tool call returns an error:

1. Run `/chrome` → select "Reconnect extension"
2. If reconnection fails → restart Chrome and Claude Code, then retry
3. **NEVER silently skip browser tests because the extension disconnected** — always attempt recovery first

## Video Recording

Record browser interactions as `.webm` video. Output path is caller-provided.

### Step-by-step

```
1. gif_creator(action: "start_recording", tabId: <id>)
2. computer(action: "screenshot", tabId: <id>)   ← capture initial state (in-recording only)
3. Perform all user flow actions (click, type, navigate, etc.)
4. computer(action: "screenshot", tabId: <id>)   ← capture final state (in-recording only)
5. gif_creator(action: "stop_recording", tabId: <id>)
6. gif_creator(action: "export", tabId: <id>, filename: "<output-file>", download: true)
```

Output file path and name are provided by the caller.

## ⚠️ Screenshot evidence: never use `computer(action: "screenshot")`

The `computer` tool captures the **entire operating-system display** (terminal, Claude Code window, menu bar, other tabs — everything). This is fine inside the gif-recording flow above (where the final webm is the artifact), but it is **NEVER acceptable as PR evidence** because:

1. It leaks the user's desktop contents (terminal output, other apps, system info, file names).
2. The actual feature under test is usually a tiny fraction of the frame.
3. Retina captures are 5120×2880 PNGs (1.5–2 MB each) that bloat the test-evidence release.

For evidence screenshots (`$STATE_DIR/evidence/browser-verify-*.png`, `tia-*.png`), **always use `agent-browser screenshot`** — it captures the page viewport only (~1280×720, 100–180 KB) via Playwright. This applies even when the rest of the flow uses claude-in-chrome for authenticated navigation.

```bash
# CORRECT — viewport-only capture for evidence
agent-browser screenshot --path "$STATE_DIR/evidence/browser-verify-phase1-step01-empty-state.png"

# WRONG — full-screen capture leaks desktop contents
# mcp__claude-in-chrome__computer(action: "screenshot", ...)  ← DO NOT use for evidence
```

If `agent-browser` is genuinely unavailable (extension disconnected AND CLI broken), use `mcp__claude-in-chrome__javascript_tool` to inject a `chrome.tabs.captureVisibleTab()` call — which captures the tab's rendered area only, not the whole screen. Never reach for `computer(action: "screenshot")` for evidence.

The pre-PR gate hook rejects evidence PNGs above 1920×1080 — full-screen captures fail the gate automatically.
