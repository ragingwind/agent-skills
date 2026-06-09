#!/usr/bin/env bash
# events.sh — events.jsonl writer + reader library
#
# Dual-mode: source this file to get functions, or invoke as a subcommand:
#   bash events.sh state_dir
#   bash events.sh diff_hash [base]
#   bash events.sh append <state_dir> <json_payload>
#   bash events.sh latest <state_dir> <type> [key=value ...]
#   bash events.sh validate <jsonl_path>
#
# Portability: macOS + Linux. No flock (uses mkdir atomic lock).
# Requires: git, jq, shasum (or sha256sum), hostname, sed, awk.

set -u

# ---------- helpers ----------

_events_die() {
    echo "events.sh: $*" >&2
    return 1
}

_events_sha256() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256
    elif command -v sha256sum >/dev/null 2>&1; then
        sha256sum
    else
        _events_die "no sha256 tool (shasum or sha256sum) found"
        return 1
    fi
}

_events_realpath() {
    local target="$1"
    if command -v realpath >/dev/null 2>&1; then
        realpath "$target" 2>/dev/null && return 0
    fi
    # Portable fallback: cd + pwd -P
    (cd "$target" 2>/dev/null && pwd -P)
}

# _events_check_orchestrator_token <state_dir> <caller_name>
# Guards stage.passed / stage.failed emits so sub-agents cannot forge gate
# outcomes. The check is only active when `.orch-writer-token` exists in the
# state dir — pre-migration logs without a token file pass through unchanged.
# When active, the caller's ORCHESTRATOR_TOKEN env must equal the file's
# contents byte-for-byte; anything else returns 1 with a diagnostic.
_events_check_orchestrator_token() {
    local sd="$1" caller="$2"
    local tok_file="$sd/.orch-writer-token"
    [ -f "$tok_file" ] || return 0  # no token file → compatibility mode
    local expected
    expected=$(cat "$tok_file" 2>/dev/null)
    [ -z "$expected" ] && return 0  # unreadable/empty token → compatibility mode
    if [ -z "${ORCHESTRATOR_TOKEN:-}" ]; then
        _events_die "${caller}: ORCHESTRATOR_TOKEN not set (caller not orchestrator?)"
        return 1
    fi
    if [ "${ORCHESTRATOR_TOKEN}" != "$expected" ]; then
        _events_die "${caller}: ORCHESTRATOR_TOKEN mismatch (caller not orchestrator?)"
        return 1
    fi
    return 0
}

# ---------- state_dir resolver (§5) ----------

