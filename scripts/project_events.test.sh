#!/usr/bin/env bash
# project_events.sh tests — status + format + post (with gh mock).
set -u

PASS=0
FAIL=0
GREEN='\033[32m'; RED='\033[31m'; RESET='\033[0m'
ok()  { printf "  ${GREEN}ok${RESET} %s\n" "$1"; PASS=$((PASS+1)); }
bad() { printf "  ${RED}FAIL${RESET} %s\n" "$1"; FAIL=$((FAIL+1)); }

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd -P)

SBX=$(mktemp -d)
trap "rm -rf '$SBX'" EXIT

# Shared setup — copy the scripts-under-test from this repo, not the author's home
FAKE_HOME="$SBX/home"
mkdir -p "$FAKE_HOME/.claude/scripts"
cp "$SCRIPT_DIR/events.sh"         "$FAKE_HOME/.claude/scripts/events.sh"
cp "$SCRIPT_DIR/project_events.sh" "$FAKE_HOME/.claude/scripts/project_events.sh"
chmod +x "$FAKE_HOME/.claude/scripts/"*.sh

# project_events.sh resolves events.sh via ${CLAUDE_PLUGIN_ROOT}/scripts/; point it
# at the sandbox copy so the test exercises the same path the plugin uses.
export CLAUDE_PLUGIN_ROOT="$FAKE_HOME/.claude"

# A fake gh that captures arguments and returns a synthetic URL
BIN_DIR="$SBX/bin"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/gh" <<'GHSTUB'
#!/usr/bin/env bash
# Record what was called
echo "$@" >> "$GH_LOG"
case "$1 $2" in
    "pr comment"|"issue comment")
        # emit a synthetic URL ending in #issuecomment-<rand>
        N=$RANDOM
        echo "https://github.com/acme/repo/issues/42#issuecomment-${N}"
        ;;
    "pr list")
        # No PR exists → return empty
        echo ""
        ;;
    *)
        echo "gh stub: unexpected args: $*" >&2
        exit 2
        ;;
esac
GHSTUB
chmod +x "$BIN_DIR/gh"

# Create a git repo and populate events.jsonl
REPO="$SBX/repo"
mkdir -p "$REPO"
(
    cd "$REPO"
    git init -q -b main
    touch README
    git add README
    git -c user.email=t@t -c user.name=t commit -q -m init
    git checkout -q -b feat/one
)

HOME="$FAKE_HOME" . "$FAKE_HOME/.claude/scripts/events.sh"
SD=$(cd "$REPO" && HOME="$FAKE_HOME" bash -c '. "'"$FAKE_HOME"'/.claude/scripts/events.sh" && events_state_dir')
mkdir -p "$SD"
DH=$(cd "$REPO" && HOME="$FAKE_HOME" bash -c '. "'"$FAKE_HOME"'/.claude/scripts/events.sh" && events_diff_hash main' 2>/dev/null || echo 0000000000000000)

events_emit_init "$SD" "42-one" "acme/repo" 42 "feat/one" main main "$REPO"
# Phase 4: orchestrator writer token is required for stage.passed/failed.
# emit_init already created the token file; export it for the rest of the test.
if [ -f "$SD/.orch-writer-token" ]; then
    export ORCHESTRATOR_TOKEN=$(cat "$SD/.orch-writer-token")
fi
events_emit_stage_started "$SD" "42-one" builder build 1 "$DH"
events_emit_stage_passed  "$SD" "42-one" builder build 1 "$DH" "build tests pass"
events_emit_stage_passed  "$SD" "42-one" reviewer review 1 "$DH" "APPROVED: looks good"

# ==================
echo "== status =="

OUT=$(bash "$FAKE_HOME/.claude/scripts/project_events.sh" status "$SD" 2>&1)
if echo "$OUT" | grep -q "pending: line 3 stage.passed build" \
   && echo "$OUT" | grep -q "pending: line 4 stage.passed review"; then
    ok "status reports build+review as pending"
else
    bad "status output: $OUT"
fi

# ==================
echo "== format =="

BODY=$(bash "$FAKE_HOME/.claude/scripts/project_events.sh" format "$SD" 3 2>&1)
if echo "$BODY" | head -1 | grep -q '<!-- gate:build:42-one -->' \
   && echo "$BODY" | grep -q 'build tests pass'; then
    ok "format build → gate comment body"
