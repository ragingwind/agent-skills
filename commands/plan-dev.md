---
description: Standalone dev plan — generate implementation plan and post as issue comment (break-point)
argument-hint: <issue-number> [--dry-run] [--approved]
---

# /plan-dev

Standalone plan command. Generates a development plan via the `planning-features` skill, shows it to the user for review, and posts it as an issue comment only after confirmation.

For automatic posting without confirmation, pass `--approved`. For fully in-session approval, use `/dev` directly.

## Pipeline

```
SETUP → PLAN (skill) → PREVIEW (show + ask) → POST (comment + markers)
```

## Stages

| Stage | Owner | Purpose |
|-------|-------|---------|
| SETUP | orchestrator | Compute task context, body hash |
| PLAN | orchestrator | `Skill("planning-features", args: "--mode dev")` direct invocation |
| PREVIEW | orchestrator | Show plan to user in conversation language; ask for confirmation (skipped with `--approved`) |
| POST | orchestrator | Post plan comment with `gate:dev-plan` + `plan-hash` markers |

## SETUP

**Step 0 — parse flags:**
```bash
DRY_RUN=0
APPROVED=0
case " $ARGUMENTS " in *" --dry-run "*) DRY_RUN=1 ;; esac
case " $ARGUMENTS " in *" --approved "*) APPROVED=1 ;; esac
```

**Step 1 — initialize task context:**
```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
# STATE_DIR is the single per-branch artifact + events.jsonl location.
. "${CLAUDE_PLUGIN_ROOT}/scripts/events.sh" || { echo "ERROR: scripts/events.sh missing"; exit 1; }
STATE_DIR=$(events_state_dir) || { echo "ERROR: cannot resolve state dir (not in a git worktree?)"; exit 1; }
mkdir -p "$STATE_DIR"

# Issue number: first positional arg (e.g. /plan-dev 123) takes priority;
# on re-entry (events.jsonl already exists) resolve from the init event.
_FIRST_ARG=$(echo "$ARGUMENTS" | awk '{print $1}')
if echo "$_FIRST_ARG" | grep -qE '^[0-9]+$'; then
  ISSUE="$_FIRST_ARG"
elif [ -f "$STATE_DIR/events.jsonl" ]; then
  ISSUE=$(events_latest "$STATE_DIR" init 2>/dev/null | jq -r '.issue_num // empty' 2>/dev/null || echo "")
fi
[ -z "${ISSUE:-}" ] && { echo "ERROR: no issue number — pass as first arg (e.g. /plan-dev 123)"; exit 1; }
REPO=$(git remote get-url origin | sed -e 's#^.*github\.com[:/]##' -e 's#\.git$##')

# Derive SLUG: use feature-branch slug if available, else issue title
CURRENT_BRANCH=$(git branch --show-current)
case "$CURRENT_BRANCH" in
  main|master|canary|develop)
    SLUG=$(gh issue view "$ISSUE" --json title -q '.title' \
      | tr '[:upper:]' '[:lower:]' \
      | tr -cs 'a-z0-9' '-' \
      | sed -E 's/^-+|-+$//g' \
      | cut -c1-40) ;;
  *)
    SLUG=$(echo "$CURRENT_BRANCH" | sed 's|.*/||' | tr '/' '-') ;;
esac

TASK_ID="${ISSUE}-${SLUG}"

echo "TASK_ID=$TASK_ID  STATE_DIR=$STATE_DIR"
```

**Step 1b — emit events.jsonl init event (source of truth for pipeline state):**

Records an `init` event to the plugin-scoped `events.jsonl`. Idempotent: if `events.jsonl` already has an init event, this step is a no-op. **Skipped under `--dry-run`** so dry-run is non-destructive.

```bash
if [ "$DRY_RUN" != "1" ] && [ ! -s "$STATE_DIR/events.jsonl" ]; then
  _EV_BASE="${BASE_BRANCH:-$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' | grep . || echo main)}"
  events_emit_init "$STATE_DIR" "$TASK_ID" "$REPO" "$ISSUE" \
    "$(git branch --show-current)" "$_EV_BASE" "$_EV_BASE" "$REPO_ROOT"
fi
# Orchestrator writer token — required for stage.passed/failed emits.
if [ -f "$STATE_DIR/.orch-writer-token" ]; then
  export ORCHESTRATOR_TOKEN=$(cat "$STATE_DIR/.orch-writer-token")
fi
echo "events.jsonl: $STATE_DIR/events.jsonl"
```

**Step 2 — verify issue exists:**
```bash
gh issue view "$ISSUE" --json number >/dev/null 2>&1 \
  || { echo "ERROR: issue #$ISSUE not accessible"; exit 1; }
```

**Step 3 — `--dry-run` verbose status dump (exits before PLAN stage):**

If `--dry-run`, print what PLAN+POST would do, then exit 0. **No events.jsonl write, no skill invocation, no GitHub comment posted.**

