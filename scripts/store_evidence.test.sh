#!/usr/bin/env bash
# Tests for scripts/store_evidence.sh — content-addressed evidence helper.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/store_evidence.sh"

PASS=0
FAIL=0
FAILED_TESTS=()

assert() {
    local name="$1"; shift
    if "$@"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILED_TESTS+=("$name")
        echo "FAIL: $name" >&2
    fi
}

with_tmpdir() {
    local d; d=$(mktemp -d)
    echo "$d"
}

# -------- Test 1: store copies file and returns <logical>.<hash8>.<ext> --------
t_store_basic() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state"
    printf 'hello world\n' > "$tmp/src.png"

    local fn
    fn=$(store_evidence "$state" "$tmp/src.png" "browser-verify-step01") || { rm -rf "$tmp"; return 1; }

    # SHA-256 of "hello world\n" = a948904f2f0f479b8f8197694b30184b0d2ed1c1cd2a1ec0fb85d299a192a447
    [ "$fn" = "browser-verify-step01.a948904f.png" ] || { echo "got: $fn" >&2; rm -rf "$tmp"; return 1; }
    [ -f "$state/evidence/$fn" ] || { rm -rf "$tmp"; return 1; }

    rm -rf "$tmp"; return 0
}

# -------- Test 2: idempotent — same content → same filename, one copy on disk --------
t_idempotent() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state"
    printf 'abc\n' > "$tmp/src.png"

    local fn1 fn2
    fn1=$(store_evidence "$state" "$tmp/src.png" "step") || { rm -rf "$tmp"; return 1; }
    fn2=$(store_evidence "$state" "$tmp/src.png" "step") || { rm -rf "$tmp"; return 1; }

    [ "$fn1" = "$fn2" ] || { rm -rf "$tmp"; return 1; }

    local count
    count=$(ls "$state/evidence/" | wc -l | tr -d ' ')
    [ "$count" = "1" ] || { rm -rf "$tmp"; return 1; }

    rm -rf "$tmp"; return 0
}

# -------- Test 3: different content → different hash8 --------
t_diff_content_diff_hash() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state"

    printf 'v1\n' > "$tmp/src.png"
    local a; a=$(store_evidence "$state" "$tmp/src.png" "stepX") || { rm -rf "$tmp"; return 1; }

    printf 'v2\n' > "$tmp/src.png"
    local b; b=$(store_evidence "$state" "$tmp/src.png" "stepX") || { rm -rf "$tmp"; return 1; }

    [ "$a" != "$b" ] || { rm -rf "$tmp"; return 1; }

    rm -rf "$tmp"; return 0
}

# -------- Test 4: verify passes on untampered file --------
t_verify_pass() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state"
    printf 'stable\n' > "$tmp/src.png"

    local fn
    fn=$(store_evidence "$state" "$tmp/src.png" "stable") || { rm -rf "$tmp"; return 1; }

    store_evidence_verify "$state" "$fn" || { rm -rf "$tmp"; return 1; }

    rm -rf "$tmp"; return 0
}

# -------- Test 5: verify detects tampering --------
t_verify_tamper() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state"
    printf 'original\n' > "$tmp/src.png"

    local fn
    fn=$(store_evidence "$state" "$tmp/src.png" "victim") || { rm -rf "$tmp"; return 1; }

    # Tamper
    printf 'modified\n' > "$state/evidence/$fn"

    if store_evidence_verify "$state" "$fn" 2>/dev/null; then
        rm -rf "$tmp"; return 1   # should have failed
    fi

    rm -rf "$tmp"; return 0
}

# -------- Test 6: Phase 6c — filenames without hash8 suffix are rejected --------
t_verify_rejects_unhashed() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state/evidence"; mkdir -p "$state"
    printf 'legacy\n' > "$tmp/state/evidence/legacy-name.png"

    if store_evidence_verify "$tmp/state" "legacy-name.png" 2>/dev/null; then
        rm -rf "$tmp"; return 1   # should have failed — no hash8 suffix
    fi

    rm -rf "$tmp"; return 0
}

