#!/usr/bin/env bash
# project_events.sh — Phase 3 projector.
#
# Reads events.jsonl and posts one GitHub comment per stage.passed / stage.failed /
# plan.posted event that does not yet have a corresponding mirror.posted entry.
# Emits a mirror.posted event after each successful post so subsequent runs skip it.
#
# Usage:
#   project_events.sh status <state_dir>            # print pending events
#   project_events.sh post   <state_dir> [--target-num N] [--target-kind pr|issue] [--dry-run]
#                                                   # post pending comments (--dry-run = preview only)
#   project_events.sh format <state_dir> <offset>   # format one event's comment body (stdout)
#
# Manual-invocation safety (READ BEFORE running `post` without --dry-run):
#   /dev and /qa pipelines invoke `post` automatically right after each stage.passed
#   emit — that is the safe, fresh-state path. Running `post` MANUALLY against an
#   OLD state_dir is dangerous: every unmirrored historical stage.passed event will
#   post a gate comment retroactively to whatever issue/PR the projector resolves,
#   even if the work shipped long ago and the PR is closed. Older state_dirs can
#   carry many accumulated events.
#   → ALWAYS run `post --dry-run` first on an unfamiliar state_dir to see what
#     would post, and to whom, before allowing the real post to fire.
#
# Dependencies:
#   - scripts/events.sh (sourced)
#   - gh CLI (for post)
#   - jq
#
# Contract:
#   - Never deletes or rewrites events.jsonl.
#   - Exits non-zero if events.jsonl is missing or invalid.
#   - `post` is idempotent: re-running after a crash retries only unmirrored events.
#   - `post` requires an authenticated `gh` CLI and a reachable target (pr/issue).
#   - `post --dry-run` is side-effect-free: no gh call, no mirror.posted emit.
set -u

_proj_die() { echo "project_events: $*" >&2; return 1; }

_proj_require_helper() {
    local sh="$HOME/.claude/scripts/events.sh"
    [ -f "$sh" ] || { _proj_die "events.sh not found at $sh"; return 1; }
    # shellcheck disable=SC1090
    . "$sh" || { _proj_die "failed to source events.sh"; return 1; }
}

_proj_log() { echo "$@"; }

# _proj_format_event <state_dir> <offset>
# Prints the Markdown body for the gate comment corresponding to the event at
# line <offset> (1-based). Writes nothing if the event is not mirror-worthy.
_proj_format_event() {
    local sd="$1" off="$2"
    local log="$sd/events.jsonl"
    local line
    line=$(awk -v n="$off" 'NR==n' "$log")
    [ -z "$line" ] && { _proj_die "no event at offset $off"; return 1; }

    local type task_id
    type=$(printf '%s' "$line" | jq -r '.type')
    task_id=$(printf '%s' "$line" | jq -r '.task_id')

    case "$type" in
        plan.posted)
            # plan.posted is already "posted" by the original command flow —
            # we do not re-mirror it here. The standalone /plan-dev and /plan-qa
            # commands own that post.
            return 0
            ;;
        stage.passed)
            local stage iter summary writer
            stage=$(printf '%s'   "$line" | jq -r '.stage')
            iter=$(printf '%s'    "$line" | jq -r '.iteration')
            summary=$(printf '%s' "$line" | jq -r '.summary')
            writer=$(printf '%s'  "$line" | jq -r '.writer // ""')
            {
                printf '<!-- gate:%s:%s -->\n' "$stage" "$task_id"
                [ "$stage" = "verify" ] && [ -n "$writer" ] && printf 'writer: %s\n' "$writer"
                printf '\n'
                printf '## %s (iteration %s)\n\n' "$(_proj_title "$stage")" "$iter"
                printf '%s\n' "$summary"
            }
            ;;
        stage.failed)
            local stage iter reason
            stage=$(printf '%s'  "$line" | jq -r '.stage')
            iter=$(printf '%s'   "$line" | jq -r '.iteration')
            reason=$(printf '%s' "$line" | jq -r '.reason')
            {
                printf '<!-- gate:%s:%s -->\n\n' "$stage" "$task_id"
                printf '## %s — FAILED (iteration %s)\n\n' "$(_proj_title "$stage")" "$iter"
                printf '%s\n' "$reason"
            }
            ;;
        *)
            return 0  # not mirror-worthy
            ;;
    esac
}

