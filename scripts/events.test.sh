#!/usr/bin/env bash
# events.test.sh — tests for scripts/events.sh
#
# Exercises: state_dir derivation, append lock atomicity, schema validation,
# writer-iff-verify (I4), first-event-init (I7), mirror offset bounds (I5),
# duplicate pass/fail (I2).
#
# Run: bash scripts/events.test.sh

set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd -P)
EVENTS_SH="$SCRIPT_DIR/events.sh"

if [ ! -f "$EVENTS_SH" ]; then
    echo "events.sh not found at $EVENTS_SH" >&2
    exit 2
fi

# shellcheck source=events.sh
source "$EVENTS_SH"

# ---------- tiny test harness ----------

PASS=0
FAIL=0
FAILED_NAMES=()

_ok()   { PASS=$((PASS + 1)); printf '  \033[32mok\033[0m %s\n' "$1"; }
_fail() { FAIL=$((FAIL + 1)); FAILED_NAMES+=("$1"); printf '  \033[31mFAIL\033[0m %s: %s\n' "$1" "$2"; }

# assert_eq <name> <expected> <actual>
assert_eq() {
    if [ "$2" = "$3" ]; then _ok "$1"
    else _fail "$1" "expected [$2] got [$3]"
    fi
}
# assert_contains <name> <haystack> <needle>
assert_contains() {
    case "$2" in
        *"$3"*) _ok "$1" ;;
        *)      _fail "$1" "[$2] does not contain [$3]" ;;
    esac
}
# assert_ok <name> <exit_code>
assert_ok() {
    if [ "$2" -eq 0 ]; then _ok "$1"
    else _fail "$1" "exit=$2"
    fi
}
# assert_not_ok <name> <exit_code>
assert_not_ok() {
    if [ "$2" -ne 0 ]; then _ok "$1"
    else _fail "$1" "exit=$2 (expected non-zero)"
    fi
}

# Run a command silently and return its exit code.
_silent() { "$@" >/dev/null 2>&1; return $?; }

# ---------- sandbox setup ----------

TMP_ROOT=$(mktemp -d -t events-test-XXXXXX) || { echo "mktemp failed" >&2; exit 2; }
trap 'rm -rf "$TMP_ROOT"' EXIT

REPO_DIR="$TMP_ROOT/repo"
mkdir -p "$REPO_DIR"
(
    cd "$REPO_DIR"
    git init -q -b main
    git config user.email test@example.com
    git config user.name  test
    echo init > README.md
    git add README.md
    git commit -q -m init
    git checkout -q -b feat/auth.v1
) || { echo "failed to init test repo" >&2; exit 2; }

# Override HOME so state_dir lands in the sandbox.
FAKE_HOME="$TMP_ROOT/home"
mkdir -p "$FAKE_HOME/.local/state/agent-skills"

# Helper: run in the test repo with FAKE_HOME.
in_repo() { ( cd "$REPO_DIR" && HOME="$FAKE_HOME" "$@" ); }

# ---------- section 1: state_dir ----------

echo "== state_dir =="

SD=$(in_repo bash -c 'source "'"$EVENTS_SH"'" && events_state_dir')
assert_ok "state_dir exits 0 inside repo" $?

# Expected components:
HOSTNAME_NORM=$(hostname | tr '[:upper:]' '[:lower:]' | sed 's/\./-/g')
REAL_REPO=$( (cd "$REPO_DIR" && pwd -P) )
PROJ_SLUG=$(printf '%s' "$REAL_REPO" | sed 's|/|-|g; s|\.|-|g')
BRANCH_SLUG_EXPECTED='feat-auth-v1'
EXPECTED="$FAKE_HOME/.local/state/agent-skills/${HOSTNAME_NORM}/${PROJ_SLUG}/${BRANCH_SLUG_EXPECTED}"

assert_eq "state_dir path correct (dot→dash in branch)" "$EXPECTED" "$SD"

# detached HEAD → error
(
    cd "$REPO_DIR"
    git checkout -q --detach 2>/dev/null
    HOME="$FAKE_HOME" bash -c 'source "'"$EVENTS_SH"'" && events_state_dir' >/dev/null 2>&1
    echo $?
    git checkout -q feat/auth.v1
) > "$TMP_ROOT/detached_rc" 2>&1
DETACHED_RC=$(head -n1 "$TMP_ROOT/detached_rc")
assert_not_ok "state_dir errors on detached HEAD" "$DETACHED_RC"

