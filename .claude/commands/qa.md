---
description: QA pipeline — plan, full QA, finalize
argument-hint: <issue-number | commit-range | natural-language-hint> [v1.2.0 for regression] [--skip-plan] [--dry-run]
---

# /qa

QA pipeline for professional quality assurance. PLAN is an embedded break-point — if no `gate:qa-plan` marker exists on the issue, the pipeline generates one inline and pauses for user approval before the tester agent runs.

Runs after /dev for evidence collection, or independently for regression testing.

## Pipeline

```
SETUP → ENV-AUDIT → PLAN (skill + REVIEW Ralph + AskUserQuestion) → QA(tester agent) → gate(+upload) → FINALIZE
```

## Stages & Agent Mapping

| Stage | Agent | Model | Purpose |
|-------|-------|-------|---------|
| SETUP | orchestrator | — | Task file creation, issue intake, body hash |
| ENV-AUDIT | orchestrator | — | Verify the **production environment** declared in qa-plan is reachable. HARD STOP if not. See "Real-environment principle" below. |
| PLAN | orchestrator | — | `Skill("planning-features", args: "--mode qa")` THEN `reviewer` agent in qa-plan-review mode (Ralph loop, max 3 iter) THEN `AskUserQuestion` approval. Skipped if marker exists, `--skip-plan`, or regression mode |
| QA | `tester` | opus | Full QA — regression, scenarios, evidence, report. ALL evidence MUST be produced from production code path — see "Evidence requirement" below. |
| FINALIZE | orchestrator | — | Draft → Ready (`gh pr ready`), issue sync (inline `gh issue edit`), CI check |

## Planner ≠ Reviewer principle (MANDATORY)

The skill that **writes** the qa-plan is NEVER the agent that **approves** it. Approval requires an independent `reviewer` agent dispatch in qa-plan-review mode (see `agents/reviewer.md`). The orchestrator MUST NOT skip the REVIEW Ralph loop in the embedded PLAN stage.

> Same principle as `/plan-dev` (the standalone planning command). See `commands/plan-qa.md` → "Planner ≠ Reviewer principle" for the full contract. `/qa`'s embedded PLAN stage applies the same Ralph loop.

## Real-environment principle (MANDATORY)

**QA validates the application as the user uses it — not as the test harness mocks it.**

The qa-plan, the tester agent's execution, and the evidence collected MUST all reflect the real production environment. Specifically:

| Item | Mock OK? | Real OK? |
|------|----------|----------|
| The dev server (`apps/dol`) | ❌ no — must be the actual running process | ✅ |
| The MCP server | ❌ no — must be reachable on a real URL | ✅ |
| The user account (auth/session) | ❌ no — must be a real account in the test DB | ✅ |
| External services the feature depends on | ❌ no | ✅ |
| AI streaming endpoint (when feature does NOT depend on real AI behavior) | ✅ deterministic mock allowed | ✅ |

The reviewer agent rejects any qa-plan whose `Required state` describes a mock-only environment for the feature under test. The ENV-AUDIT stage refuses to enter PLAN/QA if the declared production environment is unreachable.

## Evidence requirement (MANDATORY)

Every scenario in the qa-plan MUST produce evidence captured FROM the production code path. The tester agent records, for each evidence file, a companion `<filename>.metadata.json`:

```json
{
  "spec_path": "tests/e2e/.../mcp-apps-s4-protocol-handshake.spec.ts",
  "scenario_id": "S4",
  "covers_capability": ["C1", "C4"],
  "covers_success_criteria": ["SC-1", "SC-3"],
  "mocked_production_routes": [],
  "production_routes_exercised": ["/api/mcp/resource", "/api/mcp/call"],
  "is_synthetic_fixture": false,
  "production_path_exercised": true,
  "real_environment_components": ["dol-dev-server", "real-mcp-server@localhost:9001", "test-user-session"]
}
```

`production_path_exercised: false` is rejected by the verify gate hook unless the qa-plan declared the scenario as `mock_only: true` AND a corresponding `BLOCKED` real-environment companion scenario exists.

