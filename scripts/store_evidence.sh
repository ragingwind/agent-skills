#!/usr/bin/env bash
# store_evidence.sh — content-addressed evidence storage helpers.
#
# Filename convention: <logical_name>.<hash8>.<ext>
#   hash8 = first 8 hex chars of SHA-256(file contents)
#
# Public functions:
#   store_evidence <state_dir> <source_file> <logical_name>
#       Copy <source_file> into $STATE_DIR/evidence/ with the content-addressed
#       filename. Prints the final filename (not the full path) on stdout.
#       Idempotent: if the destination already exists with matching content, no-op.
#
#   store_evidence_verify <state_dir> <filename>
#       Given a filename (not path) expected under $STATE_DIR/evidence/, verify:
#         1. The file exists.
#         2. The filename carries a hash8 suffix (<logical>.<hash8>.<ext> or
#            <logical>.<hash8> when no extension).
#         3. The file's actual SHA-256 prefix matches the embedded hash8.
#       Returns 0 on pass, 1 on fail. Filenames without a hash8 suffix are
#       rejected outright (Phase 6c — the backward-compat pass-through that
#       existed in 6a has been removed; all writers must call store_evidence
#       or store_evidence_migrate first).

_se_die() { echo "store_evidence: $*" >&2; return 1; }

# POSIX-portable SHA-256. macOS ships `shasum`; Linux usually has `sha256sum`
# AND `shasum` (via perl-shasum). Prefer `shasum -a 256` for cross-platform.
_se_sha256() {
    local f="$1"
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$f" 2>/dev/null | awk '{print $1}'
    elif command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$f" 2>/dev/null | awk '{print $1}'
    else
        _se_die "neither shasum nor sha256sum available"
        return 1
    fi
}

# Extract extension (lowercased) from a filename. Empty if none.
_se_ext() {
    local base="${1##*/}"
    case "$base" in
        *.*) printf '%s' "${base##*.}" | tr '[:upper:]' '[:lower:]' ;;
        *)   printf '' ;;
    esac
}

# Match 8 lowercase hex chars.
_se_is_hash8() {
    case "$1" in
        [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) return 0 ;;
        *) return 1 ;;
    esac
}

# Parse filenames carrying a content-addressed hash8 suffix.
#   <logical>.<hash8>.<ext>  → prints "<hash8> <ext>"
#   <logical>.<hash8>        → prints "<hash8>"         (no extension)
# Returns 1 if the filename has no hash8 suffix.
#
# CONSTRAINT: the <logical> portion MUST NOT end in a dot-separated 8-hex-char
# segment (e.g., "foo.deadbeef.png"). Such a name would parse as a valid hash8
# suffix here and bypass the migrate step, defeating hook re-hash verification.
# Callers of store_evidence/store_evidence_migrate are responsible for choosing
# logical names that cannot be confused with a hash8 (the canonical prefixes —
# browser-verify-*, tia-*, s<N>-* — all satisfy this).
_se_parse() {
    local fn="$1"
    local ext="${fn##*.}"
    local rest="${fn%.*}"
    # Case A: <logical>.<hash8>.<ext> — `rest` still has a dot, middle token is hash8.
    case "$rest" in
        *.*)
            local h8="${rest##*.}"
            if _se_is_hash8 "$h8"; then
                printf '%s %s\n' "$h8" "$ext"
                return 0
            fi
            ;;
    esac
    # Case B: <logical>.<hash8> — no extension. The last dot-segment IS the hash8.
    if _se_is_hash8 "$ext"; then
        printf '%s\n' "$ext"
        return 0
    fi
    return 1
}

store_evidence() {
    local state_dir="${1:?state_dir required}"
    local src="${2:?source_file required}"
    local logical="${3:?logical_name required}"

    [ -f "$src" ] || { _se_die "source not found: $src"; return 1; }
    [ -d "$state_dir" ] || { _se_die "state_dir not found: $state_dir"; return 1; }

    local sha hash8 ext fn dest
    sha=$(_se_sha256 "$src") || return 1
    [ -n "$sha" ] || { _se_die "could not hash: $src"; return 1; }
    hash8="${sha%${sha#????????}}"   # take first 8 chars portably

    ext=$(_se_ext "$src")
    if [ -n "$ext" ]; then
        fn="${logical}.${hash8}.${ext}"
    else
        fn="${logical}.${hash8}"
    fi

    mkdir -p "$state_dir/evidence" || { _se_die "cannot mkdir $state_dir/evidence"; return 1; }
    dest="$state_dir/evidence/$fn"

    if [ -f "$dest" ]; then
        # Idempotent: if dest exists and SHA matches, no-op.
        local dest_sha
        dest_sha=$(_se_sha256 "$dest") || return 1
        if [ "$dest_sha" = "$sha" ]; then
            printf '%s\n' "$fn"
            return 0
        fi
        # Collision on logical_name.hash8 with different content → extremely
        # unlikely but flag it. Refuse to overwrite silently.
        _se_die "destination exists with different content: $dest"
        return 1
    fi

    cp "$src" "$dest" || { _se_die "cp failed: $src → $dest"; return 1; }
    printf '%s\n' "$fn"
}