# Outside git → error
(
    cd "$TMP_ROOT"
    HOME="$FAKE_HOME" bash -c 'source "'"$EVENTS_SH"'" && events_state_dir' >/dev/null 2>&1
    echo $?
) > "$TMP_ROOT/nogit_rc" 2>&1
NOGIT_RC=$(head -n1 "$TMP_ROOT/nogit_rc")
assert_not_ok "state_dir errors outside git" "$NOGIT_RC"

# ---------- section 2: schema validation (validate_one) ----------

echo "== validate_one =="

TS='2026-04-18T00:00:00Z'
TID='123-test'

valid_init=$(jq -cn --arg ts "$TS" --arg tid "$TID" '{
    schema_version:1, ts:$ts, task_id:$tid, agent:"orchestrator", type:"init",
    repo:"acme/app", issue_num:123, branch:"feat/auth.v1", base_branch:"main",
    pr_target:"main", worktree_root:"/tmp/x", hostname:"host"
}')
events_validate_one "$valid_init"
assert_ok "valid init accepted" $?

bad_init_missing_repo=$(jq -cn --arg ts "$TS" --arg tid "$TID" '{
    schema_version:1, ts:$ts, task_id:$tid, agent:"orchestrator", type:"init",
    issue_num:123, branch:"feat/x", base_branch:"main", pr_target:"main",
    worktree_root:"/tmp/x", hostname:"host"
}')
events_validate_one "$bad_init_missing_repo"
assert_not_ok "init missing repo rejected" $?

bad_schema_version=$(jq -cn --arg ts "$TS" --arg tid "$TID" '{
    schema_version:2, ts:$ts, task_id:$tid, agent:"orchestrator", type:"init",
    repo:"a/b", issue_num:1, branch:"x", base_branch:"main", pr_target:"main",
    worktree_root:"/tmp", hostname:"host"
}')
events_validate_one "$bad_schema_version"
assert_not_ok "unknown schema_version rejected" $?

# I4: writer iff verify
passed_verify_good=$(jq -cn --arg ts "$TS" --arg tid "$TID" '{
    schema_version:1, ts:$ts, task_id:$tid, agent:"builder", type:"stage.passed",
    stage:"verify", iteration:1, diff_hash:"abc",
    writer:"builder", evidence:[], summary:"ok"
}')
events_validate_one "$passed_verify_good"
assert_ok "verify with writer=builder accepted" $?

passed_verify_no_writer=$(jq -cn --arg ts "$TS" --arg tid "$TID" '{
    schema_version:1, ts:$ts, task_id:$tid, agent:"builder", type:"stage.passed",
    stage:"verify", iteration:1, diff_hash:"abc", evidence:[], summary:"ok"
}')
events_validate_one "$passed_verify_no_writer"
assert_not_ok "verify without writer rejected (I4)" $?

passed_build_with_writer=$(jq -cn --arg ts "$TS" --arg tid "$TID" '{
    schema_version:1, ts:$ts, task_id:$tid, agent:"builder", type:"stage.passed",
    stage:"build", iteration:1, diff_hash:"abc",
    writer:"builder", evidence:[], summary:"ok"
}')
events_validate_one "$passed_build_with_writer"
assert_not_ok "build with writer rejected (I4 reversed)" $?

passed_verify_bad_writer=$(jq -cn --arg ts "$TS" --arg tid "$TID" '{
    schema_version:1, ts:$ts, task_id:$tid, agent:"builder", type:"stage.passed",
    stage:"verify", iteration:1, diff_hash:"abc",
    writer:"orchestrator", evidence:[], summary:"ok"
}')
events_validate_one "$passed_verify_bad_writer"
assert_not_ok "verify with writer=orchestrator rejected" $?

# bad stage name
bad_stage=$(jq -cn --arg ts "$TS" --arg tid "$TID" '{
    schema_version:1, ts:$ts, task_id:$tid, agent:"builder", type:"stage.passed",
    stage:"deploy", iteration:1, diff_hash:"abc", evidence:[], summary:"ok"
}')
events_validate_one "$bad_stage"
assert_not_ok "unknown stage rejected" $?

# unknown event type
unknown_type=$(jq -cn --arg ts "$TS" --arg tid "$TID" '{
    schema_version:1, ts:$ts, task_id:$tid, agent:"orchestrator", type:"whatever"
}')
events_validate_one "$unknown_type"
assert_not_ok "unknown event type rejected" $?

# ---------- section 3: append + latest ----------

echo "== append + latest =="