The verify gate parity check (orchestrator before posting `gate:verify`):
```
COUNT_PRODUCTION_PATH = number of evidence with production_path_exercised: true
COUNT_HIGH_CRITICAL_CAPABILITIES = number of P1 capabilities in qa-plan §Capability Inventory

REQUIRED: COUNT_PRODUCTION_PATH >= COUNT_HIGH_CRITICAL_CAPABILITIES
```

Mismatch → BLOCKING; orchestrator refuses to post `gate:verify`.

## ENV-AUDIT (new stage — runs AFTER SETUP and BEFORE PLAN)

The orchestrator extracts the environment requirements declared in the dev-plan (`## Environment Requirements` section) and the qa-plan (when present, `## System Access` section). For each requirement, runs a reachability check.

```bash
# Example checks (orchestrator runs these inline)
case "$req_type" in
  service)
    curl -fsS --max-time 5 "$req_url" >/dev/null 2>&1 \
      || { echo "ENV-AUDIT FAIL: $req_url unreachable"; exit 1; } ;;
  binary)
    command -v "$req_binary" >/dev/null 2>&1 \
      || { echo "ENV-AUDIT FAIL: '$req_binary' not in PATH"; exit 1; } ;;
  account)
    # e.g., verify Test User exists in DB
    eval "$req_check_command" \
      || { echo "ENV-AUDIT FAIL: $req_id account check failed"; exit 1; } ;;
esac
```

**HARD STOP** if any check fails. Output includes the explicit setup command needed (e.g., `git clone https://github.com/.../ext-apps && cd examples/basic-server-react && pnpm dev`).

There is no `--skip-env-audit` flag. To proceed past an unreachable requirement, the user must either:
1. Provision the requirement, OR
2. Edit the qa-plan to declare the scenario as `mock_only: true` with a `BLOCKED` companion (which the reviewer agent then re-evaluates in the next REVIEW iteration).

## Flags

| Flag | Behavior |
|------|----------|
| `--skip-plan` | Skip PLAN stage entirely. |
| `--dry-run` | Run SETUP only, print verbose status (markers, hash match, mode), then exit before any stage executes. |
| `<release-tag>` (e.g., `v1.2.0`) | Regression mode. Auto-exempts PLAN requirement — release diff replaces the plan artifact. |

## Verify Commands Template

```markdown
## Verify Commands
- setup:          [ -n "$TASK_ID" ] && [ -d "$STATE_DIR" ]
- qa-plan:        [ -s $STATE_DIR/<name>-qa.md ] && grep -q '## Scenarios' $STATE_DIR/<name>-qa.md && grep -q 'Success conditions' $STATE_DIR/<name>-qa.md
- unit:           [ -s $STATE_DIR/<name>-unit.txt ] && grep -qiE "passed|[0-9]+ pass" $STATE_DIR/<name>-unit.txt
- evidence-mode:  screenshot   # screenshot (default) | video | none <reason>
                              # /qa: tester agent auto-overrides to video per agents/tester.md:99-103.
                              # Explicit screenshot override requires a written rationale in the QA report.
- evidence-flows: s1-<flow1>, s2-<flow2>   # canonical prefix — see rules/testing.md → File Naming Authority
```

## Ralph Integration

Ralph (`commands/ralph.md`) is the domain-agnostic retry-loop primitive. The QA stage invokes it with the parameters below.

### QA stage — Ralph invocation

```
executor   = tester (full QA pipeline — qa-plan validation, regression, scenarios, evidence)
verifier   = QA gate PASS — all scenarios covered
             AND evidence valid (.webm or .png per declared mode)
             AND scenario-evidence count parity
fixer      = builder (receives QA failure report from $STATE_DIR/<name>-qa-report.md)
terminator = max 5 iterations OR same-failure 3 times
```

See `commands/ralph.md` for loop semantics.

## Failure Handling

| Failure At | Recovery | Max Retries |
|-----------|----------|-------------|
| QA | QA stage Ralph loop (see "QA stage — Ralph invocation" above) | 5 (3 identical = early STOP) |
| Evidence | Re-dispatch tester(evidence mode), specify missing flows | 3 |
| 3 consecutive gate failures | HARD STOP → report to user | — |

## Anchor resolution

