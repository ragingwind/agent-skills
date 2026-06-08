#!/usr/bin/env bash
# Phase 4 hook tests — verify fail-closed entry, word-boundary APPROVED,
# gate.skipped event emission, and orchestrator-token guard behavior.
#
# Runs each hook in a sandboxed FAKE_HOME with a temp git repo, feeds the hook
# stdin, and asserts the JSON decision matches expectation.
set -uo pipefail

PASS=0
FAIL=0
GREEN='\033[32m'; RED='\033[31m'; RESET='\033[0m'

# Path to the real hooks and helper (absolute)
HOOKS_DIR="${HOOKS_DIR:-${CLAUDE_PLUGIN_ROOT}/hooks/gate-keeping}"
EVENTS_SH="${EVENTS_SH:-${CLAUDE_PLUGIN_ROOT}/scripts/events.sh}"

ok()   { printf "  ${GREEN}ok${RESET} %s\n" "$1"; PASS=$((PASS+1)); }
bad()  { printf "  ${RED}FAIL${RESET} %s\n" "$1"; FAIL=$((FAIL+1)); }

# _run_hook <hook-basename> <stdin-json> <fake-home>
#   echoes stdout (hook decision JSON or empty for allow).
_run_hook() {
    local hook="$1" input="$2" fake_home="$3"
    (
        cd "$fake_home/repo"
        HOME="$fake_home" bash "$HOOKS_DIR/$hook" <<< "$input"
    )
}

_make_sandbox() {
    local root="$1" branch="${2:-feat/sample}"
    rm -rf "$root"
    mkdir -p "$root/.claude/scripts"
    cp "$EVENTS_SH" "$root/.claude/scripts/events.sh"
    mkdir -p "$root/repo"
    (
        cd "$root/repo"
        git init -q -b main
        touch package.json
        git add package.json
        git -c user.email=t@t -c user.name=t commit -q -m init
        git checkout -q -b "$branch"
    )
}

_state_dir_for() {
    # Call the real events_state_dir from inside the repo under the given HOME,
    # so realpath canonicalization matches what the hook will resolve.
    local home="$1" repo_root="$2"
    (
        cd "$repo_root"
        HOME="$home" bash -c '. "'"$home"'/.claude/scripts/events.sh" && events_state_dir'
    )
}

# Helper: emit a full happy-path event chain (init → build.passed → review.passed
# with given review summary → verify.passed with writer=builder) into $SD.
# $SUMMARY is jq-safe (no double quotes inside).
_emit_happy_path() {
    local home="$1" sd="$2" review_summary="$3"
    (
        HOME="$home" . "$home/.claude/scripts/events.sh"
        events_emit_init "$sd" "42-sample" "acme/repo" 42 "feat/sample" main main "$home/repo"
        # Load the orchestrator token, then export for guard.
        if [ -f "$sd/.orch-writer-token" ]; then
            export ORCHESTRATOR_TOKEN=$(cat "$sd/.orch-writer-token")
        fi
        DH=$(events_diff_hash main 2>/dev/null || echo 0000000000000000)
        events_emit_stage_started "$sd" "42-sample" builder  build  1 "$DH"
        events_emit_stage_passed  "$sd" "42-sample" builder  build  1 "$DH" "build ok"
        events_emit_stage_started "$sd" "42-sample" reviewer review 1 "$DH"
        events_emit_stage_passed  "$sd" "42-sample" reviewer review 1 "$DH" "$review_summary"
        events_emit_stage_started "$sd" "42-sample" builder  verify 1 "$DH"
        events_emit_stage_passed  "$sd" "42-sample" builder  verify 1 "$DH" "tia pass" builder '[]'
    )
}

# ==============================================================
echo "== Phase 4: fail-closed entry (T10) =="
SBX=$(mktemp -d)
trap "rm -rf '$SBX'" EXIT

# ---- T10a: no events.jsonl → commit-gate denies (Phase 5: no legacy escape hatch) ----
T_HOME="$SBX/t10a"; _make_sandbox "$T_HOME"
OUT=$(_run_hook pre-bash-commit-gate.sh '{"tool_input":{"command":"git commit -m test"}}' "$T_HOME")
if echo "$OUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1 \
   && echo "$OUT" | grep -qF 'events.jsonl not found'; then
    ok "T10a commit-gate: absent events.jsonl → deny"
else
    bad "T10a expected deny mentioning 'events.jsonl not found', got: $OUT"