SD_TEST="$TMP_ROOT/state"
events_append "$SD_TEST" "$valid_init"
assert_ok "append init returns 0" $?

[ -f "$SD_TEST/events.jsonl" ]
assert_ok "events.jsonl created" $?

LINE_COUNT=$(wc -l < "$SD_TEST/events.jsonl" | tr -d ' ')
assert_eq "events.jsonl has 1 line after init" "1" "$LINE_COUNT"

# Append build started + passed
build_started=$(jq -cn --arg ts "$TS" --arg tid "$TID" '{
    schema_version:1, ts:$ts, task_id:$tid, agent:"builder", type:"stage.started",
    stage:"build", iteration:1, diff_hash:"deadbeef"
}')
build_passed=$(jq -cn --arg ts "$TS" --arg tid "$TID" '{
    schema_version:1, ts:$ts, task_id:$tid, agent:"builder", type:"stage.passed",
    stage:"build", iteration:1, diff_hash:"deadbeef",
    evidence:["h1","h2"], summary:"unit ok"
}')
events_append "$SD_TEST" "$build_started"
events_append "$SD_TEST" "$build_passed"

LATEST_BUILD=$(events_latest "$SD_TEST" "stage.passed" "stage=build")
SUMMARY=$(echo "$LATEST_BUILD" | jq -r '.summary')
assert_eq "latest stage.passed build summary" "unit ok" "$SUMMARY"

# Invalid payload rejected by append
bad_payload='{"schema_version":1}'
events_append "$SD_TEST" "$bad_payload"
assert_not_ok "append rejects invalid payload" $?

# File must have only 3 lines (bad append not persisted)
LINE_COUNT=$(wc -l < "$SD_TEST/events.jsonl" | tr -d ' ')
assert_eq "events.jsonl still 3 lines after rejected append" "3" "$LINE_COUNT"

# latest with no match → empty
NO_MATCH=$(events_latest "$SD_TEST" "finalize.pr_ready")
assert_eq "latest no match is empty" "" "$NO_MATCH"

# ---------- section 4: lock concurrency smoke ----------

echo "== lock concurrency =="

# Fire 10 concurrent appends; expect exactly 13 total lines (3 + 10).
CONC_SD="$TMP_ROOT/conc"
events_append "$CONC_SD" "$valid_init"
events_append "$CONC_SD" "$build_started"
events_append "$CONC_SD" "$build_passed"

for i in 1 2 3 4 5 6 7 8 9 10; do
    (
        source "$EVENTS_SH"
        p=$(jq -cn --arg ts "$TS" --arg tid "$TID" --argjson i "$i" '{
            schema_version:1, ts:$ts, task_id:$tid, agent:"orchestrator",
            type:"mirror.posted", target:"pr", number:1, mirrors_event_offset:$i
        }')
        events_append "$CONC_SD" "$p" >/dev/null 2>&1
    ) &
done
wait

LINE_COUNT=$(wc -l < "$CONC_SD/events.jsonl" | tr -d ' ')
assert_eq "lock: 3 base + 10 concurrent appends → 13 lines" "13" "$LINE_COUNT"

# Each line must be valid JSON.
BAD_JSON=$(awk 'NF' "$CONC_SD/events.jsonl" \
    | while IFS= read -r l; do echo "$l" | jq -e . >/dev/null 2>&1 || echo BAD; done)
assert_eq "all lines valid JSON" "" "$BAD_JSON"

# ---------- section 5: validate full log (I1-I7) ----------

echo "== validate (full) =="

GOOD_LOG="$TMP_ROOT/good.jsonl"
{
    echo "$valid_init"
    echo "$build_started"
    echo "$build_passed"
} > "$GOOD_LOG"
events_validate "$GOOD_LOG"
assert_ok "good log validates" $?

# I7: first event not init
BAD_I7="$TMP_ROOT/bad_i7.jsonl"
{
    echo "$build_started"
    echo "$valid_init"
} > "$BAD_I7"
events_validate "$BAD_I7" 2>/dev/null
assert_not_ok "I7 first-event-init violation detected" $?

# I2: duplicate (stage, iter) pass/fail
BAD_I2="$TMP_ROOT/bad_i2.jsonl"
{
    echo "$valid_init"
    echo "$build_passed"
    echo "$build_passed"
} > "$BAD_I2"
events_validate "$BAD_I2" 2>/dev/null
assert_not_ok "I2 duplicate pass/fail detected" $?

