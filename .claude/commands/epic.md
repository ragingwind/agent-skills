---
description: Epic pipeline — sub-issue dispatch + QA + final PR
argument-hint: <epic-issue-number> [--concurrency N]
---

# /epic

Fully autonomous epic pipeline. Takes the epic issue number as the first positional argument (or resolves it from the existing `events.jsonl` init event on re-entry), dispatches sub-issues layer by layer via headless Claude instances, runs QA on the epic branch, and creates the final PR.

## Pipeline

```
SETUP → DISPATCH (layer by layer) → MERGE MONITOR → QA → FINALIZE
```

## Stages & Agent Mapping

| Stage | Agent | Purpose |
|-------|-------|---------|
| SETUP | orchestrator | Epic intake, DAG construction, epic branch creation |
| DISPATCH | `epic.ts` (background) | Spawn Claude instances per sub-issue, layer by layer |
| MERGE MONITOR | orchestrator (cron) | Poll until all sub-issue PRs merge to epic branch |
| QA | `qa` | Full QA on epic branch — regression, scenarios, evidence |
| FINALIZE | orchestrator | Final PR epic branch → main, close epic issue |

## SETUP (orchestrator inline)

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
# Epic issue number: first positional arg (e.g. /epic 123) takes priority;
# on re-entry (events.jsonl already exists) resolve from the init event.
_FIRST_ARG=$(echo "$ARGUMENTS" | awk '{print $1}')
if echo "$_FIRST_ARG" | grep -qE '^[0-9]+$'; then
  EPIC_NUM="$_FIRST_ARG"
else
  EPIC_NUM=""
  if . "$HOME/.claude/scripts/events.sh" 2>/dev/null; then
    _sd=$(events_state_dir 2>/dev/null) || _sd=""
    if [ -n "$_sd" ] && [ -f "$_sd/events.jsonl" ]; then
      EPIC_NUM=$(events_latest "$_sd" init 2>/dev/null | jq -r '.issue_num // empty' 2>/dev/null || echo "")
    fi
  fi
fi
[ -z "$EPIC_NUM" ] && { echo "ERROR: no epic issue number — pass as first arg (e.g. /epic 123)"; exit 1; }
EPIC_SLUG=$(gh issue view "$EPIC_NUM" --json title -q '.title' | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | cut -c1-40)
EPIC_BRANCH="epic/${EPIC_NUM}-${EPIC_SLUG}"
CONCURRENCY=$(echo "$ARGUMENTS" | sed -n 's/.*--concurrency[= ]\([0-9]*\).*/\1/p')
CONCURRENCY=${CONCURRENCY:-3}
REPO=$(git remote get-url origin | sed -e 's#^.*github\.com[:/]##' -e 's#\.git$##')
EPIC_DIR="/tmp/claude-epic-${EPIC_NUM}"
mkdir -p "$EPIC_DIR"
```

Steps:
1. Fetch sub-issues: `gh api repos/{owner}/{repo}/issues/{EPIC_NUM}/sub_issues`
2. For each sub-issue, extract existing plan from gate:dev-plan comment:
   ```bash
   gh api "repos/{owner}/{repo}/issues/{N}/comments" --jq '[.[] | select(.body | contains("gate:dev-plan"))] | last | .body'
   ```
3. Parse dependency relationships from each sub-issue body (`depends on #N`, `blocked by #N`)
4. Topological sort → assign layers
5. Detect cycles → STOP + report if found
6. Ensure epic branch exists (create from default branch if not):
   ```bash
   _BASE=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' | grep . || echo "main")
   git fetch origin "$_BASE"
   git checkout -b "$EPIC_BRANCH" "origin/$_BASE" 2>/dev/null || git checkout "$EPIC_BRANCH"
   git push -u origin "$EPIC_BRANCH"
   ```
6b. Phase 1 ghost recording (additive, best-effort, never blocks legacy):
   Records an `init` event to the plugin-scoped `events.jsonl` for the epic branch. A failure here never aborts the pipeline.
   ```bash
   TASK_ID="${EPIC_NUM}-epic"
   if . "$HOME/.claude/scripts/events.sh" 2>/dev/null; then
     STATE_DIR=$(events_state_dir 2>/dev/null) || STATE_DIR=""
     if [ -n "$STATE_DIR" ]; then
       mkdir -p "$STATE_DIR"
       if [ ! -s "$STATE_DIR/events.jsonl" ]; then
         events_emit_init "$STATE_DIR" "$TASK_ID" "$REPO" "$EPIC_NUM" \
           "$EPIC_BRANCH" "$_BASE" "$_BASE" "$REPO_ROOT" \
           2>/dev/null || true
       fi
       # Orchestrator writer token — required for stage.passed/failed emits.
       if [ -f "$STATE_DIR/.orch-writer-token" ]; then
         export ORCHESTRATOR_TOKEN=$(cat "$STATE_DIR/.orch-writer-token")
       fi
       echo "events.jsonl: $STATE_DIR/events.jsonl"
     fi
   fi
   ```
7. Post setup comment to epic issue with `<!-- gate:epic:setup:{EPIC_NUM} -->`:
   ```
   ## Epic Pipeline Started
   - Sub-issues: #{N1}, #{N2}, ...
   - Epic branch: {EPIC_BRANCH}
   - Layers: {count}
   - Concurrency: {N}
   ```