fi

# ---- T10b: no events.jsonl → pr-gate denies (Phase 5: no legacy escape hatch) ----
T_HOME="$SBX/t10b"; _make_sandbox "$T_HOME"
OUT=$(_run_hook pre-bash-pr-gate.sh '{"tool_input":{"command":"gh pr create --fill"}}' "$T_HOME")
if echo "$OUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1 \
   && echo "$OUT" | grep -qF 'events.jsonl not found'; then
    ok "T10b pr-gate: absent events.jsonl → deny"
else
    bad "T10b expected deny mentioning 'events.jsonl not found', got: $OUT"
fi

# ==============================================================
echo "== Phase 5: CLAUDE_EVENTS_HOOK_LEGACY is a no-op (T11) =="

# ---- T11a: CLAUDE_EVENTS_HOOK_LEGACY=1 must NOT bypass fail-closed ----
T_HOME="$SBX/t11a"; _make_sandbox "$T_HOME"
OUT=$(
    cd "$T_HOME/repo"
    HOME="$T_HOME" CLAUDE_EVENTS_HOOK_LEGACY=1 bash "$HOOKS_DIR/pre-bash-commit-gate.sh" \
      <<< '{"tool_input":{"command":"git commit -m test"}}' 2>/dev/null
)
if echo "$OUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1 \
   && echo "$OUT" | grep -qF 'events.jsonl not found'; then
    ok "T11a commit-gate: LEGACY=1 is ignored — still fail-closed when events.jsonl absent"
else
    bad "T11a expected LEGACY=1 to be no-op (still deny), got: $OUT"
fi

# ---- T11b: same for pr-gate ----
T_HOME="$SBX/t11b"; _make_sandbox "$T_HOME"
OUT=$(
    cd "$T_HOME/repo"
    HOME="$T_HOME" CLAUDE_EVENTS_HOOK_LEGACY=1 bash "$HOOKS_DIR/pre-bash-pr-gate.sh" \
      <<< '{"tool_input":{"command":"gh pr create --fill"}}' 2>/dev/null
)
if echo "$OUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1 \
   && echo "$OUT" | grep -qF 'events.jsonl not found'; then
    ok "T11b pr-gate: LEGACY=1 is ignored — still fail-closed when events.jsonl absent"
else
    bad "T11b expected LEGACY=1 to be no-op (still deny), got: $OUT"
fi

# ==============================================================
echo "== Phase 4: APPROVED word-boundary negative (T12) =="

for SUMMARY in \
    "NOT_APPROVED: issues found" \
    "Status: disapproved" \
    "not approved" \
    "UNAPPROVED" \
    "DISAPPROVED"
do
    T_HOME="$SBX/t12-$(echo -n "$SUMMARY" | md5 2>/dev/null || echo -n "$SUMMARY" | md5sum | awk '{print $1}')"
    _make_sandbox "$T_HOME"
    REPO_ROOT="$T_HOME/repo"
    SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
    mkdir -p "$SD"
    _emit_happy_path "$T_HOME" "$SD" "$SUMMARY"
    OUT=$(_run_hook pre-bash-pr-gate.sh '{"tool_input":{"command":"gh pr create --fill"}}' "$T_HOME")
    if echo "$OUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; then
        ok "T12 APPROVED-negative '$SUMMARY' → deny"
    else
        bad "T12 expected deny for '$SUMMARY', got: $OUT"
    fi
done

# ==============================================================
echo "== Phase 4: APPROVED word-boundary positive (T13) =="

for SUMMARY in \
    "APPROVED" \
    "- APPROVED: all checks pass" \
    "(APPROVED)" \
    "approved"
do
    T_HOME="$SBX/t13-$(echo -n "$SUMMARY" | md5 2>/dev/null || echo -n "$SUMMARY" | md5sum | awk '{print $1}')"
    _make_sandbox "$T_HOME"
    REPO_ROOT="$T_HOME/repo"
    SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
    mkdir -p "$SD"
    _emit_happy_path "$T_HOME" "$SD" "$SUMMARY"
    OUT=$(_run_hook pre-bash-pr-gate.sh '{"tool_input":{"command":"gh pr create --fill"}}' "$T_HOME")
    if [ -z "$OUT" ]; then
        ok "T13 APPROVED-positive '$SUMMARY' → allow"
    else
        bad "T13 expected allow for '$SUMMARY', got: $OUT"
    fi
done

