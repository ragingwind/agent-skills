#!/bin/bash
# ghostty-browse-tab.sh
# Open web pages in Ghostty using awrit (Chromium + Kitty Graphics Protocol)
#
# Usage:
#   ghostty-browse-tab.sh [--tab] [--watch FILE] [url]    Open in a new tab (default)
#   ghostty-browse-tab.sh --pane [--watch FILE] [url]     Split right and open in a pane
#   ghostty-browse-tab.sh close --tab                     Close the current tab
#   ghostty-browse-tab.sh close --pane                    Close the currently focused pane

set -euo pipefail

# ── Argument parsing ───────────────────────────────────────
MODE="tab"    # tab | pane | close-tab | close-pane
URL=""
WATCH_FILE=""

# Check whether the first argument is the 'close' subcommand
if [[ "${1:-}" == "close" ]]; then
  shift
  case "${1:-}" in
    --tab|-t)  MODE="close-tab";  shift ;;
    --pane|-p) MODE="close-pane"; shift ;;
    *)
      echo "Error: a close target must be specified." >&2
      echo "  Usage: close --tab | close --pane" >&2
      exit 1 ;;
  esac
else
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --pane|-p) MODE="pane"; shift ;;
      --tab|-t)  MODE="tab";  shift ;;
      --watch|-w)
        WATCH_FILE="${2:-}"
        if [ -z "$WATCH_FILE" ]; then
          echo "Error: --watch requires a file path to watch." >&2
          exit 1
        fi
        shift 2 ;;
      -*)
        echo "Error: unknown option: $1" >&2
        echo "Usage: ghostty-browse-tab.sh [--tab|--pane] [--watch FILE] [url]" >&2
        echo "       ghostty-browse-tab.sh close [--tab|--pane]" >&2
        exit 1 ;;
      *) URL="$1"; shift ;;
    esac
  done
fi

URL="${URL:-https://example.com}"
AWRIT_EXE="${HOME}/.local/bin/awrit"

# ── Confirm Ghostty is running ─────────────────────────────
GHOSTTY_RUNNING=$(osascript -e 'tell application "System Events" to return (exists process "ghostty")' 2>/dev/null || echo "false")
if [ "$GHOSTTY_RUNNING" != "true" ]; then
  echo "Error: Ghostty is not running." >&2
  exit 1
fi

# ── Close commands ─────────────────────────────────────────
if [ "$MODE" = "close-tab" ]; then
  RESULT=$(osascript << 'HEREDOC'
tell application "Ghostty"
  set t to selected tab of front window
  set tid to id of t
  close tab t
  return "Tab closed: " & tid
end tell
HEREDOC
)
  echo "$RESULT"
  exit 0
fi

if [ "$MODE" = "close-pane" ]; then
  RESULT=$(osascript << 'HEREDOC'
tell application "Ghostty"
  set ft to focused terminal of selected tab of front window
  set fid to id of ft
  close ft
  return "Pane closed: " & fid
end tell
HEREDOC
)
  echo "$RESULT"
  exit 0
fi

# ── Confirm awrit is installed ─────────────────────────────
if [ ! -x "$AWRIT_EXE" ]; then
  echo "Error: awrit is not installed." >&2
  echo "" >&2
  echo "Installation:" >&2
  echo "  curl -fsS https://chase.github.io/awrit/get | bash" >&2
  echo "  (bun is required: curl -fsSL https://bun.sh/install | bash)" >&2
  exit 1
fi

# ── Open ───────────────────────────────────────────────────
if [ "$MODE" = "pane" ]; then
  ID=$(osascript << HEREDOC
tell application "Ghostty"
  set conf to new surface configuration
  set initial input of conf to "awrit ${URL}\n"
  set newTerm to split (focused terminal of selected tab of front window) direction right with configuration conf
  return id of newTerm
end tell
HEREDOC
)
  echo "Pane opened (right): ${ID}"
else
  ID=$(osascript << HEREDOC
tell application "Ghostty"
  set conf to new surface configuration
  set initial input of conf to "awrit ${URL}\n"
  new tab in front window with configuration conf
  return id of (selected tab of front window)
end tell
HEREDOC
)
  echo "Tab opened: ${ID}"
fi

echo "URL: ${URL}"
echo "Browser: awrit (Chromium + Kitty Graphics Protocol)"

# ── File watch (auto-reload) ───────────────────────────────
if [ -n "$WATCH_FILE" ]; then
  if ! command -v fswatch &>/dev/null; then
    echo "" >&2
    echo "WARNING: --watch requires fswatch." >&2
    echo "   Install: brew install fswatch" >&2
  else
    TERM_ID="${ID}"
    RESOLVED_WATCH=$(realpath "$WATCH_FILE" 2>/dev/null || echo "$WATCH_FILE")

    # Detect file change → send Ctrl+R to the matching terminal
    (
      fswatch -o "${RESOLVED_WATCH}" | while read -r _; do
        osascript -e "
tell application \"Ghostty\"
  repeat with w in windows
    repeat with t in tabs of w
      repeat with term in terminals of t
        if (id of term as string) = \"${TERM_ID}\" then
          write text (ASCII character 18) to term
          exit repeat
        end if
      end repeat
    end repeat
  end repeat
end tell" 2>/dev/null || true
      done
    ) &
    WATCHER_PID=$!

    echo ""
    echo "Watching file: ${WATCH_FILE} → auto-reload on change"
    echo "Stop watcher: kill ${WATCHER_PID}"
  fi
fi

echo ""
echo "Controls: q / Ctrl+C — quit │ Ctrl+L — address bar │ Alt+Left/Right — back/forward"
echo "Close:    ghostty-browse-tab.sh close --tab   (entire tab)"
echo "          ghostty-browse-tab.sh close --pane  (single pane)"
