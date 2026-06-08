---
description: Standalone QA plan — generate qa-plan and post as issue comment (break-point)
argument-hint: <issue-number | commit-range | natural-language-hint> [--dry-run] [--approved]
---

# /plan-qa

Standalone QA plan command. Generates a qa-plan via the `planning-features` skill, runs it through the reviewer agent, shows it to the user for review, and posts it as an issue comment only after confirmation.

For automatic posting without confirmation, pass `--approved`. For fully in-session approval, use `/qa` directly.

## Pipeline

```
SETUP → PLAN (skill) → REVIEW (reviewer agent + Ralph) → PREVIEW (show + ask) → POST (comment + markers)
```

## Stages

| Stage | Owner | Purpose |
|-------|-------|---------|
| SETUP | orchestrator | Compute task context, body hash |
| PLAN | orchestrator | `Skill("planning-features", args: "--mode qa")` direct invocation — produces draft qa-plan |
| REVIEW | `reviewer` agent (Ralph loop) | Audits draft qa-plan; rejects mock-only environments and missing evidence; planner re-invokes skill with feedback until APPROVED |
| PREVIEW | orchestrator | Show approved qa-plan to user in conversation language; ask for confirmation (skipped with `--approved`) |
| POST | orchestrator | Post qa-plan comment with `gate:qa-plan` + `plan-hash` markers |

## Planner ≠ Reviewer principle (MANDATORY)

The agent that **writes** the qa-plan (`planning-features` skill) is NEVER the agent that **approves** it. Approval requires an independent `reviewer` agent dispatch.

The orchestrator MUST NOT skip the REVIEW stage. There is no `--skip-review` flag. The only way to bypass is to abort `/plan-qa` entirely.

> **Why**: a single agent that both writes a plan and judges its sufficiency systematically misses the criteria it failed to think of. An independent reviewer applies a separate decision tree against the qa-plan output. See `rules/orchestration.md` → "Planner ≠ Reviewer" for the full rationale.

## Real-environment principle (MANDATORY)

The qa-plan MUST define scenarios that exercise the **production code path** in the **real user environment**. The reviewer agent rejects qa-plans whose `Required state` describes mock-only environments. Detection patterns (the reviewer scans the qa-plan text for these tokens):

| Pattern | Why rejected |
|---------|--------------|
| `page.route(` | Playwright mocking a production HTTP endpoint |
| `route.fulfill(` | Test-harness-fabricated response replacing production response |
| `withEnforceCsp(` (or any in-test header/body injection helper) | Bypasses the production injection code path |
| `synthesized fixture`, `hand-written fixture` | Author-written HTML standing in for real upstream output |
| Any environment described purely in test-harness terms instead of real-service terms (no real URL, no real account, no real running process) | The validation does not exercise what the user uses |
| Equivalent expressions in any other language used in qa-plans (the reviewer agent normalizes the qa-plan body to English meaning before applying the matcher) | qa-plans drafted in non-English languages must still be audited against the same rules |

If any P1/P2 scenario matches these patterns, the reviewer agent issues `CHANGES_REQUIRED` and the orchestrator MUST loop until the planner produces real-environment scenarios OR explicitly declares `mock_only: true` with a rationale that includes the corresponding real-environment scenario marked as `BLOCKED` (with the missing infrastructure named).

The reviewer agent is the single source of truth for whether a qa-plan satisfies these principles.

## Anchor resolution

The first positional arg to `/plan-qa` can be:

| Type | Pattern | Handling |
|------|---------|----------|
| Issue number | all-digits (e.g. `123`) | `ISSUE=arg`; use existing issue |
| Commit / tag range | contains `..` (e.g. `abc..HEAD`, `v0.1.0..HEAD`) | `COMMIT_RANGE=arg`; auto-create issue |
| Natural-language hint | anything else (e.g. `"last 10 commits"`, `"since v0.1.0"`) | **Orchestrator resolves BEFORE bash SETUP runs** |
| (absent) | — | HARD STOP — unless `events.jsonl` has a prior `init` event (re-entry) |

**Orchestrator responsibilities for natural-language hints** (before SETUP bash runs):

