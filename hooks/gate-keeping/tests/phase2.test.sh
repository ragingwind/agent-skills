#!/usr/bin/env bash
# Phase 2 hook tests — verify events.jsonl primary-read and fail-closed behavior.
#
# Runs each hook in a sandboxed FAKE_HOME with a temp git repo, feeds the hook
# stdin, and asserts the JSON decision matches expectation.
set -euo pipefail

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

# ==============================================================
echo "== Phase 2: pre-bash-commit-gate.sh =="
SBX=$(mktemp -d)
trap "rm -rf '$SBX'" EXIT

# ---- T1: no events.jsonl → deny (Phase 5: fail-closed, no legacy escape hatch) ----
T_HOME="$SBX/t1"; _make_sandbox "$T_HOME"
OUT=$(_run_hook pre-bash-commit-gate.sh '{"tool_input":{"command":"git commit -m test"}}' "$T_HOME")
if echo "$OUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1 \
   && echo "$OUT" | grep -qF 'events.jsonl not found'; then
    ok "T1 absent events.jsonl → fail-closed deny"
else bad "T1 expected deny mentioning 'events.jsonl not found', got: $OUT"; fi

# ---- T2: events.jsonl present + valid + build.passed → allow ----
T_HOME="$SBX/t2"; _make_sandbox "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD"
(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    events_emit_init "$SD" "42-sample" "acme/repo" 42 "feat/sample" main main "$REPO_ROOT"
    export ORCHESTRATOR_TOKEN=$(cat "$SD/.orch-writer-token")
    events_emit_stage_started "$SD" "42-sample" builder build 1 "$(events_diff_hash main 2>/dev/null || echo 0000)"
    events_emit_stage_passed  "$SD" "42-sample" builder build 1 "$(events_diff_hash main 2>/dev/null || echo 0000)" "unit/integration tests green"
)
OUT=$(_run_hook pre-bash-commit-gate.sh '{"tool_input":{"command":"git commit -m test"}}' "$T_HOME")
if [ -z "$OUT" ]; then ok "T2 valid events with build pass → allow"
else bad "T2 expected allow, got: $OUT"; fi

# ---- T3: events.jsonl present but no build pass → deny ----
T_HOME="$SBX/t3"; _make_sandbox "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD"
(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    events_emit_init "$SD" "42-sample" "acme/repo" 42 "feat/sample" main main "$REPO_ROOT"
)
OUT=$(_run_hook pre-bash-commit-gate.sh '{"tool_input":{"command":"git commit -m test"}}' "$T_HOME")
if echo "$OUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; then
    ok "T3 missing build pass → deny"
else bad "T3 expected deny, got: $OUT"; fi

# ---- T4: corrupted events.jsonl → deny (fail-closed) ----
T_HOME="$SBX/t4"; _make_sandbox "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD"
echo 'not valid json' > "$SD/events.jsonl"
OUT=$(_run_hook pre-bash-commit-gate.sh '{"tool_input":{"command":"git commit -m test"}}' "$T_HOME")
if echo "$OUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; then
    ok "T4 corrupted events.jsonl → deny"
else bad "T4 expected deny on corrupt, got: $OUT"; fi

# ---- T5: CLAUDE_EVENTS_HOOK_SKIP=1 → bypass ----
T_HOME="$SBX/t5"; _make_sandbox "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD"
echo 'not valid json' > "$SD/events.jsonl"
OUT=$(
    cd "$T_HOME/repo"
    HOME="$T_HOME" CLAUDE_EVENTS_HOOK_SKIP=1 bash "$HOOKS_DIR/pre-bash-commit-gate.sh" \
      <<< '{"tool_input":{"command":"git commit -m test"}}' 2>/dev/null
)
if [ -z "$OUT" ]; then ok "T5 CLAUDE_EVENTS_HOOK_SKIP=1 bypasses"
else bad "T5 expected empty with skip=1, got: $OUT"; fi

# ==============================================================
echo "== Phase 2: pre-bash-pr-gate.sh =="