# store_evidence_migrate <state_dir>
# Rename every file under $state_dir/evidence/ that lacks a <hash8> suffix to
# <logical>.<hash8>.<ext> (or <logical>.<hash8> if no extension). Idempotent:
# files already carrying a valid hash8 suffix are left untouched.
#
# Used by orchestrators after an agent writes evidence with logical names
# (e.g. browser-verify-phase1-step01-settings.png) to stamp content-addressed
# suffixes before emitting stage.passed events.
store_evidence_migrate() {
    local state_dir="${1:?state_dir required}"
    [ -d "$state_dir/evidence" ] || return 0
    local f base logical ext sha h8 newname
    for f in "$state_dir"/evidence/*; do
        [ -f "$f" ] || continue
        base="${f##*/}"
        # Already carries <hash8>.<ext>? → leave alone.
        if _se_parse "$base" >/dev/null 2>&1; then
            continue
        fi
        if case "$base" in *.*) true ;; *) false ;; esac; then
            ext="${base##*.}"
            logical="${base%.*}"
        else
            ext=""
            logical="$base"
        fi
        sha=$(_se_sha256 "$f") || return 1
        h8="${sha%${sha#????????}}"
        if [ -n "$ext" ]; then
            newname="${logical}.${h8}.${ext}"
        else
            newname="${logical}.${h8}"
        fi
        # Skip if migration would be a no-op (same name).
        [ "$base" = "$newname" ] && continue
        mv "$f" "$state_dir/evidence/$newname" || return 1
    done
    return 0
}

# store_evidence_list_json <state_dir> [glob ...]
# Print a compact JSON array of basenames under $state_dir/evidence/ matching
# the given shell glob(s). With no glob, list every file. Duplicates are
# removed; ordering is stable (by scan order). Always emits valid JSON, even
# when the directory is empty (`[]`).
store_evidence_list_json() {
    local state_dir="${1:?state_dir required}"
    shift
    [ -d "$state_dir/evidence" ] || { printf '[]\n'; return 0; }

    local tmp
    tmp=$(mktemp 2>/dev/null) || { _se_die "mktemp failed"; return 1; }

    if [ $# -eq 0 ]; then
        for f in "$state_dir"/evidence/*; do
            [ -f "$f" ] && printf '%s\n' "${f##*/}" >> "$tmp"
        done
    else
        local pat
        for pat in "$@"; do
            # Disable nullglob pollution: rely on explicit [ -f ] check.
            for f in "$state_dir"/evidence/$pat; do
                [ -f "$f" ] && printf '%s\n' "${f##*/}" >> "$tmp"
            done
        done
    fi

    # Dedup + serialize via jq. awk preserves first-seen order.
    awk 'NF && !seen[$0]++' "$tmp" | jq -R . | jq -sc .
    local rc=$?
    rm -f "$tmp" 2>/dev/null
    return $rc
}