1. Use `git log`, `git tag`, `git describe`, `git log --since`, `git log --grep` etc. to convert the hint to a concrete `BASE..HEAD` range.
   - "last N commits" → `HEAD~N..HEAD`
   - "since v1.0 tag" → `v1.0..HEAD`
   - "since yesterday" → resolve start SHA via `git log --since=yesterday --format=%H | tail -1`, then `<sha>..HEAD`
   - keyword hint → `git log --grep=<keyword> --oneline` to find candidate commits, propose a contiguous range
   - The orchestrator MUST handle hints in any natural language (the codebase has multilingual users); the rules above are language-agnostic — translate the hint to its English meaning first, then apply the rule
2. Display the resolved range for transparency before proceeding: `Resolved: '<hint>' → <range> (<short-sha>..<short-sha>)`
3. If ambiguous (multiple non-contiguous regions, or >20 candidates) → use `AskUserQuestion` to confirm. **Never silently pick.**
4. Set `COMMIT_RANGE=<resolved>` (env var) before the SETUP bash block runs. Optionally also set `ISSUE_TITLE`, `ISSUE_BODY`, `ISSUE_ORIGIN_HINT` for richer issue content.

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

# Anchor: first positional arg takes priority; on re-entry resolve from events.jsonl.
# Natural-language hints MUST be resolved by the orchestrator BEFORE this bash block runs
# (see "Anchor resolution" section). Orchestrator pre-sets COMMIT_RANGE env var.
_FIRST_ARG=$(echo "$ARGUMENTS" | awk '{print $1}')
COMMIT_RANGE="${COMMIT_RANGE:-}"  # May be pre-set by orchestrator (resolved from NL hint)

if echo "$_FIRST_ARG" | grep -qE '^[0-9]+$'; then
  ISSUE="$_FIRST_ARG"
elif echo "$_FIRST_ARG" | grep -q '\.\.'; then
  COMMIT_RANGE="$_FIRST_ARG"
elif [ -n "$COMMIT_RANGE" ]; then
  : # already resolved by orchestrator from natural-language hint
elif [ -f "$STATE_DIR/events.jsonl" ]; then
  ISSUE=$(events_latest "$STATE_DIR" init 2>/dev/null | jq -r '.issue_num // empty' 2>/dev/null || echo "")
elif [ -n "${_FIRST_ARG:-}" ]; then
  echo "ERROR: orchestrator must resolve natural-language hint to a commit range before bash SETUP"
  echo "  Hint received: '$_FIRST_ARG'"
  echo "  Expected: all-digits (issue number) or 'abc..def' (commit range)"
  exit 1
fi

[ -z "${ISSUE:-}" ] && [ -z "${COMMIT_RANGE:-}" ] && {
  echo "ERROR: provide an anchor — issue number, commit range, or natural-language hint"
  echo "  /plan-qa 123                   — QA against issue #123"
  echo "  /plan-qa abc123..HEAD          — QA against commit range (auto-creates issue)"
  echo "  /plan-qa \"last 10 commits\"     — natural-language hint (orchestrator resolves first)"
  exit 1
}