# -------- Test 7: verify fails on missing file --------
t_verify_missing() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"

    if store_evidence_verify "$state" "ghost.aabbccdd.png" 2>/dev/null; then
        rm -rf "$tmp"; return 1
    fi

    rm -rf "$tmp"; return 0
}

# -------- Test 8: basename-only guard (reject paths in filename arg) --------
t_verify_rejects_path() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"

    if store_evidence_verify "$state" "sub/ghost.aabbccdd.png" 2>/dev/null; then
        rm -rf "$tmp"; return 1
    fi

    rm -rf "$tmp"; return 0
}

# -------- Test 9: store fails gracefully on missing source --------
t_store_missing_source() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state"

    if store_evidence "$state" "$tmp/nonexistent.png" "x" 2>/dev/null; then
        rm -rf "$tmp"; return 1
    fi

    rm -rf "$tmp"; return 0
}

# -------- Test 10: no extension → <logical>.<hash8> --------
t_no_extension() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state"
    printf 'data\n' > "$tmp/src"

    local fn
    fn=$(store_evidence "$state" "$tmp/src" "raw") || { rm -rf "$tmp"; return 1; }

    # Must match raw.<8hex> (no trailing dot)
    case "$fn" in
        raw.[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
        *) echo "got: $fn" >&2; rm -rf "$tmp"; return 1 ;;
    esac

    rm -rf "$tmp"; return 0
}

# -------- Test 11: extension case is normalized to lowercase --------
t_ext_lowercased() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state"
    printf 'data\n' > "$tmp/src.PNG"

    local fn
    fn=$(store_evidence "$state" "$tmp/src.PNG" "upper") || { rm -rf "$tmp"; return 1; }

    case "$fn" in
        upper.[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f].png) ;;
        *) echo "got: $fn" >&2; rm -rf "$tmp"; return 1 ;;
    esac

    rm -rf "$tmp"; return 0
}

# -------- Test 12: migrate renames unhashed file → <logical>.<hash8>.<ext> --------
t_migrate_basic() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'hello world\n' > "$state/evidence/browser-verify-step01.png"

    store_evidence_migrate "$state" || { rm -rf "$tmp"; return 1; }

    # Original name should be gone, hash8 form should exist.
    [ ! -f "$state/evidence/browser-verify-step01.png" ] || { echo "original not renamed" >&2; rm -rf "$tmp"; return 1; }
    [ -f "$state/evidence/browser-verify-step01.a948904f.png" ] || { echo "migrated file missing" >&2; ls "$state/evidence/" >&2; rm -rf "$tmp"; return 1; }

    rm -rf "$tmp"; return 0
}

# -------- Test 13: migrate is idempotent — already-hashed files untouched --------
t_migrate_idempotent() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'stable\n' > "$tmp/src"
    local fn
    fn=$(store_evidence "$state" "$tmp/src" "stable") || { rm -rf "$tmp"; return 1; }

    # First migrate — no-op (already hashed).
    store_evidence_migrate "$state" || { rm -rf "$tmp"; return 1; }
    [ -f "$state/evidence/$fn" ] || { rm -rf "$tmp"; return 1; }

    # Second migrate — still no-op.
    store_evidence_migrate "$state" || { rm -rf "$tmp"; return 1; }
    local count
    count=$(ls "$state/evidence/" | wc -l | tr -d ' ')
    [ "$count" = "1" ] || { rm -rf "$tmp"; return 1; }

    rm -rf "$tmp"; return 0
}

# -------- Test 14: migrate handles files without extension --------
t_migrate_no_ext() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'raw\n' > "$state/evidence/raw-name"

    store_evidence_migrate "$state" || { rm -rf "$tmp"; return 1; }

    local matches
    matches=$(ls "$state/evidence/" | grep -cE '^raw-name\.[0-9a-f]{8}$' || true)
    [ "$matches" = "1" ] || { ls "$state/evidence/" >&2; rm -rf "$tmp"; return 1; }

    rm -rf "$tmp"; return 0
}