events_state_dir() {
    local worktree_root branch hostname project_slug branch_slug project_dir existing init_wt

    worktree_root=$(git rev-parse --show-toplevel 2>/dev/null) \
        || { _events_die "not inside a git worktree"; return 1; }
    worktree_root=$(_events_realpath "$worktree_root") \
        || { _events_die "cannot resolve worktree realpath"; return 1; }

    branch=$(git -C "$worktree_root" branch --show-current 2>/dev/null)
    if [ -z "$branch" ]; then
        _events_die "detached HEAD or no current branch"
        return 1
    fi

    hostname=$(hostname 2>/dev/null | tr '[:upper:]' '[:lower:]' | sed 's/\./-/g')
    [ -z "$hostname" ] && { _events_die "hostname unavailable"; return 1; }

    project_slug=$(printf '%s' "$worktree_root" | sed 's|/|-|g; s|\.|-|g')
    branch_slug=$(printf '%s' "$branch" | sed 's|/|-|g; s|\.|-|g')

    # Identity Lock (rules/orchestration.md): if any state dir under this
    # project_slug has an init event whose worktree_root matches ours, return
    # that path regardless of current branch. Prevents drift on branch rename.
    project_dir="$HOME/.local/state/agent-skills/$hostname/$project_slug"
    if [ -d "$project_dir" ]; then
        for existing in "$project_dir"/*/; do
            [ -f "${existing}events.jsonl" ] || continue
            init_wt=$(head -1 "${existing}events.jsonl" 2>/dev/null \
                | jq -r 'select(.type == "init") | .worktree_root // empty' 2>/dev/null)
            if [ -n "$init_wt" ] && [ "$init_wt" = "$worktree_root" ]; then
                printf '%s\n' "${existing%/}"
                return 0
            fi
        done
    fi

    printf '%s/.local/state/agent-skills/%s/%s/%s\n' \
        "$HOME" "$hostname" "$project_slug" "$branch_slug"
}

# ---------- diff_hash (§6 I3) ----------

events_diff_hash() {
    # Working-tree vs base (2-dot) — includes BOTH committed branch diff
    # AND any uncommitted changes. This is the correct semantic for gate
    # staleness: any change made after a gate was posted must invalidate it.
    local base="${1:-}"
    if [ -z "$base" ]; then
        base=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null \
            | sed 's|refs/remotes/origin/||')
        [ -z "$base" ] && base="main"
        base="origin/$base"
    fi
    git diff "$base" 2>/dev/null | _events_sha256 | awk '{print substr($1, 1, 16)}'
}

# ---------- lock (portable, macOS + Linux) ----------

_events_lock() {
    local state_dir="$1"
    local lock_dir="$state_dir/.lock"
    local max_iter=300  # 300 * 0.1s = 30s
    local i=0
    mkdir -p "$state_dir" 2>/dev/null
    while ! mkdir "$lock_dir" 2>/dev/null; do
        if [ "$i" -ge "$max_iter" ]; then
            _events_die "failed to acquire lock at $lock_dir within 30s"
            return 1
        fi
        sleep 0.1
        i=$((i + 1))
    done
    return 0
}

_events_unlock() {
    local state_dir="$1"
    rmdir "$state_dir/.lock" 2>/dev/null || true
}

# ---------- single-event schema validator ----------

# Validates envelope + per-type required fields + I4 (writer iff verify).
# Usage: events_validate_one <json_line>
events_validate_one() {
    local line="$1"
    [ -z "$line" ] && return 1

    # Envelope: schema_version == 1, ts/task_id/agent/type are strings
    echo "$line" | jq -e '
        (.schema_version == 1) and
        (.ts | type == "string") and
        (.task_id | type == "string") and
        (.agent | type == "string") and
        (.type | type == "string")
    ' >/dev/null 2>&1 || return 1

    local type
    type=$(echo "$line" | jq -r '.type')

    case "$type" in
        init)
            echo "$line" | jq -e '
                .repo and .issue_num and .branch and .base_branch and
                .worktree_root and .hostname and (.pr_target // .base_branch)
            ' >/dev/null 2>&1 || return 1
            ;;
        plan.posted)
            echo "$line" | jq -e '
                (.kind == "dev" or .kind == "qa") and
                (.plan_hash | type == "string") and
                (.comment_url | type == "string")
            ' >/dev/null 2>&1 || return 1
            ;;
        stage.started)
            echo "$line" | jq -e '
                (.stage == "build" or .stage == "review" or .stage == "verify" or .stage == "qa") and
                (.iteration | type == "number") and
                (.diff_hash | type == "string")
            ' >/dev/null 2>&1 || return 1
            ;;
        stage.passed)
            echo "$line" | jq -e '
                (.stage == "build" or .stage == "review" or .stage == "verify" or .stage == "qa") and
                (.iteration | type == "number") and
                (.diff_hash | type == "string") and
                (.evidence | type == "array") and
                (.summary | type == "string")
            ' >/dev/null 2>&1 || return 1
            # I4: writer iff verify
            local stage writer
            stage=$(echo "$line" | jq -r '.stage')
            writer=$(echo "$line" | jq -r '.writer // empty')
            if [ "$stage" = "verify" ]; then
                case "$writer" in
                    builder|tester) ;;
                    *) return 1 ;;
                esac
            else
                [ -z "$writer" ] || return 1
            fi
            ;;
        stage.failed)
            echo "$line" | jq -e '
                (.stage == "build" or .stage == "review" or .stage == "verify" or .stage == "qa") and
                (.iteration | type == "number") and
                (.diff_hash | type == "string") and
                (.reason | type == "string")
            ' >/dev/null 2>&1 || return 1
            ;;
        mirror.posted)
            echo "$line" | jq -e '
                (.target == "issue" or .target == "pr") and
                (.number | type == "number") and
                (.mirrors_event_offset | type == "number")
            ' >/dev/null 2>&1 || return 1
            ;;
        task.archived)
            echo "$line" | jq -e '.superseded_by_issue' >/dev/null 2>&1 || return 1
            ;;
        finalize.pr_ready)
            echo "$line" | jq -e '
                (.pr_number | type == "number") and
                (.pr_url | type == "string")
            ' >/dev/null 2>&1 || return 1
            ;;
        gate.skipped)
            echo "$line" | jq -e '
                (.hook   | type == "string") and
                (.reason | type == "string")
            ' >/dev/null 2>&1 || return 1
            ;;
        evidence.uploaded)
            echo "$line" | jq -e '
                (.stage == "build" or .stage == "review" or .stage == "verify" or .stage == "qa") and
                (.iteration   | type == "number") and
                (.asset_count | type == "number") and
                (.asset_urls  | type == "array")  and
                (.release_tag | type == "string")
            ' >/dev/null 2>&1 || return 1
            ;;
        *)
            return 1
            ;;
    esac
    return 0
}

# ---------- append (I1) ----------

# Usage: events_append <state_dir> <json_payload>
events_append() {
    local state_dir="${1:-}"
    local payload="${2:-}"
    [ -z "$state_dir" ] && { _events_die "state_dir required"; return 1; }
    [ -z "$payload" ]   && { _events_die "payload required"; return 1; }

    events_validate_one "$payload" \
        || { _events_die "payload failed schema validation"; return 1; }

    local compact
    compact=$(echo "$payload" | jq -c '.' 2>/dev/null) \
        || { _events_die "jq compaction failed"; return 1; }

    mkdir -p "$state_dir" || { _events_die "mkdir $state_dir failed"; return 1; }
    _events_lock "$state_dir" || return 1
    printf '%s\n' "$compact" >> "$state_dir/events.jsonl"
    local rc=$?
    _events_unlock "$state_dir"
    return $rc
}

# ---------- latest (reader) ----------

# Usage: events_latest <state_dir> <type> [key=value ...]
# Emits the latest matching event as compact JSON on stdout; empty if none.
events_latest() {
    local state_dir="${1:-}"
    local type="${2:-}"
    [ -z "$state_dir" ] && { _events_die "state_dir required"; return 1; }
    [ -z "$type" ]      && { _events_die "type required"; return 1; }
    shift 2

    local log="$state_dir/events.jsonl"
    [ -f "$log" ] || return 0

    local filter=".type == \"$type\""
    local kv k v
    for kv in "$@"; do
        k="${kv%%=*}"
        v="${kv#*=}"
        if [[ "$v" =~ ^-?[0-9]+$ ]]; then
            filter="$filter and .${k} == ${v}"
        else
            # Escape backslashes and quotes for jq string literal.
            v_escaped=$(printf '%s' "$v" | sed 's|\\|\\\\|g; s|"|\\"|g')
            filter="$filter and .${k} == \"${v_escaped}\""
        fi
    done

    jq -cn "[inputs | select($filter)] | last // empty" < "$log" 2>/dev/null
}

# ---------- validate full log (I1-I7) ----------

# Usage: events_validate <jsonl_path>
events_validate() {
    local log="${1:-}"
    [ -z "$log" ] && { _events_die "jsonl_path required"; return 1; }
    [ -f "$log" ] || { _events_die "$log not found"; return 1; }

    local line_num=0
    local init_branch="" init_worktree=""
    local line type off iter stage key task_id_i2

    # Track (stage, iteration) to enforce I2.
    local seen_file
    seen_file=$(mktemp 2>/dev/null || mktemp -t events) \
        || { _events_die "mktemp failed"; return 1; }
    # shellcheck disable=SC2064
    trap "rm -f '$seen_file'" RETURN

    while IFS= read -r line || [ -n "$line" ]; do
        [ -z "$line" ] && continue
        line_num=$((line_num + 1))

        events_validate_one "$line" \
            || { _events_die "line $line_num: schema validation failed"; return 1; }

        type=$(echo "$line" | jq -r '.type')

        # I7: first event must be init; branch/worktree will be checked by hooks
        # against current git state (out of scope here).
        if [ "$line_num" -eq 1 ]; then
            if [ "$type" != "init" ]; then
                _events_die "line 1 must be init (got $type)"
                return 1
            fi
            init_branch=$(echo "$line"   | jq -r '.branch')
            init_worktree=$(echo "$line" | jq -r '.worktree_root')
        fi

        # I5: mirror.posted.mirrors_event_offset points to an earlier line (1-based)
        if [ "$type" = "mirror.posted" ]; then
            off=$(echo "$line" | jq -r '.mirrors_event_offset')
            if [ "$off" -lt 1 ] || [ "$off" -ge "$line_num" ]; then
                _events_die "line $line_num: mirror_event_offset $off out of range"
                return 1
            fi
        fi

        # I2: at most one pass/fail per (task_id, stage, iteration)
        if [ "$type" = "stage.passed" ] || [ "$type" = "stage.failed" ]; then
            stage=$(echo "$line"       | jq -r '.stage')
            iter=$(echo "$line"        | jq -r '.iteration')
            task_id_i2=$(echo "$line"  | jq -r '.task_id // ""')
            key="${task_id_i2}|$stage|$iter"
            if grep -Fxq "$key" "$seen_file"; then
                _events_die "line $line_num: duplicate stage.passed/failed for ($stage, $iter)"
                return 1
            fi
            printf '%s\n' "$key" >> "$seen_file"
        fi
    done < "$log"

    if [ "$line_num" -eq 0 ]; then
        _events_die "log is empty"
        return 1
    fi

    # Stash init fields on stdout for callers that want them
    # (not strictly needed; comment out if noisy)
    : "$init_branch" "$init_worktree"
    return 0
}

# ---------- emit helpers (typed wrappers over append) ----------
#
# Phase-1 callers use these instead of hand-rolling JSON. All helpers:
#   1. Build a schema-valid payload with jq
#   2. Call events_append (which validates + locks + appends)
#   3. Return the exit code of events_append
#
# For Phase-1 ghost recording, callers are expected to wrap these with `|| true`
# so a failing event emit never blocks the legacy pipeline.

_events_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# events_emit_init <state_dir> <task_id> <repo> <issue_num> <branch> <base_branch> <pr_target> <worktree_root>
events_emit_init() {
    local sd="${1:?state_dir}" tid="${2:?task_id}" repo="${3:?repo}" issue="${4:?issue_num}"
    local branch="${5:?branch}" base="${6:?base_branch}" pr_target="${7:?pr_target}" wt="${8:?worktree_root}"


    local host
    host=$(hostname 2>/dev/null | tr '[:upper:]' '[:lower:]' | sed 's/\./-/g')
    local payload
    payload=$(jq -cn \
        --arg ts "$(_events_now)" --arg tid "$tid" --arg repo "$repo" --argjson issue "$issue" \
        --arg branch "$branch" --arg base "$base" --arg pr_target "$pr_target" \
        --arg wt "$wt" --arg host "$host" \
        '{schema_version:1, ts:$ts, task_id:$tid, agent:"orchestrator", type:"init",
          repo:$repo, issue_num:$issue, branch:$branch, base_branch:$base,
          pr_target:$pr_target, worktree_root:$wt, hostname:$host}') || return 1
    events_append "$sd" "$payload" || return 1

    # Ensure an orchestrator writer-token exists for this state dir. The token
    # guards events_emit_stage_passed/failed so sub-agents cannot forge gate
    # outcomes — only callers with ORCHESTRATOR_TOKEN set (exported by pipeline
    # SETUP) can append pass/fail events. Pre-migration state dirs without a
    # token file remain compatible: the guard only activates when the file
    # exists, and this emitter (init) creates the file on first init.
    if [ ! -f "$sd/.orch-writer-token" ]; then
        if command -v openssl >/dev/null 2>&1; then
            openssl rand -hex 32 > "$sd/.orch-writer-token" 2>/dev/null
        elif [ -r /dev/urandom ]; then
            head -c 32 /dev/urandom 2>/dev/null | od -A n -t x1 | tr -d ' \n' \
                > "$sd/.orch-writer-token" 2>/dev/null
        fi
        chmod 0400 "$sd/.orch-writer-token" 2>/dev/null || true
    fi
    return 0
}

# events_emit_stage_started <state_dir> <task_id> <agent> <stage> <iteration> <diff_hash>
events_emit_stage_started() {
    local sd="${1:?state_dir}" tid="${2:?task_id}" agent="${3:?agent}"
    local stage="${4:?stage}" iter="${5:?iteration}" dh="${6:?diff_hash}"
    local payload
    payload=$(jq -cn \
        --arg ts "$(_events_now)" --arg tid "$tid" --arg agent "$agent" \
        --arg stage "$stage" --argjson iter "$iter" --arg dh "$dh" \
        '{schema_version:1, ts:$ts, task_id:$tid, agent:$agent, type:"stage.started",
          stage:$stage, iteration:$iter, diff_hash:$dh}') || return 1
    events_append "$sd" "$payload"
}

# events_emit_stage_passed <state_dir> <task_id> <agent> <stage> <iteration> <diff_hash> <summary> [writer] [evidence_json_array]
# writer required iff stage==verify
events_emit_stage_passed() {
    local sd="${1:?state_dir}" tid="${2:?task_id}" agent="${3:?agent}"
    local stage="${4:?stage}" iter="${5:?iteration}" dh="${6:?diff_hash}" summary="${7:?summary}"
    local writer="${8:-}" evidence="${9:-[]}"
    _events_check_orchestrator_token "$sd" "events_emit_stage_passed" || return 1

    # HARD GATE: any stage.passed with a non-empty evidence array MUST be preceded
    # by an evidence.uploaded event for the same stage+iter. This prevents the
    # orchestrator from claiming a gate is open while the asset upload was skipped.
    #
    # Bypass: set EVENTS_ALLOW_UNUPLOADED_EVIDENCE=1 (logged downstream as gate.skipped).
    # Only intended for emergencies — the recovery path is to run upload-evidence
    # first, then re-call this function.
    local ev_count
    ev_count=$(printf '%s' "$evidence" | jq 'length' 2>/dev/null || echo 0)
    if [ "${ev_count:-0}" -gt 0 ] && [ "${EVENTS_ALLOW_UNUPLOADED_EVIDENCE:-0}" != "1" ]; then
        local uploaded_count
        uploaded_count=$(jq -c --arg s "$stage" --argjson it "$iter" \
            'select(.type=="evidence.uploaded" and .stage==$s and .iteration==$it)' \
            "$sd/events.jsonl" 2>/dev/null | wc -l | tr -d ' ')
        if [ "${uploaded_count:-0}" -eq 0 ]; then
            _events_die "refusing stage.passed($stage iter=$iter) — evidence array has $ev_count items but no evidence.uploaded event found for this stage. Run upload-evidence FIRST (e.g. Skill(\"upload-evidence\", args: \"--pr <N> --section '<title>' --description '<context>'\")), or set EVENTS_ALLOW_UNUPLOADED_EVIDENCE=1 to bypass (not recommended)."
            return 1
        fi
    fi

    # UI-CHANGE ENFORCEMENT: for stage=build, evidence=[] is NOT accepted when UI
    # work exists. Two complementary checks run in order:
    #   1. Disk-based: browser-verify files on disk → upload required regardless of
    #      git state. Catches pre-commit calls where git diff shows 0 UI lines.
    #   2. Git-diff-based: committed .tsx/.jsx/.css/.svg changes → upload required.
    #      Catches post-commit cases where evidence dir was cleaned before emit.
    # Both checks are skipped when plan.md declares evidence-mode: none, or when
    # EVENTS_ALLOW_UNUPLOADED_EVIDENCE=1 is set.
    if [ "$stage" = "build" ] && [ "${EVENTS_ALLOW_UNUPLOADED_EVIDENCE:-0}" != "1" ]; then
        local _plan_md="$sd/plan.md"
        local _ev_mode=""
        [ -f "$_plan_md" ] && _ev_mode=$(grep -E '^evidence-mode:' "$_plan_md" | head -1 | sed 's/^evidence-mode:[[:space:]]*//')
        if [ "$_ev_mode" != "none" ]; then
            local _init_ev _wt_root _base_branch _ui_lines _ui_uploaded _disk_evidence

            # Check 1: disk-based — browser-verify files on disk require upload even
            # before commits are made (git diff is blind to uncommitted changes).
            # Callers may run under set -e/pipefail; find must not fail the pipeline
            # when evidence/ does not exist yet.
            _disk_evidence=0
            if [ -d "$sd/evidence" ]; then
                _disk_evidence=$(find "$sd/evidence" -maxdepth 1 \
                    \( -name 'browser-verify-*.png' -o -name 'browser-verify-*.webm' \) \
                    2>/dev/null | wc -l | tr -d ' ')
            fi
            if [ "${_disk_evidence:-0}" -gt 0 ]; then
                _ui_uploaded=$(jq -c --arg s "$stage" --argjson it "$iter" \
                    'select(.type=="evidence.uploaded" and .stage==$s and .iteration==$it)' \
                    "$sd/events.jsonl" 2>/dev/null | wc -l | tr -d ' ')
                if [ "${_ui_uploaded:-0}" -eq 0 ]; then
                    _events_die "refusing stage.passed($stage iter=$iter) — ${_disk_evidence} browser-verify file(s) exist in evidence/ but no evidence.uploaded event found for stage=$stage iter=$iter. Call upload-evidence FIRST (e.g. Skill(\"upload-evidence\", args: \"--pr <N> --section '<title>' --description '<context>'\")), or declare 'evidence-mode: none' in plan.md to explicitly waive browser verification. If these files are leftover from a previous iteration, set EVENTS_ALLOW_UNUPLOADED_EVIDENCE=1 to bypass."
                    return 1
                fi
            fi

            # Check 2: git-diff-based — committed UI file changes also require upload.
            # Runs after check 1; catches cases where evidence dir is empty but diff
            # shows .tsx/.jsx/.css/.svg lines (evidence was saved elsewhere or deleted).
            _init_ev=$(events_latest "$sd" "init" 2>/dev/null || echo "")
            if [ -n "$_init_ev" ]; then
                _wt_root=$(printf '%s' "$_init_ev" | jq -r '.worktree_root // empty' 2>/dev/null)
                _base_branch=$(printf '%s' "$_init_ev" | jq -r '.base_branch // "canary"' 2>/dev/null)
                if [ -n "$_wt_root" ] && [ -d "$_wt_root" ]; then
                    # { ...|| true; } keeps pipefail callers alive when the base
                    # ref doesn't exist (e.g. repo without an origin remote).
                    _ui_lines=$({ git -C "$_wt_root" diff "origin/${_base_branch}...HEAD" \
                        -- '*.tsx' '*.jsx' '*.css' '*.svg' 2>/dev/null || true; } | wc -l | tr -d ' ')
                    if [ "${_ui_lines:-0}" -gt 0 ]; then
                        _ui_uploaded=$(jq -c --arg s "$stage" --argjson it "$iter" \
                            'select(.type=="evidence.uploaded" and .stage==$s and .iteration==$it)' \
                            "$sd/events.jsonl" 2>/dev/null | wc -l | tr -d ' ')
                        if [ "${_ui_uploaded:-0}" -eq 0 ]; then
                            _events_die "refusing stage.passed($stage iter=$iter) — diff contains UI files (.tsx/.jsx/.css/.svg) but no evidence.uploaded event found for this stage. Call upload-evidence before emitting stage.passed(build), or declare 'evidence-mode: none' in plan.md to explicitly waive browser verification."
                            return 1
                        fi
                    fi
                fi
            fi
        fi
    fi

    local payload
    if [ "$stage" = "verify" ]; then
        [ -z "$writer" ] && { _events_die "writer required for stage=verify"; return 1; }
        payload=$(jq -cn \
            --arg ts "$(_events_now)" --arg tid "$tid" --arg agent "$agent" \
            --arg stage "$stage" --argjson iter "$iter" --arg dh "$dh" \
            --arg sum "$summary" --arg writer "$writer" --argjson ev "$evidence" \
            '{schema_version:1, ts:$ts, task_id:$tid, agent:$agent, type:"stage.passed",
              stage:$stage, iteration:$iter, diff_hash:$dh, summary:$sum,
              writer:$writer, evidence:$ev}') || return 1
    else
        [ -n "$writer" ] && { _events_die "writer must be empty for stage=$stage"; return 1; }
        payload=$(jq -cn \
            --arg ts "$(_events_now)" --arg tid "$tid" --arg agent "$agent" \
            --arg stage "$stage" --argjson iter "$iter" --arg dh "$dh" \
            --arg sum "$summary" --argjson ev "$evidence" \
            '{schema_version:1, ts:$ts, task_id:$tid, agent:$agent, type:"stage.passed",
              stage:$stage, iteration:$iter, diff_hash:$dh, summary:$sum,
              evidence:$ev}') || return 1
    fi
    events_append "$sd" "$payload"
}

