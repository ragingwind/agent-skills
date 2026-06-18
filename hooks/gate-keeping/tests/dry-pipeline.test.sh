#!/usr/bin/env bash
# dry-pipeline.test.sh — reproduce Gap 2 (Phase 4.5).
#
# Goal: prove that after /dev SETUP creates events.jsonl with only an init
# event, pre-bash-commit-gate.sh and pre-bash-pr-gate.sh fail-close. This
# test documents the broken state that Phase 4.5 (stage event emissions in
# commands/dev.md and commands/qa.md) must fix.
#
# Pattern follows phase2.test.sh: per-test sandbox under FAKE_HOME containing
# a copy of events.sh, so the hook loads its helper from the sandbox.
set -uo pipefail

PASS=0
FAIL=0
GREEN=$'\033[32m'; RED=$'\033[31m'; RESET=$'\033[0m'
ok()  { printf '  %sok%s %s\n'   "$GREEN" "$RESET" "$1"; PASS=$((PASS + 1)); }
bad() { printf '  %sFAIL%s %s\n' "$RED"   "$RESET" "$1"; FAIL=$((FAIL + 1)); }

HOOKS_DIR="${HOOKS_DIR:-${CLAUDE_PLUGIN_ROOT}/hooks/gate-keeping}"
EVENTS_SH="${EVENTS_SH:-${CLAUDE_PLUGIN_ROOT}/scripts/events.sh}"
[ -x "$HOOKS_DIR/pre-bash-commit-gate.sh" ] || { echo "missing commit hook"; exit 1; }
[ -x "$HOOKS_DIR/pre-bash-pr-gate.sh" ]     || { echo "missing pr hook"; exit 1; }
[ -f "$EVENTS_SH" ]                         || { echo "missing events.sh"; exit 1; }

_make_sandbox() {
    local root="$1" branch="${2:-feat/dry}"
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
    local home="$1" repo_root="$2"
    (
        cd "$repo_root"
        HOME="$home" bash -c '. "'"$home"'/.claude/scripts/events.sh" && events_state_dir'
    )
}

_run_hook() {
    local hook="$1" input="$2" fake_home="$3"
    (
        cd "$fake_home/repo"
        HOME="$fake_home" bash "$HOOKS_DIR/$hook" <<< "$input"
    )
}

SBX=$(mktemp -d)
trap 'rm -rf "$SBX"' EXIT

# ======================================================================
echo "== dry-pipeline: reproducing Gap 2 (init-only events.jsonl) =="

T_HOME="$SBX/gap2"; _make_sandbox "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD"

(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    events_emit_init "$SD" "42-dry" "acme/dry" 42 "feat/dry" main main "$REPO_ROOT"
)

LINES=$(wc -l < "$SD/events.jsonl" | tr -d ' ')
if [ "$LINES" = "1" ]; then ok "SETUP-only state: events.jsonl has 1 event (init)"
else bad "SETUP-only state: expected 1 event, got $LINES"; fi

OUT=$(_run_hook pre-bash-commit-gate.sh '{"tool_input":{"command":"git commit -m test"}}' "$T_HOME")
if printf '%s' "$OUT" | grep -q '"permissionDecision":"deny"' \
   && printf '%s' "$OUT" | grep -q 'no stage.passed(build)'; then
    ok "Gap 2 reproduced: commit denied after SETUP-only init"
else
    bad "Gap 2 NOT reproduced — commit was allowed or denied for other reason. Output: $OUT"
fi

OUT=$(_run_hook pre-bash-pr-gate.sh '{"tool_input":{"command":"gh pr create --title x --body y"}}' "$T_HOME")
if printf '%s' "$OUT" | grep -q '"permissionDecision":"deny"'; then
    ok "PR gate also denies init-only state"
else
    bad "PR gate unexpectedly allowed init-only state. Output: $OUT"
fi

# ======================================================================
echo "== dry-pipeline: full emit sequence (what Phase 4.5 must produce) =="

T_HOME="$SBX/full"; _make_sandbox "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD"

(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    events_emit_init "$SD" "42-dry" "acme/dry" 42 "feat/dry" main main "$REPO_ROOT"
    export ORCHESTRATOR_TOKEN
    ORCHESTRATOR_TOKEN=$(cat "$SD/.orch-writer-token")
    DH=$(events_diff_hash main 2>/dev/null || echo "0000000000000000")
    events_emit_stage_started "$SD" "42-dry" builder  build  1 "$DH"
    events_emit_stage_passed  "$SD" "42-dry" builder  build  1 "$DH" "unit tests 12/12 passed"
)

OUT=$(_run_hook pre-bash-commit-gate.sh '{"tool_input":{"command":"git commit -m test"}}' "$T_HOME")
if [ -z "$OUT" ]; then ok "commit allowed after stage.passed(build)"
else bad "commit unexpectedly denied. Output: $OUT"; fi

(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    export ORCHESTRATOR_TOKEN
    ORCHESTRATOR_TOKEN=$(cat "$SD/.orch-writer-token")
    DH=$(events_diff_hash main 2>/dev/null || echo "0000000000000000")
    events_emit_stage_started "$SD" "42-dry" reviewer review 1 "$DH"
    events_emit_stage_passed  "$SD" "42-dry" reviewer review 1 "$DH" "APPROVED: ship it"
    events_emit_stage_started "$SD" "42-dry" builder  verify 1 "$DH"
    events_emit_stage_passed  "$SD" "42-dry" builder  verify 1 "$DH" "TIA pass" builder '[]'
)

OUT=$(_run_hook pre-bash-pr-gate.sh '{"tool_input":{"command":"gh pr create --title x --body y"}}' "$T_HOME")
if [ -z "$OUT" ]; then ok "PR create allowed after build + review(APPROVED) + verify(writer)"
else bad "PR create unexpectedly denied. Output: $OUT"; fi

# ======================================================================
echo "== dry-pipeline: negative — negated APPROVED rejected =="

T_HOME="$SBX/neg"; _make_sandbox "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD"

(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    events_emit_init "$SD" "42-dry" "acme/dry" 42 "feat/dry" main main "$REPO_ROOT"
    export ORCHESTRATOR_TOKEN
    ORCHESTRATOR_TOKEN=$(cat "$SD/.orch-writer-token")
    DH=$(events_diff_hash main 2>/dev/null || echo "0000000000000000")
    events_emit_stage_passed "$SD" "42-dry" builder  build  1 "$DH" "build ok"
    events_emit_stage_passed "$SD" "42-dry" reviewer review 1 "$DH" "NOT_APPROVED: critical findings"
    events_emit_stage_passed "$SD" "42-dry" builder  verify 1 "$DH" "TIA pass" builder '[]'
)

OUT=$(_run_hook pre-bash-pr-gate.sh '{"tool_input":{"command":"gh pr create --title x --body y"}}' "$T_HOME")
if printf '%s' "$OUT" | grep -q 'negation of APPROVED'; then
    ok "PR create denied on NOT_APPROVED summary"
else
    bad "PR create unexpectedly allowed or denied for other reason. Output: $OUT"
fi

# ======================================================================
echo
echo "=================="
echo "Passed: $PASS"
echo "Failed: $FAIL"
if [ "$FAIL" -gt 0 ]; then
    echo "SOME FAILURES"
    exit 1
fi
echo "ALL GREEN"