Same contract as `/plan-qa` — see `commands/plan-qa.md` → "Anchor resolution" for the full spec.

| Type | Pattern | Handling |
|------|---------|----------|
| Issue number | all-digits | `ISSUE=arg`; use existing issue |
| Commit / tag range | contains `..` | `COMMIT_RANGE=arg`; auto-create issue |
| Natural-language hint | anything else | **Orchestrator resolves BEFORE bash SETUP runs** |
| (absent) | — | HARD STOP — unless `events.jsonl` has a prior `init` event (re-entry) |

Orchestrator resolves natural-language hints via `git log/tag/describe`, displays the resolved range for transparency, and either confirms ambiguous hints via `AskUserQuestion` or aborts. The resolved `COMMIT_RANGE` (plus optional `ISSUE_TITLE`, `ISSUE_BODY`, `ISSUE_ORIGIN_HINT`) is passed as env vars to SETUP.

## SETUP

**Step 1 — initialize task context:**
```bash
# Compute task context — orchestrator runs this ONCE in SETUP
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
  echo "  /qa 123                   — QA against issue #123"
  echo "  /qa abc123..HEAD          — QA against commit range (auto-creates issue)"
  echo "  /qa \"last 10 commits\"     — natural-language hint (orchestrator resolves first)"
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

_Auto-created by /qa for ad-hoc QA. Close after session ends._
BODY_EOF
)
  fi
  case " $ARGUMENTS " in *" --dry-run "*) _EARLY_DRY_RUN=1 ;; *) _EARLY_DRY_RUN=0 ;; esac
  if [ "$_EARLY_DRY_RUN" = "1" ]; then
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
SLUG=$(git branch --show-current | sed 's|.*/||' | tr '/' '-')
TASK_ID="${ISSUE}-${SLUG}"
REPO=$(git remote get-url origin | sed -e 's#^.*github\.com[:/]##' -e 's#\.git$##')
```

> **Orchestrator passes `TASK_ID`, `STATE_DIR`, `REPO`, `ISSUE` explicitly in every agent prompt.** Agents do NOT compute these themselves — they use the values provided by the orchestrator.

`$STATE_DIR` is the per-branch artifact directory (alongside `events.jsonl`) where every stage writes its `*.log` files. There is no task file. Agents do NOT post gate comments directly — the orchestrator emits the `stage.passed` event after dispatch and posts the `<!-- gate:<stage>:${TASK_ID} -->` marker.

**Step 2 — verify context:** `echo "TASK_ID=$TASK_ID STATE_DIR=$STATE_DIR REPO=$REPO"`

**Step 2b — emit events.jsonl init event (source of truth for pipeline state):**

Records an `init` event to the plugin-scoped `events.jsonl`. Idempotent: if `events.jsonl` already has an init event, this step is a no-op. **Skipped under `--dry-run`** so dry-run is non-destructive.

```bash
# Detect --dry-run early (Step 3 parses it canonically; this guard is for state writes only).
case " $ARGUMENTS " in *" --dry-run "*) _EARLY_DRY_RUN=1 ;; *) _EARLY_DRY_RUN=0 ;; esac
if [ "$_EARLY_DRY_RUN" != "1" ] && [ ! -s "$STATE_DIR/events.jsonl" ]; then
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

**Step 3 — compute body hash + parse flags + detect regression mode:**
```bash
BODY_HASH=$(gh issue view "$ISSUE" --json body -q '.body' | shasum -a 256 | awk '{print $1}' | cut -c1-16)

SKIP_PLAN=0; DRY_RUN=0; REGRESSION_TAG=""
case " $ARGUMENTS " in *" --skip-plan "*) SKIP_PLAN=1 ;; esac
case " $ARGUMENTS " in *" --dry-run "*) DRY_RUN=1 ;; esac
# Regression mode: any token matching a semver-ish release tag (v1.2.3 or 1.2.3)
for TOKEN in $ARGUMENTS; do
  case "$TOKEN" in
    v[0-9]*.[0-9]*.[0-9]*|[0-9]*.[0-9]*.[0-9]*) REGRESSION_TAG="$TOKEN" ;;
  esac