# events_emit_stage_failed <state_dir> <task_id> <agent> <stage> <iteration> <diff_hash> <reason>
events_emit_stage_failed() {
    local sd="${1:?state_dir}" tid="${2:?task_id}" agent="${3:?agent}"
    local stage="${4:?stage}" iter="${5:?iteration}" dh="${6:?diff_hash}" reason="${7:?reason}"
    _events_check_orchestrator_token "$sd" "events_emit_stage_failed" || return 1
    local payload
    payload=$(jq -cn \
        --arg ts "$(_events_now)" --arg tid "$tid" --arg agent "$agent" \
        --arg stage "$stage" --argjson iter "$iter" --arg dh "$dh" --arg reason "$reason" \
        '{schema_version:1, ts:$ts, task_id:$tid, agent:$agent, type:"stage.failed",
          stage:$stage, iteration:$iter, diff_hash:$dh, reason:$reason}') || return 1
    events_append "$sd" "$payload"
}

# events_emit_plan_posted <state_dir> <task_id> <kind:dev|qa> <plan_hash> <comment_url>
events_emit_plan_posted() {
    local sd="${1:?state_dir}" tid="${2:?task_id}" kind="${3:?kind}"
    local ph="${4:?plan_hash}" url="${5:?comment_url}"
    local payload
    payload=$(jq -cn \
        --arg ts "$(_events_now)" --arg tid "$tid" \
        --arg kind "$kind" --arg ph "$ph" --arg url "$url" \
        '{schema_version:1, ts:$ts, task_id:$tid, agent:"orchestrator", type:"plan.posted",
          kind:$kind, plan_hash:$ph, comment_url:$url}') || return 1
    events_append "$sd" "$payload"
}