store_evidence_verify() {
    local state_dir="${1:?state_dir required}"
    local filename="${2:?filename required}"

    case "$filename" in
        */*) _se_die "filename must be basename only, got: $filename"; return 1 ;;
    esac

    local ev_path="$state_dir/evidence/$filename"
    [ -f "$ev_path" ] || { _se_die "missing: $ev_path"; return 1; }

    local parsed expected_hash
    parsed=$(_se_parse "$filename") || {
        _se_die "filename missing <hash8> suffix: $filename (writer did not call store_evidence?)"
        return 1
    }
    expected_hash="${parsed%% *}"
    local actual_sha actual8
    actual_sha=$(_se_sha256 "$ev_path") || return 1
    actual8="${actual_sha%${actual_sha#????????}}"
    if [ "$actual8" != "$expected_hash" ]; then
        _se_die "hash mismatch for $filename: filename says $expected_hash, actual $actual8"
        return 1
    fi
    return 0
}

# check_evidence_parity <state_dir> [stage]
#
# Verify every flow declared in plan.md's "evidence-flows:" line has at least
# one matching file under $state_dir/evidence/. Type-prefix conventions:
#   browser-verify-* / tia-*  → ≥1 .png  (multiple steps allowed per flow)
#   s<N>-*                     → ≥1 .webm (one scenario video per flow)
#
# When [stage] is given, only flows relevant to that stage are checked:
#   build  → browser-verify-* + s<N>-*  (both [A] and [B] evidence belong here)
#   verify → tia-*
#   (any other / unset) → check ALL declared flows
#
# Returns:
#   0 — no plan.md, no evidence-flows line, OR every relevant flow satisfied
#   1 — at least one declared flow has no matching file
#
# On miss, emits "MISSING: <flow>(<expected-ext>)" lines to stderr (one per
# missing flow). Callers should capture stderr and surface to the user.
#
# Rationale: the existing store_evidence_verify only validates files that the
# orchestrator already chose to put in the stage.passed evidence array. It
# does NOT cross-check against the plan's contract. This helper closes that
# gap — the plan is the contract; runtime evidence must satisfy the contract.
check_evidence_parity() {
    local state_dir="${1:?state_dir required}"
    local stage="${2:-}"
    local plan="$state_dir/plan.md"
    [ -f "$plan" ] || return 0

    local flows_line
    flows_line=$(grep -E '^[[:space:]]*evidence-flows:' "$plan" 2>/dev/null | head -1)
    [ -z "$flows_line" ] && return 0

    local flows
    flows=$(printf '%s\n' "$flows_line" \
        | sed -E 's/^[[:space:]]*evidence-flows:[[:space:]]*//' \
        | tr ',' '\n' \
        | sed -E 's/^[[:space:]]+|[[:space:]]+$//g' \
        | grep -v '^$' || true)
    [ -z "$flows" ] && return 0

    if [ -n "$stage" ]; then
        case "$stage" in
            build)  flows=$(printf '%s\n' "$flows" | grep -E '^(browser-verify-|s[0-9]+-)' || true) ;;
            verify) flows=$(printf '%s\n' "$flows" | grep -E '^tia-' || true) ;;
            *)      ;;
        esac
    fi
    [ -z "$flows" ] && return 0

    # Use `find` (POSIX, no shell-option dependency) instead of bare globs:
    # zsh under default options errors on unmatched globs ("no matches found"),
    # which would crash this helper when called from a zsh main-conversation
    # shell. Bash leaves the literal pattern (handled by the [ -f ] check);
    # find sidesteps both and is uniformly available.
    local missing=0
    local flow expected_ext match
    while IFS= read -r flow; do
        [ -z "$flow" ] && continue
        match=""
        case "$flow" in
            browser-verify-*|tia-*)
                expected_ext=".png"
                match=$(find "$state_dir/evidence" -maxdepth 1 -type f \
                    -name "${flow}*.png" 2>/dev/null | head -1)
                ;;
            s[0-9]*-*)
                expected_ext=".webm"
                match=$(find "$state_dir/evidence" -maxdepth 1 -type f \
                    -name "${flow}*.webm" 2>/dev/null | head -1)
                ;;
            *)
                expected_ext="any"
                match=$(find "$state_dir/evidence" -maxdepth 1 -type f \
                    -name "${flow}*" 2>/dev/null | head -1)
                ;;
        esac
        if [ -z "$match" ]; then
            printf 'MISSING: %s(%s)\n' "$flow" "$expected_ext" >&2
            missing=$((missing + 1))
        fi
    done <<EOF
$flows
EOF

    [ "$missing" -gt 0 ] && return 1
    return 0
}

# check_cutover_consistency <state_dir>
#
# Detect a contradiction between evidence-flows and cutover-phase in plan.md.
# When evidence-flows declares any s<N>-* (E2E scenario), the change is by
# definition exercising the production code path → cutover-phase MUST be
# true so the production-path metadata check (in pre-bash-pr-gate.sh)
# actually applies.
#
# The contradiction case is: s<N>-* declared but cutover-phase != true. That
# combination lets a writer claim E2E scenarios while bypassing the
# production-path verification, which is the exact failure mode this helper
# closes.
#
# Returns:
#   0 — no plan.md, no s<N>-* flows declared, OR cutover-phase: true present
#   1 — s<N>-* declared AND cutover-phase != true (contradiction)
#
# On contradiction, emits a single "CONTRADICTION: ..." line to stderr.
check_cutover_consistency() {
    local state_dir="${1:?state_dir required}"
    local plan="$state_dir/plan.md"
    [ -f "$plan" ] || return 0

    local flows_line
    flows_line=$(grep -E '^[[:space:]]*evidence-flows:' "$plan" 2>/dev/null | head -1)
    [ -z "$flows_line" ] && return 0

    local has_scenario
    has_scenario=$(printf '%s' "$flows_line" \
        | sed -E 's/^[[:space:]]*evidence-flows:[[:space:]]*//' \
        | tr ',' '\n' \
        | sed -E 's/^[[:space:]]+|[[:space:]]+$//g' \
        | grep -cE '^s[0-9]+-' 2>/dev/null | head -1)
    has_scenario="${has_scenario:-0}"
    [ "$has_scenario" -lt 1 ] 2>/dev/null && return 0

    local cutover_true
    cutover_true=$(grep -cE '^[[:space:]]*cutover-phase:[[:space:]]*true[[:space:]]*$' "$plan" 2>/dev/null | head -1)
    cutover_true="${cutover_true:-0}"
    if [ "$cutover_true" -lt 1 ] 2>/dev/null; then
        printf 'CONTRADICTION: evidence-flows declares E2E scenarios (s<N>-*) but cutover-phase is not true. E2E scenarios validate production code paths; cutover-phase MUST be true so the production-path evidence check applies. Either set cutover-phase: true OR remove the s<N>-* flows.\n' >&2
        return 1
    fi
    return 0
}

# This file is intended to be sourced:
#   . "${CLAUDE_PLUGIN_ROOT}/scripts/store_evidence.sh"
# Callers invoke store_evidence / store_evidence_verify as shell functions.