done
echo "BODY_HASH=$BODY_HASH  SKIP_PLAN=$SKIP_PLAN  DRY_RUN=$DRY_RUN  REGRESSION_TAG=${REGRESSION_TAG:-<none>}"
```

**Step 4 — `--dry-run` verbose status dump (exits before PLAN stage):**

```bash
if [ "$DRY_RUN" = "1" ]; then
  echo
  echo "[dry-run] /qa status for issue #$ISSUE"
  echo "  TASK_ID       = $TASK_ID"
  echo "  STATE_DIR     = $STATE_DIR"
  echo "  BODY_HASH     = $BODY_HASH"
  echo "  branch        = $(git branch --show-current)"
  echo "  regression    = ${REGRESSION_TAG:-<standard mode>}"

  if [ -n "$REGRESSION_TAG" ]; then
    echo "  PLAN          = auto-exempt (regression mode uses release diff)"
  else
    PLAN_COMMENT=$(gh issue view "$ISSUE" --json comments -q \
      '.comments | reverse | map(select(.body | contains("<!-- gate:qa-plan:"))) | .[0].body' 2>/dev/null)
    if [ -z "$PLAN_COMMENT" ] || [ "$PLAN_COMMENT" = "null" ]; then
      echo "  gate:qa-plan  = MISSING  ← /plan-qa needed (or --skip-plan)"
    else
      SAVED_HASH=$(printf '%s' "$PLAN_COMMENT" | grep -oE '<!-- plan-hash:[a-f0-9]+ -->' | head -1 \
        | sed -E 's/.*plan-hash:([a-f0-9]+).*/\1/')
      if [ "$SAVED_HASH" = "$BODY_HASH" ]; then
        echo "  gate:qa-plan  = PRESENT  (hash match: $SAVED_HASH)"
      else
        echo "  gate:qa-plan  = STALE    (saved=$SAVED_HASH, current=$BODY_HASH) ← re-run /plan-qa"
      fi
    fi
  fi

  echo "  --skip-plan   = $([ "$SKIP_PLAN" = "1" ] && echo ON || echo off)"
  echo
  echo "[dry-run] exiting before PLAN stage"
  exit 0
fi
```

## PLAN Stage (embedded break-point)

Runs after SETUP, before QA. Orchestrator-driven, no subagent dispatch.

### Decision tree

```
1. Regression mode (release tag supplied)?  → SKIP PLAN (release diff replaces plan)
2. --skip-plan flag set?                     → SKIP PLAN, proceed to QA
3. gate:qa-plan marker on issue?
   ├─ yes, plan-hash == BODY_HASH            → SKIP PLAN, proceed to QA (already planned via /plan-qa)
   └─ yes, plan-hash != BODY_HASH            → HARD STOP: "plan is stale (issue body changed).
                                                Re-run /plan-qa or add --skip-plan."
4. no marker                                 → RUN inline PLAN (below)
```

### Inline PLAN flow (Planner ≠ Reviewer + Ralph + AskUserQuestion)

```
a. Skill("planning-features", args: "--mode qa")  # writes $STATE_DIR/${TASK_ID}-qa.md (DRAFT)

b. REVIEW Ralph loop (MANDATORY — same loop as /plan-qa REVIEW stage):
   for iter in 1..3:
       i.   Dispatch reviewer agent (mode: qa-plan-review)
            inputs:
              - $STATE_DIR/${TASK_ID}-qa.md  (the draft)
              - $STATE_DIR/${TASK_ID}-plan.md (if dev-plan exists)
              - git diff $BASE_BRANCH...HEAD --stat
              - iteration number
       ii.  Reviewer writes $STATE_DIR/${TASK_ID}-qa-review.md with verdict
       iii. If verdict APPROVED (0 CRITICAL / 0 HIGH) → break; proceed to (c).
       iv.  If verdict CHANGES_REQUIRED:
              - Append review findings to $STATE_DIR/${TASK_ID}-qa-feedback.log
              - rm $STATE_DIR/${TASK_ID}-qa-review.md
              - Re-invoke Skill("planning-features", args: "--mode qa --feedback $STATE_DIR/${TASK_ID}-qa-feedback.log")
              - The skill MUST address each numbered finding and re-emit the qa-plan
              - Continue loop (next iteration)
       v.   If iter == 3 and still CHANGES_REQUIRED → HARD STOP, exit /qa
       vi.  If same finding repeats 3x → HARD STOP, exit /qa