# events_emit_evidence_uploaded <state_dir> <task_id> <stage> <iteration> <asset_count> <asset_urls_json_array> [release_tag]
# Records that evidence assets for a stage have been successfully uploaded to a GitHub
# Release. This event is REQUIRED by events_emit_stage_passed when its evidence array
# is non-empty — see "HARD GATE" comment there. Callers (typically upload-evidence.sh)
# should emit this AFTER the gh release upload succeeds and the API verifies asset state.
events_emit_evidence_uploaded() {
    local sd="${1:?state_dir}" tid="${2:?task_id}" stage="${3:?stage}"
    local iter="${4:?iteration}" count="${5:?asset_count}"
    local urls="${6:-[]}" tag="${7:-test-evidence}"
    local payload
    payload=$(jq -cn \
        --arg ts "$(_events_now)" --arg tid "$tid" \
        --arg stage "$stage" --argjson iter "$iter" --argjson cnt "$count" \
        --argjson urls "$urls" --arg tag "$tag" \
        '{schema_version:1, ts:$ts, task_id:$tid, agent:"orchestrator", type:"evidence.uploaded",
          stage:$stage, iteration:$iter, asset_count:$cnt, asset_urls:$urls, release_tag:$tag}') || return 1
    events_append "$sd" "$payload"
}

