---
name: browse-terminal
description: Open web pages directly inside the Ghostty terminal. Uses awrit (Chromium + Kitty Graphics Protocol) to render real web pages in the terminal without a browser. Supports new tab, right-side pane, and close.
model: haiku
allowed-tools: Bash
user-invocable: true
argument-hint: "[--tab|--pane] [--watch FILE] [url] | close [--tab|--pane]"
---

Render web pages directly inside a Ghostty terminal tab or pane.

## Technical background

- **awrit** ([chase/awrit](https://github.com/chase/awrit)): Chromium-based terminal browser
- **Kitty Graphics Protocol**: image rendering protocol supported by Ghostty
- Ghostty does not support Sixel → carbonyl is unusable, so awrit is the best choice

## Arguments

| Argument | Behavior |
|----------|----------|
| `[url]` | Open in a new tab (default) |
| `--tab [url]` | Open in a new tab |
| `--pane [url]` | Split the current tab to the right and open there |
| `--watch FILE` | Auto-reload on file change (use with an open option) |
| `close --tab` | Close the current tab |
| `close --pane` | Close the currently focused pane |

When the URL is omitted, the default is: `https://example.com`

## Execution

```bash
# Open
bash ~/.claude/scripts/ghostty-browse-tab.sh [--tab|--pane] [URL]

# Watch a file + auto-reload (e.g., refresh the Slidev view when slides.md is edited)
bash ~/.claude/scripts/ghostty-browse-tab.sh --pane --watch slides.md http://localhost:3030

# Close
bash ~/.claude/scripts/ghostty-browse-tab.sh close [--tab|--pane]
```

## How --watch works

1. When the awrit pane/tab opens, store the corresponding terminal UUID
2. Use `fswatch` to watch the specified file in the background
3. On file change, send `Ctrl+R` to that terminal via Ghostty AppleScript → awrit (Chromium) reloads the page

**Prerequisite**: `brew install fswatch`

> **Note**: When Slidev (`pnpm dev`) is running, Vite HMR pushes changes to awrit over WebSocket automatically. `--watch` is an explicit fallback for cases where HMR is not available.

## When awrit is not installed

```
awrit is not installed.
Install: curl -fsS https://chase.github.io/awrit/get | bash
(bun is required: curl -fsSL https://bun.sh/install | bash)
```

## Completion report format

```
# Open tab
Tab opened: tab-xxxxxxxx
URL: [url]

# Open pane
Pane opened (right): [uuid]
URL: [url]

# Close tab
Tab closed: tab-xxxxxxxx

# Close pane
Pane closed: [uuid]
```