# I5: mirror offset out of range (points to a future/nonexistent line)
bad_mirror=$(jq -cn --arg ts "$TS" --arg tid "$TID" '{
    schema_version:1, ts:$ts, task_id:$tid, agent:"orchestrator",
    type:"mirror.posted", target:"pr", number:1, mirrors_event_offset:99
}')
BAD_I5="$TMP_ROOT/bad_i5.jsonl"
{
    echo "$valid_init"
    echo "$bad_mirror"
} > "$BAD_I5"
events_validate "$BAD_I5" 2>/dev/null
assert_not_ok "I5 mirror offset violation detected" $?

# Empty log rejected
EMPTY="$TMP_ROOT/empty.jsonl"
: > "$EMPTY"
events_validate "$EMPTY" 2>/dev/null
assert_not_ok "empty log rejected" $?

# ---------- section 6: diff_hash ----------

echo "== diff_hash =="

HASH=$(in_repo bash -c 'source "'"$EVENTS_SH"'" && events_diff_hash main')
assert_eq "diff_hash length == 16 on clean branch" "16" "${#HASH}"

(
    cd "$REPO_DIR"
    echo "change" > README.md
)
HASH2=$(in_repo bash -c 'source "'"$EVENTS_SH"'" && events_diff_hash main')
# After modifying working tree, diff vs main changes → hash changes.
if [ "$HASH" != "$HASH2" ]; then _ok "diff_hash changes with working-tree diff"
else _fail "diff_hash changes with working-tree diff" "hash unchanged [$HASH]"
fi

# ---------- section 7: emit helpers ----------

echo "== emit helpers =="

EMIT_SD="$TMP_ROOT/emit"

events_emit_init "$EMIT_SD" "123-feat-auth" "acme/app" 123 "feat/auth" "main" "main" "/Users/x/app"
assert_ok "emit_init appends" $?

# Phase 4: export orchestrator token so stage.passed/failed emits are accepted.
if [ -f "$EMIT_SD/.orch-writer-token" ]; then
    export ORCHESTRATOR_TOKEN=$(cat "$EMIT_SD/.orch-writer-token")
fi

events_emit_stage_started "$EMIT_SD" "123-feat-auth" "builder" "build" 1 "dh0001"
assert_ok "emit_stage_started appends" $?

events_emit_stage_passed "$EMIT_SD" "123-feat-auth" "builder" "build" 1 "dh0001" "unit 10/10"
assert_ok "emit_stage_passed (non-verify, no writer) appends" $?

events_emit_stage_passed "$EMIT_SD" "123-feat-auth" "builder" "verify" 1 "dh0001" "tia ok" "builder" '["sha1","sha2"]'
assert_ok "emit_stage_passed (verify with writer) appends" $?

# verify stage without writer must fail
events_emit_stage_passed "$EMIT_SD" "123-feat-auth" "builder" "verify" 2 "dh0001" "tia ok" 2>/dev/null
assert_not_ok "emit_stage_passed verify without writer rejected" $?

# non-verify with writer must fail
events_emit_stage_passed "$EMIT_SD" "123-feat-auth" "builder" "build" 2 "dh0001" "unit ok" "builder" 2>/dev/null
assert_not_ok "emit_stage_passed non-verify with writer rejected" $?

events_emit_stage_failed "$EMIT_SD" "123-feat-auth" "reviewer" "review" 1 "dh0001" "3 CRITICAL findings"
assert_ok "emit_stage_failed appends" $?

events_emit_plan_posted "$EMIT_SD" "123-feat-auth" "dev" "hash0012345678ab" "https://github.com/x/y/issues/123#issuecomment-1"
assert_ok "emit_plan_posted appends" $?

events_emit_mirror_posted "$EMIT_SD" "123-feat-auth" "issue" 123 9999 2
assert_ok "emit_mirror_posted appends" $?

events_emit_finalize_pr_ready "$EMIT_SD" "123-feat-auth" 456 "https://github.com/x/y/pull/456"
assert_ok "emit_finalize_pr_ready appends" $?

# Full validation of emitted log
events_validate "$EMIT_SD/events.jsonl"
assert_ok "emitted log passes full validation" $?

# Line count sanity (1 init + 1 started + 2 passed + 1 failed + 1 plan + 1 mirror + 1 finalize = 8)
LINE_COUNT=$(wc -l < "$EMIT_SD/events.jsonl" | tr -d ' ')
assert_eq "emit log has 8 lines" "8" "$LINE_COUNT"

# ---------- section 7b: orchestrator token guard ----------

