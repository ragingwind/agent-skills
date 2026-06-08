#!/usr/bin/env bash
# Stop completion gate — warns about incomplete evidence chain
# Trigger: Stop event (non-blocking)
set -euo pipefail

INPUT=$(cat)

# Prevent infinite loop
ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)
[ "$ACTIVE" = "true" ] && exit 0

# Phase 4 emergency skip (logged + recorded to events.jsonl if available)
if [ "${CLAUDE_EVENTS_HOOK_SKIP:-0}" = "1" ]; then
  if . "$HOME/.claude/scripts/events.sh" 2>/dev/null \
     && _sd=$(events_state_dir 2>/dev/null) && [ -d "$_sd" ] && [ -f "$_sd/events.jsonl" ]; then
    # Corrupt events.jsonl would make `events_latest | jq` fail under pipefail.
    _tid=$( { events_latest "$_sd" init 2>/dev/null || true; } | jq -r '.task_id // "unknown"' 2>/dev/null || echo "unknown")
    events_emit_gate_skipped "$_sd" "${_tid:-unknown}" "stop-gate" "CLAUDE_EVENTS_HOOK_SKIP" \
      "stop" 2>/dev/null || true
  fi
  echo "stop-gate: CLAUDE_EVENTS_HOOK_SKIP=1 — skipping gate (logged to events.jsonl if available)" >&2
  exit 0
fi

# Must be in a git repo
git rev-parse --show-toplevel >/dev/null 2>&1 || exit 0

# Events-authoritative (Phase 5): completeness is enforced by events.jsonl + gate hooks.
# stop-gate no longer emits warnings — the pre-commit / pre-PR gates are authoritative.
exit 0