c. AskUserQuestion (final user gate AFTER reviewer APPROVED):
      1) Approve        → proceed to POST
      2) Revise         → user supplies freeform feedback,
                          orchestrator restarts loop (b) at iter 1 with combined feedback
      3) Abort          → exit /qa without posting marker

d. POST (Approve branch):
      gh issue comment "$ISSUE" --body "$(cat $PLAN_PATH)\n\n---\n<!-- gate:qa-plan:${TASK_ID} -->\n<!-- plan-hash:${BODY_HASH} -->"

e. Proceed to QA stage
```

### Why both reviewer AND AskUserQuestion?

- The **reviewer agent** applies the Planner ≠ Reviewer principle systematically — it audits the qa-plan against `agents/reviewer.md` → QAPlanReviewMode CRITICAL/HIGH gates (mock-only env, evidence schema, capability coverage, etc.). The orchestrator cannot self-approve a draft from the planner skill.
- The **AskUserQuestion** is a final user-judgment break-point AFTER the agent gate. The user may still want to revise scope or wording even when the reviewer says APPROVED.

The reviewer agent is the **structural** gate (mechanical, applies fixed rules). The user is the **judgment** gate (taste, scope, priorities).

### Staleness HARD STOP (decision 2)

If a prior `gate:qa-plan` marker exists but its `plan-hash` does not match the current `BODY_HASH`, `/qa` halts with an error directing the user to re-run `/plan-qa`. There is no `--force-stale` flag.

### tester agent Phase 1 invalid — ABORT (decision 3)

Even after PLAN marker is posted, the tester agent re-validates the plan in its Phase 1 (4 structural checks — see `agents/tester.md:54-63`). If validation fails, the tester agent **aborts** (does NOT regenerate the plan). The orchestrator deletes `$STATE_DIR/${TASK_ID}-qa.md` and reports to the user in the local log (no PR comment). The user re-runs `/plan-qa` after addressing the issue, then re-runs `/qa`.

### Ralph in PLAN

The REVIEW sub-stage IS a Ralph loop (executor=reviewer, verifier=verdict==APPROVED, fixer=skill re-invocation with feedback, terminator=max-3 OR same-findings-3x). The outer AskUserQuestion break-point is NOT a Ralph loop — user judgment is the retry mechanism for that layer.

## QA Stage

**CRITICAL: MUST use `subagent_type: "tester"` — NEVER substitute with `builder` or any other agent type.**
The `tester` agent owns QA-PLAN, REGRESSION, SCENARIOS, EVIDENCE, and REPORT phases. Builder (Verify mode) only runs TIA on diff-affected specs; substituting builder breaks the entire QA pipeline.

Dispatch tester agent (standard or regression mode).
- Standard: prompt without release tag → `$BASE_BRANCH...HEAD` diff
- Regression: prompt with release tag (e.g., `v1.2.0`) → `git diff v1.2.0...HEAD`

tester agent runs internal 6-phase pipeline:
ENV PRE-FLIGHT → QA-PLAN (confirm) → REGRESSION (TIA-gap) → SCENARIOS → EVIDENCE → REPORT

Gate: tester agent produces evidence files in `$STATE_DIR/`. The orchestrator uploads evidence and posts the gate marker.
Note: gate rejects `.gif` files. In screenshot mode, each flow must have ≥1 `.png`. In video mode, each flow must have a `.webm` ≥ 50KB.

### Evidence Upload (by orchestrator, after tester agent completes)

After tester agent reports completion, orchestrator uploads evidence and posts gate marker:

1. Read `$STATE_DIR/<task-name>-qa-report.md` for scenario-evidence mapping.
2. **Verify scenario-evidence count parity** (BLOCKING) — refuse to upload if the qa-plan declares N scenarios but `$STATE_DIR/evidence/` does not contain exactly N evidence files of the declared mode. The mode is inferred from the `Expected evidence` filename extensions (`.webm` → video, `.png` → screenshot):
   ```bash
   QA_PLAN="$STATE_DIR/<task-name>-qa.md"
   SCENARIO_COUNT=$(grep -cE '^### S[0-9]+:' "$QA_PLAN")
   EXPECTED_EVIDENCE=$(grep -cE '^\*\*Expected evidence\*\*:' "$QA_PLAN")

   # Extract every backtick-enclosed basename from Expected evidence lines.
   # awk anchor + grep -oE handles multiple backticks per line (e.g. "a.webm and b.webm").
   DECLARED_FILES=$(awk '/^\*\*Expected evidence\*\*:/' "$QA_PLAN" | grep -oE '`[^`]+`' | tr -d '`')

   if echo "$DECLARED_FILES" | grep -qE '\.webm$'; then
     MODE=video
     ACTUAL_EVIDENCE=$(find "$STATE_DIR/evidence" -maxdepth 1 -name '*.webm' -size +50k 2>/dev/null | wc -l | tr -d ' ')
   elif echo "$DECLARED_FILES" | grep -qE '\.png$'; then
     MODE=screenshot
     ACTUAL_EVIDENCE=$(find "$STATE_DIR/evidence" -maxdepth 1 -name '*.png' 2>/dev/null | wc -l | tr -d ' ')
   else
     echo "ERROR: qa-plan Expected evidence declares no .webm or .png files" >&2
     exit 1
   fi

   if [ "$SCENARIO_COUNT" -ne "$ACTUAL_EVIDENCE" ] || [ "$SCENARIO_COUNT" -ne "$EXPECTED_EVIDENCE" ]; then
     echo "ERROR: scenario/evidence mismatch (mode=$MODE) — scenarios=$SCENARIO_COUNT, declared=$EXPECTED_EVIDENCE, files=$ACTUAL_EVIDENCE" >&2
     exit 1
   fi

   # Cross-check every declared filename exists on disk
   echo "$DECLARED_FILES" | while read -r BASENAME; do
     [ -z "$BASENAME" ] && continue
     case "$MODE" in
       screenshot) [ -f "$STATE_DIR/evidence/$BASENAME" ] || { echo "ERROR: declared evidence missing: evidence/$BASENAME" >&2; exit 1; } ;;
       video)      [ -f "$STATE_DIR/evidence/$BASENAME" ] || { echo "ERROR: declared evidence missing: evidence/$BASENAME" >&2; exit 1; } ;;
     esac
   done
   ```
3. Call `Skill("upload-evidence", args: "--pipeline qa --mode <$MODE> --section 'S<N>: <title>' --description '<purpose>'")` per scenario.
4. Post `<!-- gate:verify:${TASK_ID} -->` marker to PR with scenario-evidence mapping table. The comment body MUST begin with `writer: tester` on its own line so `pre-bash-pr-gate.sh` can route evidence validation to the scenario (.webm / screenshot) path.

## FINALIZE: Pipeline Completion

After QA gate passes, the orchestrator runs these steps inline (no separate agent):

```bash
# 1. Convert Draft PR to Ready
PR_NUM=$(gh pr view --json number -q '.number')
gh pr ready "$PR_NUM"

