#!/usr/bin/env bash
# Pre-commit gate — blocks git commit until events.jsonl has stage.passed(build).
#
# Events-authoritative (Phase 5):
#   - Valid log with stage.passed(build) → allow.
#   - Valid log without build pass        → deny with actionable message.
#   - Invalid log                         → deny (fail-closed on ambiguity).
#   - events.jsonl absent                 → skip (not a pipeline branch; direct
#     commits allowed — PR creation stays fail-closed via pre-bash-pr-gate.sh).
#
# Emergency escape hatch: CLAUDE_EVENTS_HOOK_SKIP=1 (logged to stderr).
#
# Trigger: PreToolUse:Bash (command contains "git commit")
set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$COMMAND" ] && exit 0

# Only match git commit commands
echo "$COMMAND" | grep -qE 'git\s+commit' || exit 0

# Skip merge commits and amend-only
echo "$COMMAND" | grep -qE '\-\-allow-empty|--amend\b.*--no-edit' && exit 0

# Emergency skip (logged + recorded to events.jsonl if available)
if [ "${CLAUDE_EVENTS_HOOK_SKIP:-0}" = "1" ]; then
  if . "${CLAUDE_PLUGIN_ROOT}/scripts/events.sh" 2>/dev/null \
     && _sd=$(events_state_dir 2>/dev/null) && [ -d "$_sd" ] && [ -f "$_sd/events.jsonl" ]; then
    # Corrupt events.jsonl would make `events_latest | jq` fail under pipefail.
    # Wrap in `|| true` so skip emission never blocks the bypass itself.
    _tid=$( { events_latest "$_sd" init 2>/dev/null || true; } | jq -r '.task_id // "unknown"' 2>/dev/null || echo "unknown")
    events_emit_gate_skipped "$_sd" "${_tid:-unknown}" "pre-bash-commit-gate" "CLAUDE_EVENTS_HOOK_SKIP" \
      "$(printf '%s' "$COMMAND" | head -c 200)" 2>/dev/null || true
  fi
  echo "pre-bash-commit-gate: CLAUDE_EVENTS_HOOK_SKIP=1 — skipping gate (logged to events.jsonl if available)" >&2
  exit 0
fi

# Must be in a git repo to enforce
git rev-parse --show-toplevel >/dev/null 2>&1 || exit 0

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)

# Repos without build config have no pipeline to gate — skip entirely.
# Why this runs BEFORE the Phase 4 events check: config repos like ~/.claude
# itself have no package.json and are not driven by /dev or /qa, so Phase 4's
# fail-closed-on-missing-events.jsonl must not apply to them.
if [ ! -f "$REPO_ROOT/package.json" ] && [ ! -f "$REPO_ROOT/turbo.json" ]; then
  exit 0
fi

# ---------- Phase 4: events.jsonl primary read (fail-closed when absent) ----------
if [ -f "${CLAUDE_PLUGIN_ROOT}/scripts/events.sh" ]; then
  # Load silently; failure here means the helper is broken — fall through.
  # shellcheck disable=SC1091
  if . "${CLAUDE_PLUGIN_ROOT}/scripts/events.sh" 2>/dev/null; then
    _EV_STATE_DIR=$(events_state_dir 2>/dev/null || echo "")
    if [ -n "$_EV_STATE_DIR" ] && [ -f "$_EV_STATE_DIR/events.jsonl" ]; then
      # Present — events is authoritative; validate and enforce.
      if ! events_validate "$_EV_STATE_DIR/events.jsonl" >/dev/null 2>&1; then
        echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: events.jsonl failed validation (Phase 2 fail-closed). Inspect '"$_EV_STATE_DIR"'/events.jsonl or set CLAUDE_EVENTS_HOOK_SKIP=1 for emergencies."}}'
        exit 0
      fi
      _EV_BUILD_PASS=$(events_latest "$_EV_STATE_DIR" "stage.passed" "stage=build" 2>/dev/null || echo "")
      if [ -z "$_EV_BUILD_PASS" ]; then
        echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: no stage.passed(build) event in '"$_EV_STATE_DIR"'/events.jsonl. Run /dev BUILD stage."}}'
        exit 0
      fi

      # --- Browser-verify evidence enforcement (UI changes must have screenshots) ---
      # Check if the staged diff includes UI files (.tsx/.jsx/.css/.svg)
      _UI_FILES=$(git diff --cached --name-only 2>/dev/null | grep -E '\.(tsx|jsx|css|svg)$' || true)
      if [ -n "$_UI_FILES" ]; then
        # UI files changed — evidence is mandatory
        _EV_ARRAY=$(printf '%s' "$_EV_BUILD_PASS" | jq -r '.evidence // [] | length' 2>/dev/null || echo "0")
        _DISK_COUNT=$(find "$_EV_STATE_DIR/evidence" -maxdepth 1 -name 'browser-verify-*.png' 2>/dev/null | wc -l | tr -d ' ' || echo "0")
        if [ "${_EV_ARRAY:-0}" = "0" ] && [ "${_DISK_COUNT:-0}" = "0" ]; then
          echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: UI files changed but no browser-verify screenshots found. Run agent-browser and save screenshots to '"$_EV_STATE_DIR"'/evidence/browser-verify-<phase>-step<NN>-<desc>.png before committing."}}'
          exit 0
        fi
      fi
      # Events-driven PASS — allow commit.
      exit 0
    fi
    # events.jsonl absent — warn only (direct commits outside pipeline are allowed).
    echo "pre-bash-commit-gate: no events.jsonl found — skipping gate (not a pipeline branch)" >&2
    exit 0
  fi
fi

exit 0
