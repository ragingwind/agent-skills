---
name: agent-browser
description: Playwright-based browser automation CLI for headless, scriptable UI verification. Use as the primary browser verification tool when Chrome for Claude extension connectivity is unreliable or unavailable.
---

# agent-browser Skill

Playwright-based CLI for browser automation during development. Designed for pipelines where Chrome extension connectivity is unreliable. No extension required — runs headless by default, fully scriptable.

## Performance: --native Flag

```bash
# Use native Rust daemon instead of Node.js (experimental, significantly faster startup)
agent-browser --native snapshot
AGENT_BROWSER_NATIVE=1 agent-browser snapshot   # via env var
```

**Recommended for pipeline use.** The Rust daemon avoids Node.js startup overhead, making sequential commands (open → snapshot → click → screenshot) noticeably faster. Set `AGENT_BROWSER_NATIVE=1` in the shell environment to apply globally without repeating the flag on every command.

## When to Use

| Scenario | Tool |
|----------|------|
| Headless, scriptable browser verification | **agent-browser** (primary) |
| Multi-worktree dev environments | **agent-browser** (primary) |
| Authenticated apps (Google Docs, Gmail, etc.) | Chrome for Claude |
| Ad-hoc interactive debugging in existing browser | Chrome for Claude |
| CI/CD automated E2E tests | Playwright spec files |

## Core Commands

### Session Lifecycle

```bash
# Open browser and navigate (caller provides URL)
agent-browser open <url>

# Navigate within session
agent-browser goto /chat/123

# Close browser (cleanup after session)
agent-browser close
```

### Page Inspection

```bash
# Full page snapshot (text + refs for clicking/filling)
agent-browser snapshot

# Interactive snapshot — shows only interactive elements (buttons, inputs, links)
agent-browser snapshot -i

# Screenshot (saved to current dir or specified path)
agent-browser screenshot [--path <file.png>]

# Get text content of element or page
agent-browser get text @ref
agent-browser get text                   # full page text
```

### Interaction

```bash
# Click by element reference (from snapshot)
agent-browser click @ref

# Fill input by reference
agent-browser fill @ref "value"

# Type into focused element
agent-browser type "text"

# Execute JavaScript in page context
agent-browser eval "document.title"
```

### Recording (Video Evidence)

```bash
# Start recording — creates .webm video
agent-browser record start <feature>-<flow>.webm

# Stop recording
agent-browser record stop

# Move recording to output directory immediately (file may be overwritten on next recording)
mv <output-file.webm> <output-dir>/
```

**IMPORTANT:** Move the webm to the evidence directory immediately. The `.webm` file may be overwritten on the next recording. Upload webm directly — GitHub Video Player extension plays webm inline.

## Screenshot Workflow

For development-time UI verification where screenshot evidence is sufficient.

**Caller provides:** `<url>` (page to verify), `<output-dir>` (where to save screenshots).

```bash
# 0. Enable native Rust daemon (recommended)
export AGENT_BROWSER_NATIVE=1

# 1. Open browser and navigate
agent-browser open <url>

# 2. Warm-up — wait for page to fully compile and render
agent-browser snapshot
agent-browser screenshot --path /tmp/warmup.png    # confirm rendering

# 3. Set up pre-existing state if needed (navigate, create data, return to target)
#    Complete all setup BEFORE taking evidence screenshots.

# 4. Take initial screenshot
agent-browser screenshot --path <output-dir>/step01-initial.png

# 5. Interact with the UI
agent-browser click @ref-button
agent-browser fill @ref-input "test value"

# 6. Re-snapshot after interaction (DOM refs invalidated by React re-renders)
agent-browser snapshot -i

# 7. Take screenshots after each interaction step
agent-browser screenshot --path <output-dir>/step02-after-click.png
agent-browser screenshot --path <output-dir>/step03-after-fill.png

# 8. Close browser
agent-browser close
```

### Warm-up Rule
- Always `snapshot` before taking evidence screenshots — it triggers and waits for page compilation.
- Complete all state setup before taking any evidence screenshots.
- **NEVER skip `snapshot -i` between interactions** — DOM refs are stale after any re-render; using a stale ref causes silent misses or wrong-element clicks.

## Recording Workflow

For acceptance-level verification where continuous visual proof of the user journey is required.

**Caller provides:** `<url>`, `<output-file.webm>` (recording filename), `<output-dir>` (destination directory).

```bash
# 0. Enable native Rust daemon (recommended)
export AGENT_BROWSER_NATIVE=1

# 1. Open browser
agent-browser open <url>

# 2. Warm-up — MUST happen before recording starts
agent-browser snapshot
agent-browser screenshot --path /tmp/warmup.png    # confirm rendering

# 3. Set up pre-existing state — MUST happen before recording starts
#    (login, creating data, navigating to starting state)

# 4. Start recording only after page is fully loaded and ready
agent-browser record start <output-file.webm>

# 5. Inspect page structure
agent-browser snapshot -i
#    NOTE: snapshot -i acts as a natural pause — use it between interactions
#    so reviewers can see each state change clearly.

# 6. Take initial screenshot
agent-browser screenshot --path <output-dir>/step01-initial.png

# 7. Interact with the UI
agent-browser click @ref-button
agent-browser fill @ref-input "test value"

# 8. Re-snapshot after interaction
agent-browser snapshot -i

# 9. Take screenshots after each interaction step
agent-browser screenshot --path <output-dir>/step02-after-click.png
agent-browser screenshot --path <output-dir>/step03-after-fill.png

# 10. Stop recording
agent-browser record stop

# 11. Move recording to output directory (file may be overwritten on next recording)
mv <output-file.webm> <output-dir>/

# 12. Close browser
agent-browser close
```

### Recording-Specific Rules
- **NEVER start `record start` immediately after `open`** — the loading spinner will dominate the video. Always warm up first.
- **NEVER set up test state after `record start`** — setup actions (login, creating data, navigating) must not appear in the feature recording.
- **NEVER skip `snapshot -i` between interactions** — recordings without pauses look like a rapid blur; reviewers cannot verify correctness.

## Re-snapshot Rule

**MUST re-snapshot after every interaction.** DOM element references (`@ref`) are invalidated by React re-renders, route changes, and any DOM mutation. Using a stale ref causes silent misses or wrong-element clicks.

```bash
agent-browser click @ref-submit     # triggers form submit → DOM re-renders
agent-browser snapshot -i            # MUST re-snapshot — old refs are stale
agent-browser click @ref-confirm    # now uses fresh refs from re-snapshot
```

## Verification Loop Rule

**UI verification is a gate, not a formality.** If the feature does not work correctly in the browser:

1. **Stop** — do not proceed to the next phase
2. **Document** — note what failed (screenshot + description)
3. **Return** — go back to the implementation phase and fix
4. **Re-verify** — run the browser verification again
5. **Repeat** until the verification passes

```
Implement → Browser verify → PASS? → Commit → Next phase
                   ↓ FAIL
              Fix implementation → Re-verify
```

This applies to every phase that modifies `.tsx`, `.jsx`, `.css`, or `.svg` files. **Never advance to the next phase with a failing browser verification.**

## Fallback: Chrome for Claude

If `agent-browser` is unavailable (binary not installed, unexpected crash), fall back to Chrome for Claude:

```
agent-browser unavailable → note "browser verify: agent-browser unavailable, using Chrome for Claude"
                          → use mcp__claude-in-chrome__* tools as fallback
```

If both are unavailable:
```
note "browser verify: unavailable (agent-browser not installed, Chrome extension not connected)"
→ proceed with E2E tests only
→ add note to PR comment: "browser verification not performed — automated E2E only"
```