# -------- Test 15: list_json returns [] for empty/missing evidence dir --------
t_list_json_empty() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state"

    local result
    result=$(store_evidence_list_json "$state")
    [ "$result" = "[]" ] || { echo "got: $result" >&2; rm -rf "$tmp"; return 1; }

    mkdir -p "$state/evidence"
    result=$(store_evidence_list_json "$state")
    [ "$result" = "[]" ] || { echo "got (empty dir): $result" >&2; rm -rf "$tmp"; return 1; }

    rm -rf "$tmp"; return 0
}

# -------- Test 16: list_json returns filenames in a valid JSON array --------
t_list_json_files() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'a\n' > "$state/evidence/first.aaaaaaaa.png"
    printf 'b\n' > "$state/evidence/second.bbbbbbbb.png"

    local result
    result=$(store_evidence_list_json "$state")

    # Parseable JSON array of length 2.
    local len
    len=$(printf '%s' "$result" | jq 'length') || { rm -rf "$tmp"; return 1; }
    [ "$len" = "2" ] || { echo "got length: $len / result: $result" >&2; rm -rf "$tmp"; return 1; }

    # Both names present.
    printf '%s' "$result" | jq -e 'contains(["first.aaaaaaaa.png"]) and contains(["second.bbbbbbbb.png"])' >/dev/null || {
        echo "missing expected filenames in: $result" >&2; rm -rf "$tmp"; return 1
    }

    rm -rf "$tmp"; return 0
}

# -------- Test 17: list_json filters by glob --------
t_list_json_glob() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'a\n' > "$state/evidence/browser-verify-step01.aaaaaaaa.png"
    printf 'b\n' > "$state/evidence/tia-chat-step01.bbbbbbbb.png"

    local result
    result=$(store_evidence_list_json "$state" 'browser-verify-*')

    printf '%s' "$result" | jq -e '. == ["browser-verify-step01.aaaaaaaa.png"]' >/dev/null || {
        echo "expected only browser-verify match, got: $result" >&2; rm -rf "$tmp"; return 1
    }

    rm -rf "$tmp"; return 0
}

# -------- Test 18: migrate + list_json integration — hashed names pass verify --------
t_migrate_then_verify() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'data1\n' > "$state/evidence/browser-verify-step01.png"
    printf 'data2\n' > "$state/evidence/browser-verify-step02.png"

    store_evidence_migrate "$state" || { rm -rf "$tmp"; return 1; }

    local result
    result=$(store_evidence_list_json "$state" 'browser-verify-*')

    # Each listed filename should pass verify.
    local name
    for name in $(printf '%s' "$result" | jq -r '.[]'); do
        store_evidence_verify "$state" "$name" || { echo "verify failed for: $name" >&2; rm -rf "$tmp"; return 1; }
    done

    rm -rf "$tmp"; return 0
}

# -------- Test 19: parity — no plan.md → 0 (no contract) --------
t_parity_no_plan() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    check_evidence_parity "$state" 2>/dev/null || { rm -rf "$tmp"; return 1; }
    rm -rf "$tmp"; return 0
}

# -------- Test 20: parity — plan.md without evidence-flows → 0 --------
t_parity_no_flows_line() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'evidence-mode: screenshot\n' > "$state/plan.md"
    check_evidence_parity "$state" 2>/dev/null || { rm -rf "$tmp"; return 1; }
    rm -rf "$tmp"; return 0
}

# -------- Test 21: parity — declared browser-verify with matching .png → 0 --------
t_parity_browser_verify_present() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'evidence-flows: browser-verify-foo\n' > "$state/plan.md"
    printf 'png-data\n' > "$state/evidence/browser-verify-foo-step01-x.png"
    check_evidence_parity "$state" 2>/dev/null || { rm -rf "$tmp"; return 1; }
    rm -rf "$tmp"; return 0
}