else
    bad "format build body: $BODY"
fi

BODY=$(bash "$FAKE_HOME/.claude/scripts/project_events.sh" format "$SD" 4 2>&1)
if echo "$BODY" | head -1 | grep -q '<!-- gate:review:42-one -->' \
   && echo "$BODY" | grep -q 'APPROVED'; then
    ok "format review → gate comment body"
else
    bad "format review body: $BODY"
fi

# ==================
echo "== dry-run (side-effect-free preview) =="

# Dry-run with explicit target: prints bodies, makes no gh call, emits no mirror.posted.
GH_LOG="$SBX/gh.log"; : > "$GH_LOG"
export GH_LOG
EVENTS_BEFORE=$(wc -l < "$SD/events.jsonl")
PATH="$BIN_DIR:$PATH" bash "$FAKE_HOME/.claude/scripts/project_events.sh" post "$SD" \
    --target-num 42 --target-kind issue --dry-run > "$SBX/dry.out" 2>&1
EVENTS_AFTER=$(wc -l < "$SD/events.jsonl")

grep -q "projector (dry-run): would-post=2 skipped=0 target=issue#42" "$SBX/dry.out" \
    && ok "dry-run: would-post summary correct" \
    || bad "dry-run summary: $(cat "$SBX/dry.out")"

grep -q "<!-- gate:build:42-one -->" "$SBX/dry.out" \
    && grep -q "<!-- gate:review:42-one -->" "$SBX/dry.out" \
    && ok "dry-run: prints both gate-comment bodies" \
    || bad "dry-run bodies missing: $(cat "$SBX/dry.out")"

[ ! -s "$GH_LOG" ] \
    && ok "dry-run: no gh calls made" \
    || bad "dry-run unexpectedly called gh: $(cat "$GH_LOG")"

[ "$EVENTS_BEFORE" = "$EVENTS_AFTER" ] \
    && ok "dry-run: events.jsonl unchanged (no mirror.posted appended)" \
    || bad "dry-run mutated events.jsonl: $EVENTS_BEFORE → $EVENTS_AFTER"

# Dry-run WITHOUT target — tolerated, uses ?#? placeholder.
PATH="$BIN_DIR:$PATH" bash "$FAKE_HOME/.claude/scripts/project_events.sh" post "$SD" \
    --dry-run > "$SBX/dry2.out" 2>&1
# The gh stub returns "" for "pr list", so target auto-resolution returns empty;
# dry-run should NOT die on that.
grep -qE "would-post=2.*target=(\?#\?|issue#42)" "$SBX/dry2.out" \
    && ok "dry-run: tolerates unresolved target (placeholder or fallback)" \
    || bad "dry-run with no target failed: $(cat "$SBX/dry2.out")"

# ==================
echo "== post (offline with gh stub) =="
GH_LOG="$SBX/gh.log"; : > "$GH_LOG"
export GH_LOG
PATH="$BIN_DIR:$PATH" bash "$FAKE_HOME/.claude/scripts/project_events.sh" post "$SD" \
    --target-num 42 --target-kind issue > "$SBX/post.out" 2>&1
grep -q "posted=2 skipped=0 failed=0" "$SBX/post.out" \
    && ok "post: emits 2 comments" \
    || bad "post summary: $(cat "$SBX/post.out")"

# Re-post should skip (mirror.posted already recorded)
: > "$GH_LOG"
PATH="$BIN_DIR:$PATH" bash "$FAKE_HOME/.claude/scripts/project_events.sh" post "$SD" \
    --target-num 42 --target-kind issue > "$SBX/post2.out" 2>&1
grep -q "posted=0 skipped=2" "$SBX/post2.out" \
    && ok "post is idempotent — second run skips" \
    || bad "second-post summary: $(cat "$SBX/post2.out")"

# Log still validates after projector added mirror.posted events
if events_validate "$SD/events.jsonl" >/dev/null 2>&1; then
    ok "events.jsonl remains valid after projector appends mirror.posted"
else
    bad "events.jsonl invalid after projector run"
fi

# ==================
echo
echo "=================="
echo "Passed: $PASS"
echo "Failed: $FAIL"
if [ "$FAIL" -eq 0 ]; then echo "ALL GREEN"; exit 0; else echo "FAIL"; exit 1; fi