# 2. Sync issue checklist from posted gate markers.
#    The orchestrator queries gate markers on the PR, then toggles the matching
#    `- [ ]` items in $ISSUE_BODY to `- [x]` before writing back. Toggle mapping
#    is interpreted by the orchestrator at runtime (gate name → checklist item)
#    because gate names and checklist phrasing are project-specific.
GATE_NAMES=$(gh api "repos/$REPO/issues/$PR_NUM/comments" --jq '.[].body' \
  | grep -oE '<!-- gate:[a-z-]+:[^ ]+ -->' \
  | sed -E 's|<!-- gate:([a-z-]+):.*|\1|' | sort -u)
ISSUE_BODY=$(gh issue view "$ISSUE" --json body -q '.body')
# Orchestrator: apply per-gate toggles to $ISSUE_BODY here (sed/awk), then:
gh issue edit "$ISSUE" --body "$ISSUE_BODY"
```

> Local gates (QA/VERIFY via `events.jsonl stage.passed`) are the source of truth. GitHub-side CI status is a reviewer concern, not a pipeline gate.

## Gate Enforcement Rules

Same as `/dev` — see `commands/dev.md` → "Gate Check Protocol" for the canonical event
emission + GitHub comment posting contract. In `/qa` the tester produces evidence but
does NOT post markers; the orchestrator emits `stage.started(tester, verify)` +
`stage.passed(tester, verify, writer=tester, evidence=[...])` to `events.jsonl` AND
posts the `<!-- gate:verify:${TASK_ID} -->` comment with `writer: tester` on the
first line of the body (the comment is a one-way projection for human readers).
`pre-bash-pr-gate.sh` verifies the events source before `gh pr create`.

### Phase 6b — Evidence list for the /qa verify event

Before emitting `stage.passed(verify)` the orchestrator migrates unhashed
evidence under `$STATE_DIR/evidence/` to the `<logical>.<hash8>.<ext>` form
and collects the resulting filenames into the event's `evidence` array:

```bash
. "${CLAUDE_PLUGIN_ROOT}/scripts/store_evidence.sh" 2>/dev/null || true
store_evidence_migrate "$STATE_DIR" 2>/dev/null || true

