---
name: cleanup
description: Clean up stale worktrees and orphan plugin-scoped state dirs
---

# /cleanup

Cleans up stale state from completed or abandoned work.

## What it cleans

1. **Stale git worktrees** — `git worktree prune`
2. **Orphan plugin-scoped state dirs** under `$HOME/.local/state/agent-skills/<hostname>/<project-slug>/<branch-slug>/` — identified by reading the init event's `worktree_root` + `branch` and verifying both still exist.

> Project-owned resources (dev server processes, build caches, etc.) are cleaned by
> project-level hooks and scripts — not by this skill. See the target project's CLAUDE.md.

## Steps

### 1. Prune stale worktrees
```bash
git worktree prune
git worktree list
```

### 2. Prune orphan plugin state dirs

Environment overrides:
- `CLEANUP_DRY_RUN=1` (default) — only report; `CLEANUP_DRY_RUN=0` to actually delete
- `CLEANUP_AGE_DAYS=7` (default) — skip state dirs whose `events.jsonl` was modified within N days even if the worktree/branch is gone (safety margin for in-flight work that temporarily disappears from `git branch --list`)

```bash
. "${CLAUDE_PLUGIN_ROOT}/scripts/events.sh" 2>/dev/null || true
HOST=$(hostname 2>/dev/null | tr '[:upper:]' '[:lower:]' | sed 's/\./-/g')
PLUGIN_ROOT="$HOME/.local/state/agent-skills/${HOST}"

AGE_DAYS="${CLEANUP_AGE_DAYS:-7}"
DRY_RUN="${CLEANUP_DRY_RUN:-1}"

_mtime() {
  # POSIX-portable mtime in epoch seconds (macOS BSD stat vs Linux GNU stat).
  stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null
}

if [ ! -d "$PLUGIN_ROOT" ]; then
  echo "No plugin state root at $PLUGIN_ROOT — nothing to prune."
else
  NOW=$(date +%s)
  # State dirs are at depth 2: <project-slug>/<branch-slug>/events.jsonl
  find "$PLUGIN_ROOT" -mindepth 3 -maxdepth 3 -type f -name events.jsonl 2>/dev/null \
    | while IFS= read -r evfile; do
      state_dir=$(dirname "$evfile")
      init_line=$(head -n1 "$evfile" 2>/dev/null)
      [ -z "$init_line" ] && continue

      wt_root=$(printf '%s' "$init_line" | jq -r '.worktree_root // empty' 2>/dev/null)
      branch=$(printf '%s' "$init_line" | jq -r '.branch // empty' 2>/dev/null)

      reason=""
      if [ -z "$wt_root" ]; then
        reason="missing worktree_root in init event"
      elif ! git -C "$wt_root" rev-parse --git-dir >/dev/null 2>&1; then
        reason="worktree removed: $wt_root"
      elif [ -n "$branch" ] \
        && ! git -C "$wt_root" rev-parse --verify "refs/heads/$branch" >/dev/null 2>&1; then
        reason="branch deleted: $branch (worktree still at $wt_root)"
      fi

      [ -z "$reason" ] && continue

      last_mod=$(_mtime "$evfile")
      [ -z "$last_mod" ] && continue
      age_days=$(( (NOW - last_mod) / 86400 ))

      if [ "$age_days" -lt "$AGE_DAYS" ]; then
        echo "SKIP  (${age_days}d < ${AGE_DAYS}d): $state_dir — $reason"
        continue
      fi

      if [ "$DRY_RUN" = "1" ]; then
        echo "WOULD DELETE (${age_days}d, $reason): $state_dir"
      else
        echo "DELETE      (${age_days}d, $reason): $state_dir"
        rm -rf "$state_dir"
      fi
    done

  # Reap empty project-slug dirs left behind by deletions.
  if [ "$DRY_RUN" != "1" ]; then
    find "$PLUGIN_ROOT" -mindepth 1 -maxdepth 2 -type d -empty -exec rmdir {} + 2>/dev/null || true
  fi
fi
```

## Safety

- Default is dry-run. Review output before setting `CLEANUP_DRY_RUN=0`.
- Age gate (`CLEANUP_AGE_DAYS=7`) prevents accidental deletion of active work whose
  branch is temporarily missing (e.g., mid-rebase, stash, pushed-and-deleted-locally).
- `.orch-writer-token` is deleted with the state dir — this is intended; a new token
  is minted on the next `events_emit_init` call for that branch.
- The cleanup NEVER touches `events.jsonl` contents directly — it only removes the
  entire state dir tree when the init event's worktree/branch is gone.