# events_emit_mirror_posted <state_dir> <task_id> <target:issue|pr> <number> <comment_id> <mirrors_event_offset>
events_emit_mirror_posted() {
    local sd="${1:?state_dir}" tid="${2:?task_id}" target="${3:?target}"
    local num="${4:?number}" cid="${5:?comment_id}" off="${6:?mirrors_event_offset}"
    local payload
    payload=$(jq -cn \
        --arg ts "$(_events_now)" --arg tid "$tid" --arg target "$target" \
        --argjson num "$num" --argjson cid "$cid" --argjson off "$off" \
        '{schema_version:1, ts:$ts, task_id:$tid, agent:"orchestrator", type:"mirror.posted",
          target:$target, number:$num, comment_id:$cid, mirrors_event_offset:$off}') || return 1
    events_append "$sd" "$payload"
}

# events_emit_finalize_pr_ready <state_dir> <task_id> <pr_number> <pr_url>
events_emit_finalize_pr_ready() {
    local sd="${1:?state_dir}" tid="${2:?task_id}" pr="${3:?pr_number}" url="${4:?pr_url}"
    local payload
    payload=$(jq -cn \
        --arg ts "$(_events_now)" --arg tid "$tid" \
        --argjson pr "$pr" --arg url "$url" \
        '{schema_version:1, ts:$ts, task_id:$tid, agent:"orchestrator", type:"finalize.pr_ready",
          pr_number:$pr, pr_url:$url}') || return 1
    events_append "$sd" "$payload"
}