_proj_title() {
    case "$1" in
        build)  echo "Build" ;;
        review) echo "Review" ;;
        verify) echo "Verify" ;;
        qa)     echo "QA" ;;
        *)      echo "$1" ;;
    esac
}

# _proj_pending_offsets <state_dir>
# Echoes line numbers (1-based) of stage.passed/stage.failed events that do not
# yet have a mirror.posted with a matching mirrors_event_offset.
_proj_pending_offsets() {
    local sd="$1"
    local log="$sd/events.jsonl"
    jq -r '
        [inputs
         | {type, line: input_line_number}] as $all
        |
        # Collect mirrored offsets
        [$all[] | select(.type == "mirror.posted")] as $mirrors
        | ($mirrors
           | map(.line)) as $mirror_lines
        | [$all[]
           | select(.type == "stage.passed" or .type == "stage.failed")
           | .line] as $eligible
        # We cannot cross-reference offsets within one jq call without two passes.
        # Emit eligible lines; caller filters using scripted check.
        | $eligible[]
    ' < "$log" 2>/dev/null
}

# _proj_is_mirrored <state_dir> <offset>
_proj_is_mirrored() {
    local sd="$1" off="$2"
    local log="$sd/events.jsonl"
    jq -e --argjson o "$off" '
        select(.type == "mirror.posted" and .mirrors_event_offset == $o)
    ' < "$log" >/dev/null 2>&1
}

# project_events status <state_dir>
project_events_status() {
    local sd="${1:-}"
    [ -z "$sd" ] && { _proj_die "state_dir required"; return 2; }
    [ -f "$sd/events.jsonl" ] || { _proj_die "no events.jsonl at $sd"; return 2; }
    if ! events_validate "$sd/events.jsonl" >/dev/null 2>&1; then
        _proj_die "events.jsonl failed validation"; return 2
    fi
    local off
    _proj_pending_offsets "$sd" | while read -r off; do
        [ -z "$off" ] && continue
        if ! _proj_is_mirrored "$sd" "$off"; then
            local type stage
            type=$(awk -v n="$off" 'NR==n' "$sd/events.jsonl" | jq -r '.type')
            stage=$(awk -v n="$off" 'NR==n' "$sd/events.jsonl" | jq -r '.stage // ""')
            printf 'pending: line %s %s %s\n' "$off" "$type" "$stage"
        fi
    done
}

# project_events format <state_dir> <offset>
project_events_format() {
    _proj_format_event "$1" "$2"
}