# QA scenario evidence uses the `s<N>-...` logical-name convention (video
# `.webm` or screenshot `.png`; see rules/testing.md#file-naming-authority).
QA_EV=$(store_evidence_list_json "$STATE_DIR" 's*')

# Pre-emit parity check (orchestrator-side guard, symmetric with /dev):
# refuse to emit stage.passed(verify) when plan.md's evidence-flows declares
# scenarios that have no matching file under $STATE_DIR/evidence/. Without
# this guard the orchestrator can ship E2E evidence claims that the PR gate
# accepts at hash level but that don't satisfy the plan's contract.
if command -v check_evidence_parity >/dev/null 2>&1; then
  if ! _PARITY_ERR=$(check_evidence_parity "$STATE_DIR" 2>&1 1>/dev/null); then
    echo "ERROR: refusing to emit stage.passed(verify) — declared evidence-flows missing files:" >&2
    printf '%s\n' "$_PARITY_ERR" >&2
    echo "Resolve by capturing the missing scenarios under \$STATE_DIR/evidence/, OR amend evidence-flows in \$STATE_DIR/plan.md to match what was actually produced." >&2
    exit 1
  fi
  if ! _CUTOVER_ERR=$(check_cutover_consistency "$STATE_DIR" 2>&1 1>/dev/null); then
    echo "ERROR: refusing to emit stage.passed(verify) — plan.md contradiction:" >&2
    printf '%s\n' "$_CUTOVER_ERR" >&2
    exit 1
  fi
fi

events_emit_stage_passed "$STATE_DIR" "$TASK_ID" tester verify <ITER> "$DH" \
  "<SUMMARY>" tester "$QA_EV" 2>/dev/null || true

# Phase 3 projector — mirror the just-emitted stage.passed(verify) to GitHub.
# Idempotent; on failure, fall back to manual gh pr comment with the gate marker.
bash "${CLAUDE_PLUGIN_ROOT}/scripts/project_events.sh" post "$STATE_DIR" \
  2>&1 | sed 's/^/projector: /' || true
```

The hook (`pre-bash-pr-gate.sh`) re-hashes each filename in the `evidence`
array against its embedded `hash8` suffix and blocks `gh pr create` on
mismatch. It also re-runs `check_evidence_parity` and
`check_cutover_consistency` against `plan.md` so the contract is enforced
even when the orchestrator-side guard is bypassed (e.g. legacy emitters).

Stage names: `setup` | `qa-plan` | `qa` | `finalize`

The `qa-plan` gate is informational (break-point artifact); it is NOT enforced by `pre-bash-pr-gate.sh` — the pipeline's own PLAN stage check is the enforcement point.

## Context Resume Protocol

Query GitHub for posted gate markers: `gh pr view $PR --json comments -q '.comments[].body' | grep -oE '<!-- gate:[a-z-]+:[^ ]+ -->'` returns the stages already completed. Re-run the inline task-context snippet (see SETUP Step 1) to restore `TASK_ID` / `STATE_DIR` / `REPO`.