# events_emit_gate_skipped <state_dir> <task_id> <hook_name> <reason> [command]
# Records a hook-level bypass (e.g. CLAUDE_EVENTS_HOOK_SKIP=1). Best-effort; callers
# should wrap with `|| true` so skip emission never blocks the bypass itself.
events_emit_gate_skipped() {
    local sd="${1:?state_dir}" tid="${2:?task_id}" hook="${3:?hook}" reason="${4:?reason}"
    local command="${5:-}"
    local payload
    if [ -n "$command" ]; then
        payload=$(jq -cn \
            --arg ts "$(_events_now)" --arg tid "$tid" \
            --arg hook "$hook" --arg reason "$reason" --arg cmd "$command" \
            '{schema_version:1, ts:$ts, task_id:$tid, agent:"hook", type:"gate.skipped",
              hook:$hook, reason:$reason, command:$cmd}') || return 1
    else
        payload=$(jq -cn \
            --arg ts "$(_events_now)" --arg tid "$tid" \
            --arg hook "$hook" --arg reason "$reason" \
            '{schema_version:1, ts:$ts, task_id:$tid, agent:"hook", type:"gate.skipped",
              hook:$hook, reason:$reason}') || return 1
    fi
    events_append "$sd" "$payload"
}

# ---------- CLI dispatch ----------