# Auto-create GitHub issue when a commit range is given (no issue anchor)
if [ -n "$COMMIT_RANGE" ]; then
  _BRANCH_NOW=$(git branch --show-current)
  _COMMITS=$(git log --oneline "$COMMIT_RANGE" 2>/dev/null) \
    || { echo "ERROR: invalid commit range: '$COMMIT_RANGE'"; exit 1; }
  [ -z "$_COMMITS" ] && { echo "ERROR: commit range '$COMMIT_RANGE' contains no commits"; exit 1; }
  _DIFFSTAT=$(git diff --stat "$COMMIT_RANGE" 2>/dev/null || echo "[diff unavailable]")
  : "${ISSUE_ORIGIN_HINT:=$COMMIT_RANGE}"
  : "${ISSUE_TITLE:=qa: ${COMMIT_RANGE} on ${_BRANCH_NOW}}"
  if [ -z "${ISSUE_BODY:-}" ]; then
    ISSUE_BODY=$(cat <<BODY_EOF
## Ad-hoc QA session

**Range**: \`${COMMIT_RANGE}\`
**Hint**: ${ISSUE_ORIGIN_HINT}
**Branch**: ${_BRANCH_NOW}
**Created**: $(date -u +%Y-%m-%dT%H:%M:%SZ)

## Commits in scope
\`\`\`
${_COMMITS}
\`\`\`

## Diff summary
\`\`\`
${_DIFFSTAT}
\`\`\`

_Auto-created by /plan-qa for ad-hoc QA. Close after session ends._
BODY_EOF
)
  fi
  if [ "$DRY_RUN" = "1" ]; then
    ISSUE="<dry-run-stub>"
    echo "[dry-run] would create QA session issue (range: $COMMIT_RANGE) — skipped"
  else
    ISSUE=$(gh issue create \
      --title "$ISSUE_TITLE" \
      --body "$ISSUE_BODY" \
      | grep -oE '[0-9]+$' | tail -1)
    [ -z "${ISSUE:-}" ] && { echo "ERROR: gh issue create failed or returned no issue number"; exit 1; }
    echo "Auto-created QA session issue #$ISSUE (range: $COMMIT_RANGE)"
  fi
fi
REPO=$(git remote get-url origin | sed -e 's#^.*github\.com[:/]##' -e 's#\.git$##')

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

BODY_HASH=$(gh issue view "$ISSUE" --json body -q '.body' | shasum -a 256 | awk '{print $1}' | cut -c1-16)

echo "TASK_ID=$TASK_ID  BODY_HASH=$BODY_HASH  STATE_DIR=$STATE_DIR"
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
[ "$ISSUE" = "<dry-run-stub>" ] || gh issue view "$ISSUE" --json number >/dev/null 2>&1 \
  || { echo "ERROR: issue #$ISSUE not accessible"; exit 1; }
```

**Step 3 — `--dry-run` verbose status dump (exits before PLAN stage):**

If `--dry-run`, print what PLAN+REVIEW+POST would do, then exit 0. **No events.jsonl write, no skill invocation, no GitHub comment posted, no auto-created issue.**

```bash
if [ "$DRY_RUN" = "1" ]; then
  echo
  echo "[dry-run] /plan-qa status (issue #$ISSUE)"
  echo "  TASK_ID       = $TASK_ID"
  echo "  STATE_DIR     = $STATE_DIR"
  echo "  REPO          = $REPO"
  echo "  branch        = $(git branch --show-current)"
  if [ "$ISSUE" != "<dry-run-stub>" ]; then
    echo "  BODY_HASH     = $BODY_HASH (would be embedded as <!-- plan-hash:... -->)"
  fi
  echo
  echo "  events.jsonl  = $([ -s "$STATE_DIR/events.jsonl" ] && echo 'EXISTS (would be reused)' || echo 'absent (would be created on real run)')"
  echo "  qa-plan file  = $STATE_DIR/${TASK_ID}-qa.md"
  echo "                  $([ -s "$STATE_DIR/${TASK_ID}-qa.md" ] && echo 'EXISTS' || echo 'absent (skill would create it)')"
  echo
  echo "  --approved    = $APPROVED (1 = auto-post; 0 = show plan and ask first)"
  echo
  echo "  GitHub effects on real run:"
  if [ "$ISSUE" = "<dry-run-stub>" ]; then
    echo "    • CREATE one new issue (commit-range mode) titled \"qa: ${COMMIT_RANGE}\""
  fi
  echo "    • PREVIEW: qa-plan shown in conversation; user confirmation required (skipped with --approved)"
  echo "    • POST one new comment to the issue with body=qa-plan + gate marker (only after approval)"
  echo "    • issue body, title, labels: NOT modified"
  echo
  echo "[dry-run] exiting before PLAN stage (no state changes made)"
  exit 0
fi
```

## PLAN

Invoke the skill:
```
Skill(skill: "planning-features", args: "--mode qa")
```

Skill writes output to `$STATE_DIR/${TASK_ID}-qa.md`. The skill handles handoff collection (dev-plan, TIA, E2E scenarios) and produces the qa-plan structure (scenarios, capability mapping, scope boundary).

> The skill produces a **draft**. The plan is not authoritative until the REVIEW stage approves it. The orchestrator MUST NOT post the gate marker after PLAN — only after REVIEW exits with APPROVED.

## REVIEW (Ralph loop — MANDATORY)

The REVIEW stage is a Ralph retry loop with planner ≠ reviewer separation:

```
executor   = reviewer agent (Mode: qa-plan-review — see agents/reviewer.md)
verifier   = review verdict == APPROVED AND 0 CRITICAL AND 0 HIGH findings
fixer      = orchestrator re-invokes Skill("planning-features", args: "--mode qa")
             with the reviewer's findings file ($STATE_DIR/${TASK_ID}-qa-review.md)
             prepended to the prompt as feedback
terminator = max 3 iterations OR same-findings 3 times → HARD STOP
```

### REVIEW iteration (per Ralph cycle)

1. **Dispatch reviewer agent** in qa-plan-review mode with these inputs:
   - `$STATE_DIR/${TASK_ID}-qa.md` — the draft qa-plan
   - `$STATE_DIR/${TASK_ID}-plan.md` (if dev-plan exists) — handoff context
   - `git diff $BASE_BRANCH...HEAD --stat` — implementation scope
   - Iteration number (for context)

2. **Reviewer writes** `$STATE_DIR/${TASK_ID}-qa-review.md` with verdict + findings.

3. **Orchestrator inspects** the verdict:
   - `APPROVED` (0 CRITICAL / 0 HIGH) → exit Ralph loop, proceed to POST
   - `CHANGES_REQUIRED` (any CRITICAL or HIGH) → continue Ralph

4. **Fixer** (next iteration's executor input):
   - Append the review file's `## Findings` section to a feedback log: `$STATE_DIR/${TASK_ID}-qa-feedback.log`
   - Re-invoke `Skill("planning-features", args: "--mode qa")` with feedback log path injected
   - The skill MUST read the feedback log and address each finding before re-emitting the qa-plan
   - Skill overwrites `$STATE_DIR/${TASK_ID}-qa.md` with the revised plan

5. **Cleanup before next iteration**:
   - `rm "$STATE_DIR/${TASK_ID}-qa-review.md"` — old review file deleted
   - Iteration counter incremented

### Reviewer focus (qa-plan-review mode)

The reviewer agent applies these CRITICAL/HIGH gates (full criteria in `agents/reviewer.md` → "QA Plan Review Mode"):

| Severity | Trigger |
|----------|---------|
| 🔴 CRITICAL | Any P1 scenario's `Required state` uses mock-only environment (page.route, route.fulfill, synthesized fixture, withEnforceCsp, etc.) without explicit `mock_only: true` declaration |
| 🔴 CRITICAL | A HIGH/CRITICAL capability has no scenario covering it (per qa-plan §Capability Inventory C-number traceability) |
| 🔴 CRITICAL | A scenario lacks a concrete `Expected evidence` filename matching the `s<N>-<slug>.{webm,png}` pattern |
| 🔴 CRITICAL | A scenario's success conditions reference internal state (component names, API routes, code terms) instead of observable user-visible outcomes |
| 🟠 HIGH | `## System Access` lacks a real URL or real credentials path |
| 🟠 HIGH | A scenario marked `mock_only: true` without a corresponding `BLOCKED` real-environment companion scenario |
| 🟠 HIGH | qa-plan claims TIA-gap is empty without listing the candidate adjacent-layer specs that were checked |
| 🟠 HIGH | `Coverage Adequacy Check` mismatches the actual scenarios (false coverage claim) |

The reviewer agent MUST NOT downgrade these to MEDIUM. Downgrade requires explicit user override via `AskUserQuestion` from the orchestrator (the reviewer agent itself cannot self-override).

### HARD STOP conditions

- Iteration 3 produced CHANGES_REQUIRED → orchestrator HALTS `/plan-qa`. User must edit the dev-plan or change scope before retry.
- Same finding repeats across 3 iterations → orchestrator HALTS. The skill is unable to address that finding; user intervention required.
- Reviewer fails to produce a verdict (e.g., agent crash, file empty) → orchestrator HALTS.

On HARD STOP, the orchestrator emits `stage.failed(qa-plan-review)` and reports to the user. No `gate:qa-plan` marker is posted.

## PREVIEW

Show the reviewer-approved qa-plan to the user and confirm before posting to GitHub.

1. Read `$STATE_DIR/${TASK_ID}-qa.md` and display its full contents in the conversation.
2. Present a brief summary (2–4 bullet points covering scenarios, scope, and key acceptance criteria) **in the same language the user is using** (e.g., Korean if the user wrote in Korean).
3. **If `--approved` is set**: skip `AskUserQuestion` and proceed directly to POST.
4. **Otherwise**: use `AskUserQuestion` with these options (Approve is the default):
   - **Approve** — post to GitHub issue as-is
   - **Revise** — collect freeform feedback inline, re-invoke `Skill("planning-features", args: "--mode qa")` with the feedback, re-run REVIEW, then return to step 1 of PREVIEW
   - **Abort** — halt without posting; emit `stage.failed(qa-plan)` event if events.jsonl exists

On Abort: inform the user that no comment was posted to GitHub and no gate marker was written.

## POST

```bash
PLAN_PATH="$STATE_DIR/${TASK_ID}-qa.md"
[ -s "$PLAN_PATH" ] || { echo "ERROR: qa-plan file missing or empty at $PLAN_PATH"; exit 1; }

# Structural sanity — same checks tester agent Phase 1 applies
grep -q '^### S[0-9]\+:' "$PLAN_PATH" \
  || { echo "ERROR: qa-plan has no scenarios (### S<N>:)"; exit 1; }
grep -q '^\*\*Expected evidence\*\*:' "$PLAN_PATH" \
  || { echo "ERROR: qa-plan missing 'Expected evidence' entries"; exit 1; }

_EV_COMMENT_URL=$(gh issue comment "$ISSUE" --body "$(cat <<EOF
$(cat "$PLAN_PATH")

---
<!-- gate:qa-plan:${TASK_ID} -->
<!-- plan-hash:${BODY_HASH} -->
EOF
)")
echo "$_EV_COMMENT_URL"

echo "QA plan posted to issue #$ISSUE (TASK_ID=$TASK_ID, hash=$BODY_HASH)"

# Phase 1 ghost recording — plan.posted event (best-effort, never blocks)
if [ -n "${STATE_DIR:-}" ] && command -v events_emit_plan_posted >/dev/null 2>&1; then
  events_emit_plan_posted "$STATE_DIR" "$TASK_ID" "qa" \
    "$BODY_HASH" "${_EV_COMMENT_URL:-}" 2>/dev/null || true
fi
```

## Re-run behavior

Re-running `/plan-qa` posts a new comment; prior comments are preserved. The **latest** comment carrying `<!-- gate:qa-plan:... -->` is the source of truth. `/qa` reads the latest `plan-hash` and compares against the current issue body hash — mismatch = stale plan → error.

## Break-point contract

The PREVIEW stage shows the reviewer-approved qa-plan in-session and waits for the user's confirmation before posting to GitHub. The user sees the plan content in the conversation first, then decides:

- **Approve** (default) → posts the comment with gate markers
- **Revise** → loops back to replanning with feedback (re-runs REVIEW on the new draft)
- **Abort** → exits cleanly with no GitHub side effects
- **`--approved` flag** → skips the AskUserQuestion; posts immediately after REVIEW passes

After the comment is posted, the user runs `/qa` (which detects the `gate:qa-plan` marker and skips its own PLAN stage) or re-runs `/plan-qa` after editing the issue.

## Gate marker

`<!-- gate:qa-plan:${TASK_ID} -->` — read by `/qa` PLAN stage (auto-skips PLAN if a matching marker is found; bypass entirely with `/qa --skip-plan` or via the automatic exemption in regression mode when a release tag is supplied).

## Notes

- Structural sanity checks here mirror the tester agent's Phase 1 checks (`agents/tester.md:54-63`). If the agent later finds the plan invalid anyway, per Decision 3 it ABORTs; re-run `/plan-qa` to regenerate.
- Re-validation by the tester agent is defense-in-depth, not duplication — the post-time check here is a fast local fail; the agent's check is a full structural audit.