# ==============================================================
echo "== Phase 4: gate.skipped emission (T14) =="

T_HOME="$SBX/t14"; _make_sandbox "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD"
(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    events_emit_init "$SD" "42-sample" "acme/repo" 42 "feat/sample" main main "$REPO_ROOT"
)
LINES_BEFORE=$(wc -l < "$SD/events.jsonl" | tr -d ' ')
(
    cd "$T_HOME/repo"
    HOME="$T_HOME" CLAUDE_EVENTS_HOOK_SKIP=1 bash "$HOOKS_DIR/pre-bash-commit-gate.sh" \
      <<< '{"tool_input":{"command":"git commit -m test"}}' 2>/dev/null
) >/dev/null
LINES_AFTER=$(wc -l < "$SD/events.jsonl" | tr -d ' ')
LAST_TYPE=$(tail -1 "$SD/events.jsonl" | jq -r '.type')
if [ "$LINES_AFTER" -eq $((LINES_BEFORE + 1)) ] && [ "$LAST_TYPE" = "gate.skipped" ]; then
    ok "T14 gate.skipped appended on CLAUDE_EVENTS_HOOK_SKIP=1"
else
    bad "T14 expected 1 new line with type=gate.skipped, got LINES=$LINES_BEFORE→$LINES_AFTER type=$LAST_TYPE"
fi
# Validate full log remains green after skip emission.
(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    events_validate "$SD/events.jsonl" >/dev/null 2>&1
)
if [ "$?" -eq 0 ]; then
    ok "T14 events_validate green after gate.skipped append"
else
    bad "T14 events_validate failed after gate.skipped append"
fi

# ==============================================================
echo "== Phase 4: orchestrator token guard (T15 missing, T16 ok) =="

# ---- T15: ORCHESTRATOR_TOKEN missing → stage_passed rejected, log unchanged ----
T_HOME="$SBX/t15"; _make_sandbox "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD"
(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    events_emit_init "$SD" "42-sample" "acme/repo" 42 "feat/sample" main main "$REPO_ROOT"
) >/dev/null 2>&1
LINES_BEFORE=$(wc -l < "$SD/events.jsonl" | tr -d ' ')
(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    unset ORCHESTRATOR_TOKEN
    events_emit_stage_passed "$SD" "42-sample" builder build 1 "dh0000" "build ok" 2>/dev/null
    echo "exit=$?"
) > "$SBX/t15.out" 2>&1
LINES_AFTER=$(wc -l < "$SD/events.jsonl" | tr -d ' ')
if grep -q '^exit=1$' "$SBX/t15.out" && [ "$LINES_AFTER" -eq "$LINES_BEFORE" ]; then
    ok "T15 emit_stage_passed rejects missing ORCHESTRATOR_TOKEN; log unchanged"
else
    bad "T15 expected exit=1 and no log change, got $(cat "$SBX/t15.out") LINES=$LINES_BEFORE→$LINES_AFTER"
fi

# ---- T16: ORCHESTRATOR_TOKEN correct → stage_passed accepted ----
T_HOME="$SBX/t16"; _make_sandbox "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD"
(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    events_emit_init "$SD" "42-sample" "acme/repo" 42 "feat/sample" main main "$REPO_ROOT"
) >/dev/null 2>&1
LINES_BEFORE=$(wc -l < "$SD/events.jsonl" | tr -d ' ')
(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    export ORCHESTRATOR_TOKEN=$(cat "$SD/.orch-writer-token")
    events_emit_stage_passed "$SD" "42-sample" builder build 1 "dh0000" "build ok"
    echo "exit=$?"
) > "$SBX/t16.out" 2>&1
LINES_AFTER=$(wc -l < "$SD/events.jsonl" | tr -d ' ')
if grep -q '^exit=0$' "$SBX/t16.out" && [ "$LINES_AFTER" -eq $((LINES_BEFORE + 1)) ]; then
    ok "T16 emit_stage_passed accepted with correct ORCHESTRATOR_TOKEN"
else
    bad "T16 expected exit=0 and +1 line, got $(cat "$SBX/t16.out") LINES=$LINES_BEFORE→$LINES_AFTER"
fi

# ==============================================================
echo
echo "=================="
echo "Passed: $PASS"
echo "Failed: $FAIL"
if [ "$FAIL" -eq 0 ]; then
    echo "ALL GREEN"
    exit 0
else
    echo "FAIL"
    exit 1
fi