# Only run dispatch when executed, not when sourced.
# $0 being this script's name means direct execution.
if [ "${BASH_SOURCE[0]:-}" = "$0" ]; then
    cmd="${1:-}"
    shift || true
    case "$cmd" in
        state_dir)          events_state_dir "$@" ;;
        diff_hash)          events_diff_hash "$@" ;;
        append)             events_append   "$@" ;;
        latest)             events_latest   "$@" ;;
        validate)           events_validate "$@" ;;
        validate_one)       events_validate_one "$@" ;;
        emit_init)          events_emit_init "$@" ;;
        emit_stage_started) events_emit_stage_started "$@" ;;
        emit_stage_passed)  events_emit_stage_passed  "$@" ;;
        emit_stage_failed)  events_emit_stage_failed  "$@" ;;
        emit_plan_posted)   events_emit_plan_posted   "$@" ;;
        emit_mirror_posted) events_emit_mirror_posted "$@" ;;
        emit_finalize_pr_ready) events_emit_finalize_pr_ready "$@" ;;
        emit_gate_skipped)  events_emit_gate_skipped "$@" ;;
        "")
            cat >&2 <<'USAGE'
usage:
  events.sh state_dir
  events.sh diff_hash [base]
  events.sh append <state_dir> <json_payload>
  events.sh latest <state_dir> <type> [key=value ...]
  events.sh validate <jsonl_path>
  events.sh validate_one <json_line>
USAGE
            exit 2
            ;;
        *)
            _events_die "unknown subcommand: $cmd"
            exit 2
            ;;
    esac
fi