## DISPATCH

Run epic.ts in the background:

```bash
bun ~/.claude/scripts/epic.ts "$EPIC_NUM" --concurrency "$CONCURRENCY" --epic-dir "$EPIC_DIR"
```

After each layer completes, epic.ts posts a layer result comment to the epic issue with `<!-- gate:epic:layer:{layer}:{EPIC_NUM} -->`:
```
## Layer {N} Complete
| Issue | Title | Status | PR |
|-------|-------|--------|----|
| #42   | ...   | done   | #156 |
```

## MERGE MONITOR

Poll every 5 minutes (CronCreate) until all sub-issue PRs are merged to epic branch:

```bash
gh pr list -R "$REPO" --base "$EPIC_BRANCH" --state merged --json number -q '.[].number'
```

```
CronCreate(cron: "*/5 * * * *", prompt: "/epic merge-check", recurring: true)
```

When all expected PRs are merged, cancel the cron job and proceed to QA.

## QA

1. Create QA issue:
   ```bash
   gh issue create -R "$REPO" \
     --title "QA: #${EPIC_NUM} ${EPIC_TITLE}" \
     --body "Epic: #${EPIC_NUM}\nBranch: ${EPIC_BRANCH}\nSub-issues: ..."
   ```
2. Post to epic issue: "QA started — Issue #{qa_num} created"
3. Create QA branch: `qa/epic-${EPIC_NUM}-${EPIC_SLUG}` from epic branch
4. `EnterWorktree(qa/epic-${EPIC_NUM}-${EPIC_SLUG})`
5. `Skill("qa")` — posts progress to QA issue
6. Create QA PR: `qa/epic-${EPIC_NUM}-${EPIC_SLUG}` → `${EPIC_BRANCH}`
7. Collect full QA report body from the QA PR (most recent non-bot comment, or the QA skill's gate comment):
   ```bash
   QA_REPORT=$(gh pr view "$QA_PR_NUM" -R "$REPO" --comments \
     --jq '[.comments[] | select(.body | contains("gate:epic:qa"))] | last | .body' 2>/dev/null || echo "")
   # Fallback: QA issue comments
   if [ -z "$QA_REPORT" ]; then
     QA_REPORT=$(gh api "repos/$REPO/issues/$QA_ISSUE_NUM/comments" \
       --jq '[.[] | select(.body | contains("gate:epic:qa"))] | last | .body' 2>/dev/null || echo "")
   fi
   ```
8. Post the full QA report to the epic issue with `<!-- gate:epic:qa:{EPIC_NUM} -->`:
   ```bash
   gh issue comment "$EPIC_NUM" -R "$REPO" --body "$QA_REPORT"
   ```
   > **Why epic issue, not final PR:** The final PR does not exist yet at QA time.
   > FINALIZE reads this comment and re-posts it to the final PR (step 1b below).

## FINALIZE

1. Create final PR: `${EPIC_BRANCH}` → default branch (main/canary) as **draft**
1b. Re-post QA report to the final PR (so reviewers see evidence without leaving the PR):
   ```bash
   QA_COMMENT=$(gh api "repos/$REPO/issues/$EPIC_NUM/comments" \
     --jq '[.[] | select(.body | contains("<!-- gate:epic:qa:'"$EPIC_NUM"' -->'))] | last | .body' \
     2>/dev/null || echo "")
   if [ -n "$QA_COMMENT" ]; then
     gh pr comment "$FINAL_PR_NUM" -R "$REPO" --body "$QA_COMMENT"
   fi
   ```
2. Post to epic issue with `<!-- gate:epic:done:{EPIC_NUM} -->`:
   ```
   ## Epic Complete
   Final PR: #{pr_num}
   Sub-issues: {N} merged
   QA: PR #{qa_pr_num}
   ```

## Failure Handling

| Failure At | Recovery | Max Retries |
|-----------|----------|-------------|
| Sub-issue dispatch | epic.ts skips dependents, reports per-issue status | Per-issue: pipeline retries internally |
| Merge monitor timeout | After 2 hours with no new merges, STOP and report | — |
| QA | /qa QA stage Ralph loop (see `commands/qa.md` → "QA stage — Ralph invocation") | 5 (3 identical = STOP) |

## Sub-issue Branch Naming

Epic branch: `epic/{N}-{slug}` (e.g., `epic/100-auth-overhaul`)
Sub-issue branches: `feat/epic-{N}/{sub_N}-{sub_slug}` with `base_branch = epic/{N}-{slug}`

Example:
- Epic branch: `epic/100-auth-overhaul`
- Sub-issue branches: `feat/epic-100/42-add-oauth`, `feat/epic-100/43-update-middleware`

Using `feat/epic-{N}/` groups all sub-issues visually in git and avoids ref conflicts with the `epic/` parent branch.

## Output

- `$EPIC_DIR/<issue>.ndjson` — raw stream output per sub-issue
- `$EPIC_DIR/<issue>.json` — result summary per sub-issue
- `$EPIC_DIR/summary.json` — overall dispatch report
- Epic issue comments — layer completion, QA status, final result

## Prerequisite

Bun must be installed: https://bun.sh