# -------- Test 22: parity — declared browser-verify but no .png → 1 --------
t_parity_browser_verify_missing() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'evidence-flows: browser-verify-foo\n' > "$state/plan.md"
    local err
    err=$(check_evidence_parity "$state" 2>&1 1>/dev/null)
    [ "$?" -eq 0 ] || true   # we expect non-zero from the function itself
    if check_evidence_parity "$state" 2>/dev/null; then
        echo "expected non-zero return, got 0" >&2
        rm -rf "$tmp"; return 1
    fi
    case "$err" in
        *"MISSING: browser-verify-foo(.png)"*) ;;
        *) echo "stderr did not name missing flow: $err" >&2; rm -rf "$tmp"; return 1 ;;
    esac
    rm -rf "$tmp"; return 0
}

# -------- Test 23: parity — s<N> declared but only .png present → 1 (wrong ext) --------
t_parity_scenario_wrong_ext() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'evidence-flows: s1-foo\n' > "$state/plan.md"
    printf 'png-bytes\n' > "$state/evidence/s1-foo-step01.png"   # png, not webm
    if check_evidence_parity "$state" 2>/dev/null; then
        echo "expected non-zero (s1-foo needs .webm)" >&2
        rm -rf "$tmp"; return 1
    fi
    rm -rf "$tmp"; return 0
}

# -------- Test 24: parity — s<N> with matching .webm → 0 --------
t_parity_scenario_webm_present() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'evidence-flows: s1-foo\n' > "$state/plan.md"
    printf 'webm-bytes\n' > "$state/evidence/s1-foo.deadbeef.webm"
    check_evidence_parity "$state" 2>/dev/null || { rm -rf "$tmp"; return 1; }
    rm -rf "$tmp"; return 0
}

# -------- Test 25: parity — stage filter "verify" skips browser-verify-* checks --------
t_parity_stage_filter_verify() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'evidence-flows: browser-verify-foo, tia-bar\n' > "$state/plan.md"
    # No browser-verify-foo*.png present, but tia-bar.<hash>.png IS present.
    printf 'tia-bytes\n' > "$state/evidence/tia-bar-step01.png"
    # Stage = verify → only tia-* matters → should pass.
    check_evidence_parity "$state" verify 2>/dev/null || { rm -rf "$tmp"; return 1; }
    # But unfiltered → should fail (browser-verify-foo missing).
    if check_evidence_parity "$state" 2>/dev/null; then
        rm -rf "$tmp"; return 1
    fi
    rm -rf "$tmp"; return 0
}

# -------- Test 26: parity — multiple flows, partial miss --------
t_parity_partial_miss() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'evidence-flows: browser-verify-a, s1-b, s2-c\n' > "$state/plan.md"
    printf 'x\n' > "$state/evidence/browser-verify-a-step01.png"
    printf 'y\n' > "$state/evidence/s1-b.aabbccdd.webm"
    # s2-c has no file — should fail naming s2-c.
    local err
    err=$(check_evidence_parity "$state" 2>&1 1>/dev/null)
    if check_evidence_parity "$state" 2>/dev/null; then
        rm -rf "$tmp"; return 1
    fi
    case "$err" in
        *"MISSING: s2-c(.webm)"*) ;;
        *) echo "expected MISSING: s2-c, got: $err" >&2; rm -rf "$tmp"; return 1 ;;
    esac
    case "$err" in
        *"browser-verify-a"*|*"s1-b"*) echo "should NOT name satisfied flows: $err" >&2; rm -rf "$tmp"; return 1 ;;
    esac
    rm -rf "$tmp"; return 0
}