```bash
if [ "$DRY_RUN" = "1" ]; then
  BODY_HASH=$(gh issue view "$ISSUE" --json body -q '.body' | shasum -a 256 | awk '{print $1}' | cut -c1-16)
  echo
  echo "[dry-run] /plan-dev status for issue #$ISSUE"
  echo "  TASK_ID       = $TASK_ID"
  echo "  STATE_DIR     = $STATE_DIR"
  echo "  REPO          = $REPO"
  echo "  branch        = $(git branch --show-current)"
  echo "  BODY_HASH     = $BODY_HASH (would be embedded as <!-- plan-hash:... -->)"
  echo "  --approved    = $APPROVED (1 = auto-post; 0 = show plan and ask first)"
  echo
  echo "  events.jsonl  = $([ -s "$STATE_DIR/events.jsonl" ] && echo 'EXISTS (would be reused)' || echo 'absent (would be created on real run)')"
  echo "  plan file     = $STATE_DIR/${TASK_ID}-plan.md"
  echo "                  $([ -s "$STATE_DIR/${TASK_ID}-plan.md" ] && echo 'EXISTS' || echo 'absent (skill would create it)')"
  echo
  echo "  GitHub effects on real run:"
  echo "    • PREVIEW: plan shown in conversation; user confirmation required (skipped with --approved)"
  echo "    • POST one new comment to issue #$ISSUE with body=plan + gate marker (only after approval)"
  echo "    • issue body, title, labels: NOT modified"
  echo
  echo "[dry-run] exiting before PLAN stage (no state changes made)"
  exit 0
fi
```

## PLAN

Invoke the skill:
```
Skill(skill: "planning-features", args: "--mode dev")
```

Skill writes output to `$STATE_DIR/${TASK_ID}-plan.md`. Interactive mode engages the user via `AskUserQuestionTool` to refine requirements (per `skills/planning-features/SKILL.md`).

## PREVIEW

Show the generated plan to the user and confirm before posting to GitHub.

1. Read `$STATE_DIR/${TASK_ID}-plan.md` and **output its full contents verbatim as markdown text in the conversation** (the terminal console). Do NOT rely on the Read tool's side-panel display — the full plan text MUST appear as part of your response text so the user can read it in the main console without opening any panel.
2. After the full plan text, add a short section header (2–4 bullet points) **in the same language the user is using** (e.g., Korean if the user wrote in Korean) summarizing the key decisions.
3. **If `--approved` is set**: skip `AskUserQuestion` and proceed directly to POST.
4. **Otherwise**: end with a plain-text confirmation prompt in the user's language. Do NOT use `AskUserQuestion` UI buttons. Example for Korean: `위 플랜을 이슈에 게시하려면 **apply**, 취소하려면 **cancel** 을 입력해주세요.`
   - On **apply** (or equivalent affirmative): proceed to POST.
   - On **revise** or revision feedback: collect the feedback inline, re-invoke `Skill("planning-features", args: "--mode dev")` with the feedback, then return to step 1 of PREVIEW.
   - On **cancel** / **abort**: halt without posting; emit `stage.failed(dev-plan)` event if events.jsonl exists; inform the user that no comment was posted and no gate marker was written.

> **Why full text in the console**: Tool call results (Read, Write, Bash) appear only in the side panel. A user watching the terminal cannot see those. The plan must be readable without any side panel interaction.

## POST

```bash
PLAN_PATH="$STATE_DIR/${TASK_ID}-plan.md"
[ -s "$PLAN_PATH" ] || { echo "ERROR: plan file missing or empty at $PLAN_PATH"; exit 1; }

# Compute staleness hash from the current issue body (the skill does NOT
# modify the issue body — the body is the user-authored source of truth).
# /dev later re-hashes the body and rejects the run if the user edited the
# body after this plan was posted.
BODY_HASH=$(gh issue view "$ISSUE" --json body -q '.body' | shasum -a 256 | awk '{print $1}' | cut -c1-16)
echo "BODY_HASH=$BODY_HASH"

_EV_COMMENT_URL=$(gh issue comment "$ISSUE" --body "$(cat <<EOF
$(cat "$PLAN_PATH")

---
<!-- gate:dev-plan:${TASK_ID} -->
<!-- plan-hash:${BODY_HASH} -->
EOF
)")
echo "$_EV_COMMENT_URL"

echo "Plan posted to issue #$ISSUE (TASK_ID=$TASK_ID, hash=$BODY_HASH)"

# Phase 1 ghost recording — plan.posted event (best-effort, never blocks)
if [ -n "${STATE_DIR:-}" ] && command -v events_emit_plan_posted >/dev/null 2>&1; then
  events_emit_plan_posted "$STATE_DIR" "$TASK_ID" "dev" \
    "$BODY_HASH" "${_EV_COMMENT_URL:-}" 2>/dev/null || true
fi
```

## Re-run behavior

Re-running `/plan-dev` posts a new comment; prior comments are preserved (history). The **latest** comment carrying `<!-- gate:dev-plan:... -->` is the source of truth. `/dev` reads the latest `plan-hash` and compares against the current issue body hash — mismatch = stale plan → error.

## Break-point contract

The PREVIEW stage outputs the full plan text in the conversation (terminal console) and waits for the user's confirmation before posting to GitHub. The user reads the plan directly in the console, then decides:

- **apply** (default affirmative) → posts the comment with gate markers
- **revise** or revision feedback → loops back to replanning with feedback
- **cancel** / **abort** → exits cleanly with no GitHub side effects
- **`--approved` flag** → skips the confirmation prompt; posts immediately after plan generation

After the comment is posted, the user runs `/dev` (which detects the `gate:dev-plan` marker and skips its own PLAN stage) or edits the issue body and re-runs `/plan-dev`.

## Gate marker

`<!-- gate:dev-plan:${TASK_ID} -->` — read by `/dev` PLAN stage (auto-skips PLAN if a matching marker is found; bypass entirely with `/dev --skip-plan`).