# ---- T6: events with all stages passed + review APPROVED + verify writer → allow ----
T_HOME="$SBX/t6"; _make_sandbox "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD"
(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    events_emit_init "$SD" "42-sample" "acme/repo" 42 "feat/sample" main main "$REPO_ROOT"
    export ORCHESTRATOR_TOKEN=$(cat "$SD/.orch-writer-token")
    DH=$(events_diff_hash main 2>/dev/null || echo 0000000000000000)
    events_emit_stage_started "$SD" "42-sample" builder  build  1 "$DH"
    events_emit_stage_passed  "$SD" "42-sample" builder  build  1 "$DH" "build ok"
    events_emit_stage_started "$SD" "42-sample" reviewer review 1 "$DH"
    events_emit_stage_passed  "$SD" "42-sample" reviewer review 1 "$DH" "APPROVED: ship it"
    events_emit_stage_started "$SD" "42-sample" builder  verify 1 "$DH"
    events_emit_stage_passed  "$SD" "42-sample" builder  verify 1 "$DH" "tia pass" builder '[]'
)
OUT=$(_run_hook pre-bash-pr-gate.sh '{"tool_input":{"command":"gh pr create --fill"}}' "$T_HOME")
if [ -z "$OUT" ]; then ok "T6 all stages pass + APPROVED + writer → allow"
else bad "T6 expected allow, got: $OUT"; fi

# ---- T7: review summary without APPROVED → deny ----
T_HOME="$SBX/t7"; _make_sandbox "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD"
(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    events_emit_init "$SD" "42-sample" "acme/repo" 42 "feat/sample" main main "$REPO_ROOT"
    export ORCHESTRATOR_TOKEN=$(cat "$SD/.orch-writer-token")
    DH=$(events_diff_hash main 2>/dev/null || echo 0000000000000000)
    events_emit_stage_passed "$SD" "42-sample" builder  build  1 "$DH" "build ok"
    events_emit_stage_passed "$SD" "42-sample" reviewer review 1 "$DH" "changes requested"
    events_emit_stage_passed "$SD" "42-sample" builder  verify 1 "$DH" "tia pass" builder '[]'
)
OUT=$(_run_hook pre-bash-pr-gate.sh '{"tool_input":{"command":"gh pr create --fill"}}' "$T_HOME")
if echo "$OUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; then
    ok "T7 review without APPROVED → deny"
else bad "T7 expected deny, got: $OUT"; fi

# ---- T8: verify without writer → emit helper already rejects; inject raw to simulate ----
T_HOME="$SBX/t8"; _make_sandbox "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD"
(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    events_emit_init "$SD" "42-sample" "acme/repo" 42 "feat/sample" main main "$REPO_ROOT"
    export ORCHESTRATOR_TOKEN=$(cat "$SD/.orch-writer-token")
    DH=$(events_diff_hash main 2>/dev/null || echo 0000000000000000)
    events_emit_stage_passed "$SD" "42-sample" builder  build  1 "$DH" "build ok"
    events_emit_stage_passed "$SD" "42-sample" reviewer review 1 "$DH" "APPROVED"
    # Manually write an invalid verify pass (missing writer) — validation should reject
    printf '%s\n' '{"schema_version":1,"ts":"2026-04-18T00:00:00Z","task_id":"42-sample","agent":"builder","type":"stage.passed","stage":"verify","iteration":1,"diff_hash":"'"$DH"'","evidence":[],"summary":"bad"}' >> "$SD/events.jsonl"
)
OUT=$(_run_hook pre-bash-pr-gate.sh '{"tool_input":{"command":"gh pr create --fill"}}' "$T_HOME")
if echo "$OUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; then
    ok "T8 verify without writer → validation denies"
else bad "T8 expected deny (invalid log), got: $OUT"; fi

# ---- T9: non-PR command → pass-through ----
T_HOME="$SBX/t9"; _make_sandbox "$T_HOME"
OUT=$(_run_hook pre-bash-pr-gate.sh '{"tool_input":{"command":"ls -la"}}' "$T_HOME")
if [ -z "$OUT" ]; then ok "T9 non-PR command → pass-through"
else bad "T9 expected empty, got: $OUT"; fi

# ==============================================================
echo "== Phase 6: content-addressed evidence verification =="

# Helper — stage the store_evidence.sh helper into the sandbox FAKE_HOME so
# the hook can source it.
_install_store_evidence() {
    local fake_home="$1"
    cp "${CLAUDE_PLUGIN_ROOT}/scripts/store_evidence.sh" "$fake_home/.claude/scripts/store_evidence.sh"
}

# Helper — compute first 8 chars of SHA-256 for a file's contents.
_hash8_file() {
    shasum -a 256 "$1" | awk '{print substr($1,1,8)}'
}