echo "== orchestrator token guard =="

# Token file must exist after init.
[ -f "$EMIT_SD/.orch-writer-token" ]
assert_ok "token file created by emit_init" $?

# Token file must be mode 0400 (read-only by owner) — portable across Linux + macOS.
TOK_MODE=$(stat -f '%p' "$EMIT_SD/.orch-writer-token" 2>/dev/null | awk '{print substr($0, length-2)}')
if [ -z "$TOK_MODE" ]; then
    TOK_MODE=$(stat -c '%a' "$EMIT_SD/.orch-writer-token" 2>/dev/null)
fi
assert_eq "token file mode is 400" "400" "$TOK_MODE"

# Missing ORCHESTRATOR_TOKEN → stage.passed rejected, log unchanged.
GUARD_SD="$TMP_ROOT/guard"
events_emit_init "$GUARD_SD" "999-guard" "acme/app" 999 "feat/g" "main" "main" "/x"
LINES_PRE=$(wc -l < "$GUARD_SD/events.jsonl" | tr -d ' ')
(
    unset ORCHESTRATOR_TOKEN
    events_emit_stage_passed "$GUARD_SD" "999-guard" builder build 1 "dh" "ok" 2>/dev/null
)
RC=$?
LINES_POST=$(wc -l < "$GUARD_SD/events.jsonl" | tr -d ' ')
assert_not_ok "stage_passed without token rejected" "$RC"
assert_eq "log unchanged after rejected emit" "$LINES_PRE" "$LINES_POST"

# Wrong token → rejected.
(
    export ORCHESTRATOR_TOKEN="bogus-token-xyz"
    events_emit_stage_passed "$GUARD_SD" "999-guard" builder build 1 "dh" "ok" 2>/dev/null
)
RC=$?
LINES_POST2=$(wc -l < "$GUARD_SD/events.jsonl" | tr -d ' ')
assert_not_ok "stage_passed with wrong token rejected" "$RC"
assert_eq "log unchanged after wrong-token emit" "$LINES_PRE" "$LINES_POST2"

# Correct token → accepted, log grows.
(
    export ORCHESTRATOR_TOKEN=$(cat "$GUARD_SD/.orch-writer-token")
    events_emit_stage_passed "$GUARD_SD" "999-guard" builder build 1 "dh" "ok"
)
RC=$?
LINES_POST3=$(wc -l < "$GUARD_SD/events.jsonl" | tr -d ' ')
assert_ok "stage_passed with correct token accepted" "$RC"
assert_eq "log grows by 1 after accepted emit" "$((LINES_PRE + 1))" "$LINES_POST3"

# stage_failed with correct token → accepted.
(
    export ORCHESTRATOR_TOKEN=$(cat "$GUARD_SD/.orch-writer-token")
    events_emit_stage_failed "$GUARD_SD" "999-guard" builder build 2 "dh" "unit red"
)
RC=$?
assert_ok "stage_failed with correct token accepted" "$RC"

# ---------- section 7c: gate.skipped emission ----------

echo "== gate.skipped ==";

SKIP_SD="$TMP_ROOT/skip"
events_emit_init "$SKIP_SD" "888-skip" "acme/app" 888 "feat/s" "main" "main" "/x"
LINES_PRE=$(wc -l < "$SKIP_SD/events.jsonl" | tr -d ' ')

events_emit_gate_skipped "$SKIP_SD" "888-skip" "pre-bash-commit-gate" "CLAUDE_EVENTS_HOOK_SKIP" "git commit -m test"
assert_ok "emit_gate_skipped with command accepted" $?
LAST_TYPE=$(tail -1 "$SKIP_SD/events.jsonl" | jq -r '.type')
assert_eq "last event type is gate.skipped" "gate.skipped" "$LAST_TYPE"

events_emit_gate_skipped "$SKIP_SD" "888-skip" "stop-gate" "CLAUDE_EVENTS_HOOK_SKIP"
assert_ok "emit_gate_skipped without command accepted" $?

# Log still validates with gate.skipped events.
events_validate "$SKIP_SD/events.jsonl"
assert_ok "log with gate.skipped validates" $?

# ---------- summary ----------

echo
echo "=================="
echo "Passed: $PASS"
echo "Failed: $FAIL"
if [ "$FAIL" -gt 0 ]; then
    echo "Failed tests:"
    for n in "${FAILED_NAMES[@]}"; do echo "  - $n"; done
    exit 1
fi
echo "ALL GREEN"
