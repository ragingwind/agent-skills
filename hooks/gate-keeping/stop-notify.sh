#!/usr/bin/env bash
# Stop hook: send a desktop notification when Claude finishes responding.
# Reads JSON from stdin (fields: cwd, stop_hook_active, last_assistant_message).
# Cross-platform: uses notify-send (Linux) or terminal-notifier (macOS).

INPUT=$(cat)

CWD=$(echo "$INPUT" | jq -r '.cwd')
PROJECT=$(echo "$CWD" | awk -F/ '{print $NF}')
RAW_MSG=$(echo "$INPUT" | jq -r '.last_assistant_message // ""')

# --- Context: branch, issue, PR ---
BRANCH=$(git -C "$CWD" branch --show-current 2>/dev/null)

# Issue number: events.jsonl init event is the source of truth.
ISSUE=""
if [ -f "$HOME/.claude/scripts/events.sh" ]; then
  if ( . "$HOME/.claude/scripts/events.sh" 2>/dev/null ); then
    _sd=$(cd "$CWD" && . "$HOME/.claude/scripts/events.sh" 2>/dev/null && events_state_dir 2>/dev/null || echo "")
    if [ -n "$_sd" ] && [ -f "$_sd/events.jsonl" ]; then
      ISSUE=$(cd "$CWD" && . "$HOME/.claude/scripts/events.sh" 2>/dev/null \
        && events_latest "$_sd" init 2>/dev/null \
        | jq -r '.issue_num // empty' 2>/dev/null || echo "")
    fi
  fi
fi

# PR number: from gh (non-blocking, skip if slow)
PR=$(gh pr view --repo "$(git -C "$CWD" remote get-url origin 2>/dev/null)" \
  --json number -q '.number' 2>/dev/null)

# Build context prefix: branch · #issue or PR
CONTEXT=""
[ -n "$BRANCH" ] && CONTEXT="$BRANCH"
if [ -n "$PR" ]; then
  CONTEXT="${CONTEXT:+$CONTEXT · }PR #${PR}"
elif [ -n "$ISSUE" ]; then
  CONTEXT="${CONTEXT:+$CONTEXT · }#${ISSUE}"
fi

# Title: project first, then context
if [ -n "$CONTEXT" ]; then
  TITLE="${PROJECT} · ${CONTEXT}"
else
  TITLE="$PROJECT"
fi

# Message: last assistant message snippet, fallback to empty
if [ -n "$RAW_MSG" ]; then
  MSG=$(echo "$RAW_MSG" | tr '\n' ' ' | cut -c1-100)
else
  MSG=""
fi

# --- Send notification (cross-platform) ---
if command -v notify-send &>/dev/null; then
  # Linux (libnotify)
  notify-send "Claude Code — ${TITLE}" "$MSG" --urgency=normal
elif command -v terminal-notifier &>/dev/null; then
  # macOS
  PARENT_PID=$(ps -o ppid= -p "$(ps -o ppid= -p "$(ps -o ppid= -p $$ | tr -d ' ')" | tr -d ' ')" | tr -d ' ')
  BID=$(osascript -e "tell application \"System Events\" to get bundle identifier of first process whose unix id is $PARENT_PID" 2>/dev/null)

  NOTIF_ARGS=(-title "Claude Code" -subtitle "$TITLE" -sound default)
  [ -n "$MSG" ] && NOTIF_ARGS+=(-message "$MSG")

  if [ -n "$BID" ] && ! echo "$BID" | grep -q error; then
    terminal-notifier "${NOTIF_ARGS[@]}" -sender "$BID" -activate "$BID"
  else
    terminal-notifier "${NOTIF_ARGS[@]}"
  fi
fi