# project_events post <state_dir> [--target-num N] [--target-kind pr|issue] [--dry-run]
project_events_post() {
    local sd="${1:-}"
    shift || true
    [ -z "$sd" ] && { _proj_die "state_dir required"; return 2; }
    [ -f "$sd/events.jsonl" ] || { _proj_die "no events.jsonl at $sd"; return 2; }

    local target_num="" target_kind="" dry_run=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --target-num)  target_num="$2"; shift 2 ;;
            --target-kind) target_kind="$2"; shift 2 ;;
            --dry-run)     dry_run=1; shift ;;
            *) _proj_die "unknown flag $1"; return 2 ;;
        esac
    done

    if ! events_validate "$sd/events.jsonl" >/dev/null 2>&1; then
        _proj_die "events.jsonl failed validation — refuse to post"; return 2
    fi

    # Resolve target if not provided: PR on init.branch if one exists, else init.issue_num.
    local init_issue repo branch
    init_issue=$(events_latest "$sd" init | jq -r '.issue_num // empty' 2>/dev/null)
    repo=$(events_latest       "$sd" init | jq -r '.repo // empty'       2>/dev/null)
    branch=$(events_latest     "$sd" init | jq -r '.branch // empty'     2>/dev/null)

    if [ -z "$target_num" ] || [ -z "$target_kind" ]; then
        if command -v gh >/dev/null 2>&1 && [ -n "$repo" ] && [ -n "$branch" ]; then
            local pr
            pr=$(gh pr list -R "$repo" --head "$branch" --json number -q '.[0].number' 2>/dev/null || echo "")
            if [ -n "$pr" ]; then
                target_num="$pr"; target_kind="pr"
            elif [ -n "$init_issue" ]; then
                target_num="$init_issue"; target_kind="issue"
            fi
        fi
    fi

    # Dry-run is side-effect-free: it tolerates an unresolved target (uses placeholders
    # in the preview output) so users can audit pending events even before a PR exists.
    if [ -z "$target_num" ] || [ -z "$target_kind" ]; then
        if [ "$dry_run" -eq 1 ]; then
            target_num="${target_num:-?}"
            target_kind="${target_kind:-?}"
        else
            _proj_die "cannot resolve target (pass --target-num and --target-kind)"
            return 2
        fi
    fi

    local posted=0 skipped=0 failed=0 off body url comment_id
    while read -r off; do
        [ -z "$off" ] && continue
        if _proj_is_mirrored "$sd" "$off"; then
            skipped=$((skipped+1))
            continue
        fi
        body=$(_proj_format_event "$sd" "$off" 2>/dev/null || true)
        [ -z "$body" ] && { skipped=$((skipped+1)); continue; }

        if [ "$dry_run" -eq 1 ]; then
            printf '=== [dry-run] would post offset %s → %s#%s ===\n' "$off" "$target_kind" "$target_num"
            printf '%s\n\n' "$body"
            posted=$((posted+1))
            continue
        fi

        if [ "$target_kind" = "pr" ]; then
            url=$(printf '%s' "$body" | gh pr comment "$target_num" -R "$repo" --body-file - 2>/dev/null) || url=""
        else
            url=$(printf '%s' "$body" | gh issue comment "$target_num" -R "$repo" --body-file - 2>/dev/null) || url=""
        fi

        if [ -z "$url" ]; then
            failed=$((failed+1))
            continue
        fi

        comment_id=$(printf '%s' "$url" | sed -n 's/.*#issuecomment-\([0-9]*\).*/\1/p')
        local task_id
        task_id=$(awk -v n="$off" 'NR==n' "$sd/events.jsonl" | jq -r '.task_id')
        events_emit_mirror_posted "$sd" "$task_id" "$target_kind" "$target_num" "${comment_id:-0}" "$off" \
            2>/dev/null || true
        posted=$((posted+1))
    done < <(_proj_pending_offsets "$sd")

    if [ "$dry_run" -eq 1 ]; then
        _proj_log "projector (dry-run): would-post=$posted skipped=$skipped target=${target_kind}#${target_num}"
    else
        _proj_log "projector: posted=$posted skipped=$skipped failed=$failed target=${target_kind}#${target_num}"
    fi
    [ "$failed" -eq 0 ] || return 1
    return 0
}

# ---------- CLI dispatch ----------
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    _proj_require_helper || exit 2
    cmd="${1:-}"
    shift || true
    case "$cmd" in
        status) project_events_status "$@" ;;
        post)   project_events_post   "$@" ;;
        format) project_events_format "$@" ;;
        "")
            cat >&2 <<'USAGE'
usage:
  project_events.sh status <state_dir>
  project_events.sh post   <state_dir> [--target-num N --target-kind pr|issue] [--dry-run]
  project_events.sh format <state_dir> <offset>

  --dry-run: side-effect-free preview. Reads events.jsonl, formats pending events
  to stdout, does NOT call gh and does NOT emit mirror.posted. Tolerates an
  unresolved target (prints `?#?`). Use before a real run to audit what would post.

  WARNING: `post` without --dry-run on an OLD state_dir will retroactively post
  every unmirrored historical event to the resolved target (often a long-closed
  issue/PR). /dev and /qa invoke `post` automatically on FRESH state — that path
  is safe. For manual invocation, always `--dry-run` first.
USAGE
            exit 2
            ;;
        *) _proj_die "unknown subcommand: $cmd"; exit 2 ;;
    esac
fi