_seed_stages_with_evidence() {
    # Emits init + build-pass + review-APPROVED + verify-pass with the given
    # evidence JSON array. Must be called in a subshell that has HOME set
    # and events.sh sourced.
    local sd="$1" repo_root="$2" evidence_json="$3"
    events_emit_init "$sd" "42-sample" "acme/repo" 42 "feat/sample" main main "$repo_root"
    export ORCHESTRATOR_TOKEN=$(cat "$sd/.orch-writer-token")
    local DH=$(events_diff_hash main 2>/dev/null || echo 0000000000000000)
    events_emit_stage_passed "$sd" "42-sample" builder  build  1 "$DH" "build ok" ""      "$evidence_json"
    events_emit_stage_passed "$sd" "42-sample" reviewer review 1 "$DH" "APPROVED"
    events_emit_stage_passed "$sd" "42-sample" builder  verify 1 "$DH" "tia pass" builder "$evidence_json"
}

# ---- T10: evidence file exists + hash8 matches → allow ----
T_HOME="$SBX/t10"; _make_sandbox "$T_HOME"; _install_store_evidence "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD/evidence"
printf 'screenshot data v1\n' > "$SD/evidence/src.png"
H8_T10=$(_hash8_file "$SD/evidence/src.png")
FN_T10="browser-verify-step01.${H8_T10}.png"
mv "$SD/evidence/src.png" "$SD/evidence/$FN_T10"
(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    _seed_stages_with_evidence "$SD" "$REPO_ROOT" "$(jq -cn --arg f "$FN_T10" '[$f]')"
)
OUT=$(_run_hook pre-bash-pr-gate.sh '{"tool_input":{"command":"gh pr create --fill"}}' "$T_HOME")
if [ -z "$OUT" ]; then ok "T10 valid hash8 evidence → allow"
else bad "T10 expected allow, got: $OUT"; fi

# ---- T11: evidence file missing → deny ----
T_HOME="$SBX/t11"; _make_sandbox "$T_HOME"; _install_store_evidence "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD/evidence"
# Declare an evidence file that does NOT exist on disk.
(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    _seed_stages_with_evidence "$SD" "$REPO_ROOT" '["ghost-step.aabbccdd.png"]'
)
OUT=$(_run_hook pre-bash-pr-gate.sh '{"tool_input":{"command":"gh pr create --fill"}}' "$T_HOME")
if echo "$OUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1 \
   && echo "$OUT" | grep -qF 'evidence verification failed'; then
    ok "T11 missing evidence file → deny"
else bad "T11 expected deny on missing evidence, got: $OUT"; fi

# ---- T12: evidence file tampered (hash mismatch) → deny ----
T_HOME="$SBX/t12"; _make_sandbox "$T_HOME"; _install_store_evidence "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD/evidence"
# Declare correct filename for some content, then write DIFFERENT content at
# the same filename to simulate tampering.
printf 'original content\n' > "$SD/evidence/orig.png"
H8_T12=$(_hash8_file "$SD/evidence/orig.png")
rm "$SD/evidence/orig.png"
FN_T12="victim.${H8_T12}.png"
printf 'tampered content\n' > "$SD/evidence/$FN_T12"
(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    _seed_stages_with_evidence "$SD" "$REPO_ROOT" "$(jq -cn --arg f "$FN_T12" '[$f]')"
)
OUT=$(_run_hook pre-bash-pr-gate.sh '{"tool_input":{"command":"gh pr create --fill"}}' "$T_HOME")
if echo "$OUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1 \
   && echo "$OUT" | grep -qF 'evidence verification failed'; then
    ok "T12 tampered evidence (hash mismatch) → deny"
else bad "T12 expected deny on hash mismatch, got: $OUT"; fi

# ---- T13: Phase 6c — filename without hash8 suffix is rejected ----
T_HOME="$SBX/t13"; _make_sandbox "$T_HOME"; _install_store_evidence "$T_HOME"
REPO_ROOT="$T_HOME/repo"
SD=$(_state_dir_for "$T_HOME" "$REPO_ROOT")
mkdir -p "$SD/evidence"
printf 'legacy content\n' > "$SD/evidence/legacy-name.png"
(
    HOME="$T_HOME" . "$T_HOME/.claude/scripts/events.sh"
    _seed_stages_with_evidence "$SD" "$REPO_ROOT" '["legacy-name.png"]'
)
OUT=$(_run_hook pre-bash-pr-gate.sh '{"tool_input":{"command":"gh pr create --fill"}}' "$T_HOME")
if echo "$OUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1 \
   && echo "$OUT" | grep -qF 'evidence verification failed'; then
    ok "T13 unhashed filename (no hash8) → deny"
else bad "T13 expected deny for unhashed filename, got: $OUT"; fi

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