# -------- Test 27: cutover-consistency — no s<N>-* declared → 0 --------
t_cutover_no_scenario() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'evidence-flows: browser-verify-foo\ncutover-phase: false\n' > "$state/plan.md"
    check_cutover_consistency "$state" 2>/dev/null || { rm -rf "$tmp"; return 1; }
    rm -rf "$tmp"; return 0
}

# -------- Test 28: cutover-consistency — s<N>-* + cutover-phase: true → 0 --------
t_cutover_scenario_with_true() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'evidence-flows: s1-foo, s2-bar\ncutover-phase: true\n' > "$state/plan.md"
    check_cutover_consistency "$state" 2>/dev/null || { rm -rf "$tmp"; return 1; }
    rm -rf "$tmp"; return 0
}

# -------- Test 29: cutover-consistency — s<N>-* + cutover-phase: false → 1 --------
t_cutover_scenario_with_false() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'evidence-flows: s1-foo\ncutover-phase: false\n' > "$state/plan.md"
    local err
    err=$(check_cutover_consistency "$state" 2>&1 1>/dev/null)
    if check_cutover_consistency "$state" 2>/dev/null; then
        rm -rf "$tmp"; return 1
    fi
    case "$err" in
        *"CONTRADICTION:"*) ;;
        *) echo "expected CONTRADICTION, got: $err" >&2; rm -rf "$tmp"; return 1 ;;
    esac
    rm -rf "$tmp"; return 0
}

# -------- Test 30: cutover-consistency — s<N>-* + cutover-phase missing → 1 --------
t_cutover_scenario_no_field() {
    local tmp; tmp=$(with_tmpdir)
    local state="$tmp/state"; mkdir -p "$state/evidence"
    printf 'evidence-flows: s1-foo\n' > "$state/plan.md"
    if check_cutover_consistency "$state" 2>/dev/null; then
        rm -rf "$tmp"; return 1
    fi
    rm -rf "$tmp"; return 0
}

# -------- Run all --------
assert "store_basic"              t_store_basic
assert "idempotent"               t_idempotent
assert "diff_content_diff_hash"   t_diff_content_diff_hash
assert "verify_pass"              t_verify_pass
assert "verify_tamper"            t_verify_tamper
assert "verify_rejects_unhashed"  t_verify_rejects_unhashed
assert "verify_missing"           t_verify_missing
assert "verify_rejects_path"      t_verify_rejects_path
assert "store_missing_source"     t_store_missing_source
assert "no_extension"             t_no_extension
assert "ext_lowercased"           t_ext_lowercased
assert "migrate_basic"            t_migrate_basic
assert "migrate_idempotent"       t_migrate_idempotent
assert "migrate_no_ext"           t_migrate_no_ext
assert "list_json_empty"          t_list_json_empty
assert "list_json_files"          t_list_json_files
assert "list_json_glob"           t_list_json_glob
assert "migrate_then_verify"      t_migrate_then_verify
assert "parity_no_plan"           t_parity_no_plan
assert "parity_no_flows_line"     t_parity_no_flows_line
assert "parity_browser_verify_present" t_parity_browser_verify_present
assert "parity_browser_verify_missing" t_parity_browser_verify_missing
assert "parity_scenario_wrong_ext" t_parity_scenario_wrong_ext
assert "parity_scenario_webm_present" t_parity_scenario_webm_present
assert "parity_stage_filter_verify" t_parity_stage_filter_verify
assert "parity_partial_miss"      t_parity_partial_miss
assert "cutover_no_scenario"      t_cutover_no_scenario
assert "cutover_scenario_with_true" t_cutover_scenario_with_true
assert "cutover_scenario_with_false" t_cutover_scenario_with_false
assert "cutover_scenario_no_field" t_cutover_scenario_no_field

echo
echo "Passed: $PASS"
echo "Failed: $FAIL"
if [ "$FAIL" -eq 0 ]; then
    echo "ALL GREEN"
    exit 0
fi
printf 'failing: %s\n' "${FAILED_TESTS[@]}"
exit 1
