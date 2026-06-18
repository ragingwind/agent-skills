---
description: Lightweight fix track — issue intake (or creation), fix branch, events.jsonl init, and draft PR
argument-hint: [issue-number] [--base=<branch>]
---

# /fix

Lightweight track for ad-hoc fixes outside the formal `/dev` pipeline.
Handles QA-found bugs, exploratory changes, chores, and fixes to already-tested branches.

Creates a fix branch from the resolved base, initializes pipeline state (`events.jsonl`),
pushes the branch, and opens a draft PR for collecting changes.

## Pipeline

```
SETUP → [CREATE ISSUE] → BRANCH → PUSH → DRAFT PR
```

## Flags

| Argument / Flag | Behavior |
|-----------------|----------|
| `<issue-number>` | (positional, optional) Link to existing GitHub issue |
| `--base=<branch>` | Override target base branch (default: current branch if non-trunk, else trunk) |

---

## SETUP

**Step 1 — resolve context:**

```bash
REPO=$(git remote get-url origin | sed -e 's#^.*github\.com[:/]##' -e 's#\.git$##')
REPO_ROOT=$(git rev-parse --show-toplevel)
. "${CLAUDE_PLUGIN_ROOT}/scripts/events.sh" || { echo "ERROR: events.sh missing"; exit 1; }

# Resolve trunk
_TRUNK=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null \
  | sed 's|refs/remotes/origin/||' | grep . || echo "canary")

# Resolve base: non-trunk current branch → fix targets it; trunk → fix targets trunk
CURRENT=$(git branch --show-current)
case "$CURRENT" in
  main|master|canary|develop|"$_TRUNK") BASE="$_TRUNK" ;;
  *) BASE="$CURRENT" ;;
esac

# --base=<branch> override
_BASE_OVERRIDE=$(echo "${ARGUMENTS:-}" | grep -oE -- '--base=\S+' | sed 's/--base=//')
[ -n "$_BASE_OVERRIDE" ] && BASE="$_BASE_OVERRIDE"

echo "Base branch: $BASE"
```

**Step 2 — resolve issue number:**

```bash
_FIRST=$(echo "${ARGUMENTS:-}" | awk '{print $1}')
if echo "$_FIRST" | grep -qE '^[0-9]+$'; then
  ISSUE="$_FIRST"
  ISSUE_TITLE=$(gh issue view "$ISSUE" --repo "$REPO" --json title -q '.title' 2>/dev/null \
    || echo "fix-$ISSUE")
  echo "Using issue #$ISSUE: $ISSUE_TITLE"
else
  ISSUE=""
  ISSUE_TITLE=""
fi
```

If `$ISSUE` is empty, proceed to **CREATE ISSUE**. Otherwise skip to **BRANCH**.

---

## CREATE ISSUE

Use `AskUserQuestion` when no issue number is provided.

**Prompt:**

> 이슈 번호가 없습니다. 새 GitHub 이슈를 만들까요?
>
> **이슈 제목**을 입력하세요 (비워두면 이슈 없이 진행합니다):

**Options:** Single free-form text field (title). Empty input = skip issue creation.

**If user provides title:**

```bash
ISSUE_TITLE="<user input>"
ISSUE_BODY="Fix tracked via /fix command."

ISSUE=$(gh issue create --repo "$REPO" \
  --title "$ISSUE_TITLE" \
  --body "$ISSUE_BODY" \
  | grep -oE '[0-9]+$')

echo "Created issue #$ISSUE: $ISSUE_TITLE"
```

**If user skips (empty title):**

```bash
ISSUE=""
ISSUE_TITLE="fix-$(date +%Y%m%d)"
echo "Proceeding without issue."
```

---

## BRANCH

Derive branch name and create a worktree.

```bash
# Slug from issue title or fallback timestamp
if [ -n "$ISSUE_TITLE" ]; then
  SLUG=$(printf '%s' "$ISSUE_TITLE" \
    | tr '[:upper:]' '[:lower:]' \
    | tr -cs 'a-z0-9' '-' \
    | sed -E 's/^-+|-+$//g' \
    | cut -c1-40)
else
  SLUG="fix-$(date +%Y%m%d-%H%M)"
fi

# Branch and task ID
if [ -n "$ISSUE" ]; then
  BRANCH="fix/${ISSUE}-${SLUG}"
  TASK_ID="${ISSUE}-${SLUG}"
else
  BRANCH="fix/${SLUG}"
  TASK_ID="${SLUG}"
fi

WORKTREE_NAME=$(printf '%s' "$SLUG" | cut -c1-40 | sed 's/[^a-z0-9-]/-/g')
WORKTREE_PATH="$REPO_ROOT/.claude/worktrees/${WORKTREE_NAME}"

# Sync base branch before branching
git fetch origin "$BASE"
git branch -f "$BASE" "origin/$BASE" 2>/dev/null || true

# Create branch + worktree
git worktree add -b "$BRANCH" "$WORKTREE_PATH" "origin/$BASE"
echo "Worktree: $WORKTREE_PATH  Branch: $BRANCH"
```

**Init events.jsonl in the fix worktree's state dir:**

```bash
(
  cd "$WORKTREE_PATH"
  STATE_DIR=$(events_state_dir)
  mkdir -p "$STATE_DIR"
  if [ ! -s "$STATE_DIR/events.jsonl" ]; then
    _ISSUE_NUM="${ISSUE:-0}"
    events_emit_init "$STATE_DIR" "$TASK_ID" "$REPO" "$_ISSUE_NUM" \
      "$BRANCH" "$BASE" "$BASE" "$WORKTREE_PATH"
    echo "events.jsonl initialized: $STATE_DIR"
  fi
)
```

---

## PUSH

Push from a worktree that has `node_modules` (required by the pre-push hook).

```bash
# Find worktree with node_modules; fall back to repo root
_WT_WITH_NM=$(git worktree list 2>/dev/null | awk 'NR>1{print $1}' | while read -r wt; do
  [ -d "$wt/node_modules" ] && echo "$wt" && break
done)
_PUSH_FROM="${_WT_WITH_NM:-$REPO_ROOT}"

(cd "$_PUSH_FROM" && git push origin "$BRANCH")
echo "Pushed: $BRANCH"
```

---

## DRAFT PR

Create the draft PR. The `pre-bash-pr-gate.sh` hook detects `--draft` and looks up
the head branch's state dir (via worktree list), requiring only an `init` event.

```bash
_ISSUE_REF="${ISSUE:+#$ISSUE}"
_PR_TITLE="fix: ${ISSUE_TITLE}${ISSUE:+ (#$ISSUE)}"
_PR_BODY="## Summary

Draft PR for collecting fixes.${ISSUE:+ Linked issue: #$ISSUE}

## Test plan

- [ ] (add items as fixes are committed)

${ISSUE:+Closes #$ISSUE}
"

PR_URL=$(gh pr create \
  --draft \
  --title "$_PR_TITLE" \
  --base "$BASE" \
  --head "$BRANCH" \
  --body "$_PR_BODY")

echo "Draft PR created: $PR_URL"
echo "Worktree ready at: $WORKTREE_PATH"
```

---

## Summary output

Report to the user:
- Draft PR URL
- Worktree path for working on the fix
- Branch name
- Linked issue (if any)
- Next step: run `/dev <issue>` in the worktree to start the formal build pipeline,
  or commit fixes directly and convert the PR to ready when done.
