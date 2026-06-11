---
description: Development pipeline — plan, build, review, verify, evidence, finalize
argument-hint: <issue-number> [task description] [--mode=standard|ultra|eco] [--skip-plan] [--dry-run]
---

# /dev

Development pipeline with verification gates at each stage. PLAN is an embedded break-point — if no `gate:dev-plan` marker exists on the issue, the pipeline generates one inline and pauses for user approval before BUILD starts.

## Pipeline

```
SETUP → PLAN (skill + AskUserQuestion) → BUILD → gate(+upload) → REVIEW → gate → VERIFY(builder verify mode) → gate(+upload) → FINALIZE
```

## Stages & Agent Mapping

| Stage | Agent | Model | Purpose |
|-------|-------|-------|---------|
| SETUP | orchestrator | — | Issue intake, task file creation (direct bash) |
| PLAN | orchestrator | — | `Skill("planning-features", args: "--mode dev")` + `AskUserQuestion` approval (skipped if marker exists or `--skip-plan`) |
| BUILD | `builder` (Build mode) | opus | Implementation + unit tests + integration tests + related E2E + screenshot |
| REVIEW | `reviewer` | opus | Code audit — builder output, read-only |
| VERIFY | `builder` (Verify mode) | opus | TIA on affected specs + per-spec screenshot evidence |
| FINALIZE | orchestrator | — | Re-compose `$STATE_DIR/pr-body.md` with review + TIA evidence, `gh pr edit --body-file`, route image evidence, then issue-checklist sync (PR stays draft — user promotes manually) |

## Verify Commands Template

Each task defines verification commands in the task file. Written during SETUP, executed during gate checks.

```markdown
## Verify Commands
- setup:        [ -n "$TASK_ID" ] && [ -d "$STATE_DIR" ]
- build:        <from project CLAUDE.md "## Verify Commands" → build>
- build-unit:   [ -s $STATE_DIR/<name>-build-unit.log ] && grep -qiE "passed|[0-9]+ pass" $STATE_DIR/<name>-build-unit.log
```

> `build:` is project-specific — orchestrator reads project CLAUDE.md's `## Verify Commands` during SETUP and substitutes the declared command here. See `rules/testing.md` → Verify Commands for the convention and lockfile fallback.

### Evidence Upload (per-stage, inline by orchestrator)

Each stage uploads its own evidence immediately after passing its gate. **The order is enforced** by `events_emit_stage_passed` (see Hard Gate below):

- **BUILD gate passes** → orchestrator calls `Skill("upload-evidence", args: "--pr <N> --stage build --iter <I> --section '<title>' --description '<context>'")` to upload browser-verify screenshots, then emits `stage.passed(build)` event, then posts `gate:build` PR comment.
- **VERIFY gate passes** → orchestrator calls `Skill("upload-evidence", args: "--pr <N> --stage verify --iter <I> --section '<title>' --description '<context>'")` to upload TIA screenshots, then emits `stage.passed(verify, writer=builder)` event, then posts `gate:verify` PR comment.
- For non-UI changes (no `.tsx/.jsx/.css/.svg` in diff) → evidence upload is skipped, evidence array is empty, and the hard gate is a no-op.

### Hard Gate — evidence.uploaded must precede stage.passed

`events_emit_stage_passed` REFUSES to emit when the `evidence` array is non-empty AND no matching `evidence.uploaded` event exists for the same stage+iteration. The upload-evidence skill emits `evidence.uploaded` automatically after a successful upload (after API verification, before HEAD check), so callers that follow the documented order pass through transparently. Callers that skip the upload get a clear error pointing them to run upload-evidence first.

Pass `--stage <build|verify>` and `--iter <N>` to upload-evidence so the emitted event matches the impending `stage.passed`. Omitting `--stage` is allowed (legacy callers) but then the orchestrator cannot rely on the hard gate — those callers must pass `EVENTS_ALLOW_UNUPLOADED_EVIDENCE=1` or call `events_emit_evidence_uploaded` manually after the upload.

Emergency bypass: `EVENTS_ALLOW_UNUPLOADED_EVIDENCE=1 events_emit_stage_passed ...` — use only when upload-evidence itself is broken or the assets are in a known good state but the event log was reset. Never bypass to "save time" — the bypass leaves the gate trail incomplete and downstream review will catch it.

### Private/internal repos

For private or internal repos, the anonymous HEAD reachability check on GitHub Release URLs always 404s (assets are gated behind auth). upload-evidence auto-detects this via `gh repo view --json visibility` and skips the HEAD check. Override with `--require-head-check` if needed.

## Modes

| Mode | Flag | Behavior |
|------|------|----------|
| Standard | (default) | Fully autonomous pipeline with TDD |
| Ultra | `--mode=ultra` | Maximum parallelism in build and verify stages |
| Eco | `--mode=eco` | Token-efficient: compressed outputs, minimal verbosity |

## Flags

| Flag | Behavior |
|------|----------|
| `--skip-plan` | Skip PLAN stage entirely. No reason required. Does not suppress staleness checking — simply bypasses plan requirement. |
| `--dry-run` | Run SETUP only, print verbose status (TASK_ID, markers present/missing, hash match, worktree state), then exit before any stage executes. Use to diagnose gate failures before committing to a full run. |
## Ralph Integration

Ralph (`commands/ralph.md`) is the domain-agnostic retry-loop primitive. Every stage below that needs retry-on-failure behavior invokes the Ralph loop with its own injected parameters. Ralph itself knows nothing about agents, gates, or domains — this section declares the four parameters each stage injects.

### BUILD stage — Ralph invocation

```
executor   = builder (Build mode)
verifier   = $STATE_DIR/plan.md "build:" command (project-declared; see rules/testing.md → Verify Commands)
             AND unit/integration tests pass (grep -qiE "passed|[0-9]+ pass" "$STATE_DIR/build-unit.log")
             AND browser verification succeeds (UI changes only — screenshot evidence in $STATE_DIR/evidence/)
fixer      = builder (consumes failure output from verifier)
terminator = same-failure 3 OR consecutive 3 (no fixed max — build can take many iterations)
```

Orchestrator MUST append diagnostic analysis to `$STATE_DIR/build-ralph.log` before each fixer re-dispatch (failure summary + root cause + intended fix).

See `commands/ralph.md` for loop semantics.

**BUILD stage evidence (MANDATORY for UI changes):**
After agent-browser verification, builder MUST persist evidence:
1. Save screenshots to `$STATE_DIR/evidence/browser-verify-<phase>-step<NN>-<desc>.png`
2. Write to `$STATE_DIR/build.log`: URL tested, screenshots taken (file paths), what was verified (before/after states), pass/fail for each verification step

### POST-BUILD: Create Draft PR (before gate:build comment)

After the BUILD Ralph loop exits with PASS and before posting the `gate:build` comment, the orchestrator:
1. Composes `$STATE_DIR/pr-body.md` from the approved dev-plan (the `gate:dev-plan` issue comment) plus the BUILD stage outputs (file change summary, test results). One line of "Closes #N" is **never** acceptable as a PR body for a `/dev` pipeline.
2. Pushes the branch.
3. Creates a draft PR with `--body-file "$STATE_DIR/pr-body.md"`.

**MANDATORY PR body sections** (compose these from dev-plan + build artifacts; do NOT delegate to the user to fill in afterward):
- `Closes #<issue>.`
- `## Summary` — paragraph(s) extracted from the dev-plan's Summary / Problem / Approach sections, paraphrased for PR audience (what changed and why)
- `## Root cause` — for bug fixes, the cause analysis from the issue body / dev-plan
- `## Fix` — before/after snippet OR file-level change summary
- `## Changes` — table: `File | Change` listing every modified or added file in the diff (from `git diff --stat canary...HEAD`)
- `## Test plan` — checklist with per-test outcome (from `$STATE_DIR/build-unit.log` etc.); unticked items are post-merge tasks (manual verification, canary deploy validation)
- Footer line: `🤖 Implemented via \`/dev <issue>\` pipeline.`

**Composition script** (orchestrator runs inline; substitute literal values, do not leave placeholders):

```bash
# Locate the approved dev-plan body (gate:dev-plan marker on the issue)
PLAN_BODY=$(gh api "repos/$REPO/issues/$ISSUE/comments" --jq \
  '.[] | select(.body | contains("<!-- gate:dev-plan:")) | .body' | tail -1)

# Diff stat → Changes table source
DIFF_STAT=$(git diff --stat canary...HEAD 2>/dev/null | head -20)

# Compose pr-body.md (orchestrator: replace section bodies with extracted/condensed text from PLAN_BODY)
cat > "$STATE_DIR/pr-body.md" <<EOF
Closes #${ISSUE}.

## Summary

<paragraph(s) extracted/paraphrased from PLAN_BODY's Summary or Problem section>

## Root cause

<for bug fixes: cause from issue body or dev-plan; omit section for features>

## Fix

<before/after snippet OR file-level change list>

## Changes

| File | Change |
|---|---|
<one row per file in DIFF_STAT, with a one-line description>

## Test plan

- [x] <test command from \$STATE_DIR/plan.md "build:"> — <pass count from \$STATE_DIR/*-build-unit.log>
- [x] \`pnpm --filter dol check\` — <warning/error count from \$STATE_DIR/*-build-check.log>
- [ ] <post-merge manual verification, if applicable>

🤖 Implemented via \`/dev ${ISSUE}\` pipeline.
EOF

# Push branch (idempotent)
git push -u origin "$(git branch --show-current)" 2>/dev/null || true

# Create draft PR with composed body
_PR_EXISTS=$(gh pr view --json number -q '.number' 2>/dev/null || echo "")
if [ -z "$_PR_EXISTS" ]; then
  _ISSUE_TITLE=$(gh issue view "$ISSUE" --json title -q '.title')
  _EV_BASE_PR="${BASE_BRANCH:-$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' | grep . || echo main)}"
  gh pr create --draft \
    --title "$_ISSUE_TITLE" \
    --body-file "$STATE_DIR/pr-body.md" \
    --base "$_EV_BASE_PR"
fi
PR_NUM=$(gh pr view --json number -q '.number')
echo "Draft PR: #$PR_NUM (body composed from dev-plan + build artifacts)"
```

> A `/dev`-generated PR body MUST be substantive. If the orchestrator cannot extract meaningful content from the dev-plan (e.g., `gate:dev-plan` skipped), it must HALT and demand re-running `/plan-dev`. A one-line `Closes #N` body is a pipeline failure, not an acceptable default.

> From this point on, all gate comments (gate:build, gate:review, gate:verify) are posted to the PR via `gh pr comment "$PR_NUM"`. Plan-stage comments (`gate:dev-plan`) go to the issue — they precede the PR.

### REVIEW stage — Ralph invocation (on CRITICAL/HIGH findings)

```
executor   = reviewer (full qualitative audit of the entire diff)
verifier   = verdict == APPROVED AND 0 CRITICAL AND 0 HIGH findings
fixer      = builder (receives extracted findings from $STATE_DIR/<name>-review.md)
terminator = max 3 cycles OR same-findings 3 times
```

Note: "re-review after fix" happens naturally as the next iteration's executor call — not as part of fixer. Each iteration runs a full qualitative re-review of the whole diff (not just the changed lines).

Orchestrator MUST NEVER fix code inline — always dispatch builder as the fixer.

See `commands/ralph.md` for loop semantics.

**REVIEW-FIX loop (step-by-step operational detail):**
1. Review gate marker missing or not APPROVED → FAIL with action items in detail
2. Orchestrator reads `$STATE_DIR/<name>-review.md`, extracts 🔴 CRITICAL and 🟠 HIGH findings
3. Orchestrator dispatches `builder` with: finding list, file:line refs, suggested fixes
4. Builder fixes code, runs the project-declared `build:` command (`$STATE_DIR/plan.md` → `Verify Commands` → `build:`)
5. Orchestrator removes old review log: `rm $STATE_DIR/<name>-review.md`
   > Note: The previous GitHub review comment is NOT deleted (gh CLI does not support comment deletion). The new review comment supersedes it chronologically; the gate hook reads the latest APPROVED marker.
6. Orchestrator dispatches `reviewer` for fresh full re-review (posts new `<!-- gate:review:${TASK_ID} -->` comment)
7. Check re-posted review marker — if body still lacks `APPROVED`, repeat from step 2; if PASS, proceed to TEST

### POST-REVIEW: Auto-post deferred inline comments

After the REVIEW Ralph loop exits with APPROVED and BEFORE proceeding to VERIFY, the orchestrator posts the line-level review comments that the reviewer agent recorded in its audit report's `## Deferred Inline Comments` section. The reviewer is instructed (`agents/reviewer.md` → `inline-comments` phase) to record but NOT post; this step closes the loop so the comments actually appear on the PR.

```bash
# Locate the latest review report (Ralph may have iterated, deleting older ones)
REVIEW_REPORT=$(find "$STATE_DIR" -maxdepth 1 -name "*-review*.md" -print0 \
  | xargs -0 ls -t 2>/dev/null | head -1)
if [ -n "$REVIEW_REPORT" ] && [ -n "${PR_NUM:-}" ]; then
  COMMIT_SHA=$(git rev-parse HEAD)
  bash "${CLAUDE_PLUGIN_ROOT}/scripts/post-deferred-inline.sh" \
    "$REVIEW_REPORT" "$PR_NUM" "$REPO" "$COMMIT_SHA" \
    || echo "post-deferred-inline: non-fatal — see stderr" >&2
fi
```

Silent no-op when:
- The report has no `## Deferred Inline Comments` section (reviewer judged 0 inline comments needed)
- The section is present but contains 0 data rows
- The helper script is missing (legacy environments)

Failure to post inline comments does NOT halt the pipeline (best-effort).

### VERIFY stage — Ralph invocation

```
executor   = builder (Verify mode — TIA on affected specs only)
verifier   = all TIA specs pass
             AND $STATE_DIR/<name>-tia.md written
             AND $STATE_DIR/evidence/tia-*.png written (Playwright E2E specs only — vitest unit specs do NOT require PNG; tia.md is their evidence)
fixer      = builder (Build mode modifies affected code)
terminator = max 5 iterations OR same-failure 3 times
```

Gate-check runs only when the Ralph loop exits with verifier PASS (not on HARD STOP).

See `commands/ralph.md` for loop semantics.

### VERIFY stage evidence upload (by orchestrator, after builder Verify mode passes)

After builder (Verify mode) reports completion, orchestrator verifies TIA count parity and uploads:

1. Read `$STATE_DIR/<name>-tia.md` for per-spec assertion tables.
2. **Verify TIA count parity** (BLOCKING for E2E specs; skip for vitest-only TIA) — PNG screenshots are required ONLY for Playwright E2E specs. For vitest unit tests, `tia.md` is the sole evidence and the parity check MUST be skipped (capturing terminal output as PNG is cargo-cult behavior with no informational value). Refuse to upload if the TIA report declares N E2E screenshots but `$STATE_DIR/evidence/` does not contain exactly N matching files:
   ```bash
   TIA_REPORT=$(find "$STATE_DIR" -maxdepth 1 -name '*-tia.md' | head -1)
   [ -s "$TIA_REPORT" ] || { echo "ERROR: no TIA report in $STATE_DIR" >&2; exit 1; }
   # Count screenshot rows — only present when E2E specs were in scope
   DECLARED=$(grep -cE '^\| tia-[^ |]+\.png \|' "$TIA_REPORT" || true)
   if [ "${DECLARED:-0}" -gt 0 ]; then
     ACTUAL=$(find "$STATE_DIR/evidence" -maxdepth 1 -name 'tia-*.png' 2>/dev/null | wc -l | tr -d ' ')
     if [ "$DECLARED" -ne "$ACTUAL" ]; then
       echo "ERROR: TIA E2E screenshot mismatch — declared=$DECLARED, found=$ACTUAL" >&2
       exit 1
     fi
     # Cross-check every declared filename exists on disk
     grep -oE '^\| tia-[^ |]+\.png' "$TIA_REPORT" | sed 's/^| //' | while read -r BASENAME; do
       [ -f "$STATE_DIR/evidence/$BASENAME" ] || { echo "ERROR: declared TIA screenshot missing: $BASENAME" >&2; exit 1; }
     done
   fi
   # DECLARED=0 → vitest-only TIA. tia.md is the evidence. No PNG check.
   ```
3. Call `Skill("upload-evidence", args: "--pipeline dev --mode screenshot --section 'TIA — <spec>' --description '<purpose>'")`.
4. Post `<!-- gate:verify:${TASK_ID} -->` marker to PR. The comment body MUST begin with `writer: builder` on its own line so `pre-bash-pr-gate.sh` can route evidence validation to the TIA path.

## FINALIZE: Pipeline Completion

After VERIFY gate passes, the orchestrator runs these steps inline (no separate agent):

```bash
PR_NUM=$(gh pr view --json number -q '.number')

# 0. Re-compose $STATE_DIR/pr-body.md with FINAL evidence and update the PR body.
#    POST-BUILD wrote an initial body; FINALIZE augments it with review verdict,
#    TIA outcome, and any evidence collected after BUILD. The final PR body MUST
#    include an Evidence section with collapsible <details> blocks for:
#      - Targeted vitest output (truncated)
#      - TIA report excerpt (per-spec assertion table)
#      - Reviewer audit verdict + non-blocking findings list
#      - Image-evidence file names + GitHub Release URLs (when evidence-mode != none)
#    Orchestrator: edit $STATE_DIR/pr-body.md inline (do not regenerate from scratch
#    — preserve sections written at POST-BUILD), then push:
gh pr edit "$PR_NUM" --body-file "$STATE_DIR/pr-body.md"

# 0a. Image evidence routing (MANDATORY when evidence files exist on disk):
#     If $STATE_DIR/evidence/*.png or *.jpg exist AND the PR body references
#     image filenames, the orchestrator must ensure the images are reachable
#     from the PR. Two paths:
#       (i)  PR comment via web UI drag-drop (manual; orchestrator HALTS and
#            posts a user-handoff comment instructing the user to drop images
#            into a specific PR comment placeholder).
#       (ii) `gh release upload <evidence-release-tag> <files>` against a
#            project-declared evidence Release, then markdown image links in
#            the PR body pointing to the Release asset URLs.
#     The project's CLAUDE.md selects which path. Default is (ii) when an
#     evidence Release is declared, else (i). Never silently skip — always
#     either upload or HALT and request manual handoff.

# NOTE: Do NOT run `gh pr ready` — PR stays draft. User promotes draft → ready manually.

# 1. Sync issue checklist from posted gate markers.
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

# 3. Archive cross-session task (if registered)
# [ archive task inline if cross-session task exists ]
```

> Local gates (BUILD/REVIEW/VERIFY via `events.jsonl stage.passed`) are the source of truth. GitHub-side CI status is a reviewer concern, not a pipeline gate — anyone reviewing the PR can consult `gh pr checks` if external CI is configured.

## Failure Handling

| Failure At | Recovery | Max Retries |
|-----------|----------|-------------|
| Build | BUILD stage Ralph loop (see "BUILD stage — Ralph invocation" above) | No fixed max (3 identical OR 3 consecutive = STOP) |
| Review (CRITICAL/HIGH) | REVIEW stage Ralph loop (see "REVIEW stage — Ralph invocation" above) | 3 full cycles (3 identical findings = STOP) |
| Verify | VERIFY stage Ralph loop (see "VERIFY stage — Ralph invocation" above) | 5 max (3 identical = STOP) |
| 3 consecutive gate failures | HARD STOP → report to user | — |

## Output

Pipeline completion report:
- Each stage: status + key output
- Final result: SUCCESS or STOPPED (at which stage, why)

## SETUP: Task Context Initialization (CRITICAL)

There is no task file — stage logs live in `$STATE_DIR` (`$HOME/.local/state/agent-skills/<hostname>/<project-slug>/<branch-slug>/`, alongside `events.jsonl`) and each stage posts its own gate comment to GitHub with a `<!-- gate:<stage>:${TASK_ID} -->` marker.

**Step 1 — initialize task context:**
```bash
# Compute task context — orchestrator runs this ONCE in SETUP
REPO_ROOT=$(git rev-parse --show-toplevel)
# STATE_DIR is the single per-branch artifact + events.jsonl location.
. "${CLAUDE_PLUGIN_ROOT}/scripts/events.sh" || { echo "ERROR: scripts/events.sh missing"; exit 1; }
STATE_DIR=$(events_state_dir) || { echo "ERROR: cannot resolve state dir (not in a git worktree?)"; exit 1; }
mkdir -p "$STATE_DIR"

# Issue number: first positional arg (e.g. /dev 123 ...) takes priority;
# on re-entry (events.jsonl already exists) resolve from the init event.
_FIRST_ARG=$(echo "$ARGUMENTS" | awk '{print $1}')
if echo "$_FIRST_ARG" | grep -qE '^[0-9]+$'; then
  ISSUE="$_FIRST_ARG"
elif [ -f "$STATE_DIR/events.jsonl" ]; then
  ISSUE=$(events_latest "$STATE_DIR" init 2>/dev/null | jq -r '.issue_num // empty' 2>/dev/null || echo "")
fi
[ -z "${ISSUE:-}" ] && { echo "ERROR: no issue number — pass as first arg (e.g. /dev 123)"; exit 1; }
SLUG=$(git branch --show-current | sed 's|.*/||' | tr '/' '-')
TASK_ID="${ISSUE}-${SLUG}"
REPO=$(git remote get-url origin | sed -e 's#^.*github\.com[:/]##' -e 's#\.git$##')
```

**Step 1c — worktree pre-flight (MANDATORY):**

Verify the worktree has the project scaffold. If running inside a git worktree that was created before the base branch's scaffolding commit (e.g., only contains README.md), rebase onto the base branch before proceeding. This prevents the orchestrator from routing the builder to the main repo root as a workaround.

```bash
_BASE=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo main)

# Detect stale worktree: missing package.json or tsconfig.json means the
# worktree was cut before scaffolding merged. Rebase onto base branch.
if [ ! -f "$REPO_ROOT/package.json" ] && [ ! -f "$REPO_ROOT/tsconfig.json" ]; then
  echo "PREFLIGHT: worktree missing scaffold files — rebasing onto origin/$_BASE"
  git fetch origin "$_BASE"
  git rebase "origin/$_BASE" || {
    echo "ERROR: rebase failed. Resolve conflicts, then re-run /dev."
    exit 1
  }
  echo "PREFLIGHT: rebase complete. Worktree is now up-to-date with origin/$_BASE"
else
  echo "PREFLIGHT: worktree OK (scaffold files present)"
fi

# HARD RULE: builder MUST always work inside REPO_ROOT (the worktree).
# NEVER pass the main repo root to the builder as a workaround for a stale worktree.
# If the worktree is stale, fix it here — do not route around it.
echo "Builder working directory: $REPO_ROOT (worktree)"
```

> **Orchestrator passes `TASK_ID`, `STATE_DIR`, `REPO`, `ISSUE` explicitly in every agent prompt.** Agents do NOT compute these themselves — they use the values provided by the orchestrator.

**Step 2 — write Summary and Verify Commands to `$STATE_DIR/plan.md`:**
```bash
cat > "$STATE_DIR/plan.md" <<EOF
## Summary
<one paragraph description>

## Verify Commands
setup:         events_latest "\$STATE_DIR" init | jq -e '.issue_num' >/dev/null
build:         \$(read project CLAUDE.md "## Verify Commands" → build; lockfile fallback if undeclared)
build-unit:    [ -s \$STATE_DIR/<name>-build-unit.log ] && grep -qiE "passed|[0-9]+ pass" \$STATE_DIR/<name>-build-unit.log
evidence-mode: screenshot
evidence-flows: browser-verify-<phase1>, browser-verify-<phase2>, s1-<slug>   # canonical prefixes — see rules/testing.md → File Naming Authority
EOF
```

> **Resolving `build:`**: Orchestrator resolves the `build:` command during SETUP by reading the current repo's CLAUDE.md for `## Verify Commands` → `build:`. If the section is absent, orchestrator detects the package manager from the lockfile and applies the conventional default from `rules/testing.md` → Verify Commands. The resolved literal MUST be substituted into `$STATE_DIR/plan.md` (do not leave the `$(...)` placeholder).

> **Why `$STATE_DIR` instead of a task file:** Each stage writes its log to `$STATE_DIR/` (alongside `events.jsonl`) and posts its gate marker to GitHub. Finalize (inline orchestrator) aggregates `$STATE_DIR/*.log` into the final PR comment. There is no intermediate task file.

**Step 2b — propagate base-branch (Epic sub-issues and dev branch workflows):**

Determine the base branch from one of three sources (checked in priority order):

```bash
# 1. Explicit --base-branch argument
BASE_BRANCH=$(echo "$ARGUMENTS" | sed -n 's/.*--base-branch \([^ ]*\).*/\1/p')

# 2. Re-entry: events.jsonl init event's base_branch
if [ -z "$BASE_BRANCH" ] && [ -f "$STATE_DIR/events.jsonl" ]; then
  BASE_BRANCH=$(events_latest "$STATE_DIR" init 2>/dev/null | jq -r '.base_branch // empty' 2>/dev/null || echo "")
fi

# 3. Default: empty (finalize will target main)
```

> **Why this matters:**
> - `--base-branch` — explicit per-run override. Captured in the events.jsonl init event on the first run.
> - On re-entry (subsequent `/dev` invocations on the same branch), the init event's `base_branch` is reused automatically.
> - Finalize reads `base_branch` from the events.jsonl init event; without it, PRs target main.

**Step 3 — verify context:**
```bash
echo "TASK_ID=$TASK_ID STATE_DIR=$STATE_DIR REPO=$REPO ISSUE=$ISSUE"
[ -d "$STATE_DIR" ] && echo "OK" || echo "ERROR: $STATE_DIR missing"
```

**Step 3b — emit events.jsonl init event (source of truth for pipeline state):**

Records an `init` event to the plugin-scoped `events.jsonl`. Idempotent: if `events.jsonl` already has an init event, this step is a no-op. **Skipped under `--dry-run`** so dry-run is non-destructive.

```bash
# Detect --dry-run early (Step 5 parses it canonically; this guard is for state writes only).
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

**Step 4 — compute body hash for PLAN staleness check:**
```bash
BODY_HASH=$(gh issue view "$ISSUE" --json body -q '.body' | shasum -a 256 | awk '{print $1}' | cut -c1-16)
echo "BODY_HASH=$BODY_HASH"
```

**Step 5 — parse flags:**
```bash
SKIP_PLAN=0; DRY_RUN=0
case " $ARGUMENTS " in *" --skip-plan "*) SKIP_PLAN=1 ;; esac
case " $ARGUMENTS " in *" --dry-run "*) DRY_RUN=1 ;; esac
```

**Step 6 — `--dry-run` verbose status dump (exits before PLAN stage):**

If `--dry-run`, print a verbose diagnostic of everything PLAN+gate checks would evaluate, then exit 0. Use this to debug why a pipeline would fail before committing to a full run.

```bash
if [ "$DRY_RUN" = "1" ]; then
  echo
  echo "[dry-run] /dev status for issue #$ISSUE"
  echo "  TASK_ID       = $TASK_ID"
  echo "  STATE_DIR     = $STATE_DIR"
  echo "  REPO          = $REPO"
  echo "  BODY_HASH     = $BODY_HASH"
  echo "  branch        = $CURRENT_BRANCH"
  echo "  base-branch   = ${BASE_BRANCH:-<unset, defaults to main>}"

  PLAN_COMMENT=$(gh issue view "$ISSUE" --json comments -q \
    '.comments | reverse | map(select(.body | contains("<!-- gate:dev-plan:"))) | .[0].body' 2>/dev/null)
  if [ -z "$PLAN_COMMENT" ] || [ "$PLAN_COMMENT" = "null" ]; then
    echo "  gate:dev-plan = MISSING  ← /plan-dev needed (or --skip-plan)"
  else
    SAVED_HASH=$(printf '%s' "$PLAN_COMMENT" | grep -oE '<!-- plan-hash:[a-f0-9]+ -->' | head -1 \
      | sed -E 's/.*plan-hash:([a-f0-9]+).*/\1/')
    if [ "$SAVED_HASH" = "$BODY_HASH" ]; then
      echo "  gate:dev-plan = PRESENT  (hash match: $SAVED_HASH)"
    else
      echo "  gate:dev-plan = STALE    (saved=$SAVED_HASH, current=$BODY_HASH) ← re-run /plan-dev"
    fi
  fi

  echo "  --skip-plan   = $([ "$SKIP_PLAN" = "1" ] && echo ON || echo off)"
  echo
  echo "[dry-run] exiting before PLAN stage"
  exit 0
fi
```

## PLAN Stage (embedded break-point)

Runs after SETUP, before BUILD. Orchestrator-driven, no subagent dispatch.

### Decision tree

```
1. --skip-plan flag set?           → SKIP PLAN, proceed to BUILD
2. gate:dev-plan marker on issue?
   ├─ yes, plan-hash == BODY_HASH  → SKIP PLAN, proceed to BUILD (already planned via /plan-dev)
   └─ yes, plan-hash != BODY_HASH  → HARD STOP: "plan is stale (issue body changed).
                                      Re-run /plan-dev or add --skip-plan."
3. no marker                       → RUN inline PLAN (below)
```

### Inline PLAN flow

```
a. Skill("planning-features", args: "--mode dev")  # writes $STATE_DIR/${TASK_ID}-plan.md
b. Load AskUserQuestion schema via ToolSearch     # first call only: ToolSearch("select:AskUserQuestion", max_results: 1)
c. AskUserQuestion with 3 choices:
      1) Approve        → proceed to POST
      2) Revise         → prompt user for freeform feedback (next message),
                          re-run Skill("planning-features", args: "--mode dev") with feedback appended,
                          re-ask AskUserQuestion (loop)
      3) Abort          → exit /dev without posting marker
d. POST (Approve branch):
      gh issue comment "$ISSUE" --body "$(cat $PLAN_PATH)\n\n---\n<!-- gate:dev-plan:${TASK_ID} -->\n<!-- plan-hash:${BODY_HASH} -->"
e. Proceed to BUILD stage
```

### Staleness HARD STOP (decision 2)

If a prior `gate:dev-plan` marker exists but its `plan-hash` does not match the current `BODY_HASH`, `/dev` halts with:
```
ERROR: dev-plan is stale — issue body changed since plan was written.
  saved plan-hash:   <abc123...>
  current body hash: <def456...>
Re-run /plan-dev, or use /dev --skip-plan to bypass.
```
This is not a warning — it is a hard stop. There is no `--force-stale` flag.

### Revise loop

When the user selects "Revise", they provide feedback as a freeform text input (AskUserQuestion's input-enabled option). The orchestrator appends the feedback to `$STATE_DIR/${TASK_ID}-plan-feedback.log` and re-invokes `Skill("planning-features", args: "--mode dev")` referencing the log so the skill can address the revision. Loop terminates on Approve or Abort. No fixed max — break-point relies on user judgment.

### Ralph exemption

PLAN is NOT a Ralph-loop stage. There is no retry/identical-failure logic — the break-point IS the retry mechanism (user says Revise).

### Gate marker posting

On Approve, orchestrator posts the comment directly (not via a subagent). Marker: `<!-- gate:dev-plan:${TASK_ID} -->` + `<!-- plan-hash:${BODY_HASH} -->`. Subsequent `/dev` runs with the same body will see the marker and auto-skip PLAN.

## Gate Enforcement Rules (CRITICAL)

- **Each pipeline stage MUST be a separate Agent tool call** — never run multiple stages inline.
- **Builder MUST append progress to `$STATE_DIR/build.log` after EACH phase** — for session interrupt recovery.
- **Orchestrator owns gate signalling** — after each stage passes, the orchestrator MUST (a) emit the stage event to `events.jsonl`, then (b) invoke `scripts/project_events.sh post` to mirror the event to GitHub as a `<!-- gate:<stage>:${TASK_ID} -->` comment. The projector is idempotent and records `mirror.posted` per event. Manual `gh pr comment` with the gate marker body is the documented fallback if the projector fails. Agents write evidence only.

### Gate Check Protocol

Gate verification happens at three layers:

1. **Per-stage event emission (by orchestrator):** after the stage's verify command passes, the orchestrator emits `stage.started` and `stage.passed` to `events.jsonl` — this is what Phase 4 hooks read to authorize the next tool call. Requires `$STATE_DIR` and `$ORCHESTRATOR_TOKEN` from SETUP Step 3b.

   ```bash
   # Canonical event emission per stage (run in main conversation, not in a subagent).
   # Stage names: build | review | verify. Replace <AGENT>, <STAGE>, <ITER>, <SUMMARY>.
   if [ -n "${STATE_DIR:-}" ] && [ -n "${ORCHESTRATOR_TOKEN:-}" ]; then
     DH=$(events_diff_hash "${BASE_BRANCH:-main}" 2>/dev/null || echo "0000000000000000")
     events_emit_stage_started "$STATE_DIR" "$TASK_ID" <AGENT> <STAGE> <ITER> "$DH" \
       2>/dev/null || true

     # Stamp content-addressed suffix on any unhashed evidence under
     # $STATE_DIR/evidence/ (Phase 6b). Idempotent — a no-op when files are
     # already named <logical>.<hash8>.<ext>.
     . "${CLAUDE_PLUGIN_ROOT}/scripts/store_evidence.sh" 2>/dev/null || true
     store_evidence_migrate "$STATE_DIR" 2>/dev/null || true

     # Select evidence glob + writer by stage (see glob-to-stage table below).
     # BUILD and REVIEW pass writer="" ; VERIFY (in /dev) passes writer=builder.
     case "<STAGE>" in
       build)  STAGE_EV=$(store_evidence_list_json "$STATE_DIR" 'browser-verify-*' 's*'); STAGE_WRITER="" ;;
       review) STAGE_EV='[]';                                                              STAGE_WRITER="" ;;
       verify) STAGE_EV=$(store_evidence_list_json "$STATE_DIR" 'tia-*');                  STAGE_WRITER="builder" ;;
       *)      STAGE_EV='[]';                                                              STAGE_WRITER="" ;;
     esac

     # UI-evidence enforcement (build stage only):
     # If the diff contains .tsx/.jsx/.css/.svg files, browser-verify screenshots
     # are MANDATORY — an empty evidence array here means builder skipped capture.
     # Fail hard so the builder is forced to run agent-browser before the
     # orchestrator can emit stage.passed(build).
     if [ "<STAGE>" = "build" ]; then
       _UI_CHANGED=$(git diff HEAD --name-only 2>/dev/null | grep -E '\.(tsx|jsx|css|svg)$' || true)
       if [ -n "$_UI_CHANGED" ]; then
         _EV_LEN=$(printf '%s' "${STAGE_EV:-[]}" | jq 'length' 2>/dev/null || echo "0")
         if [ "${_EV_LEN:-0}" = "0" ]; then
           echo "ERROR: UI files changed (.tsx/.jsx/.css/.svg) but no browser-verify evidence captured." >&2
           echo "Run agent-browser and save screenshots to \$STATE_DIR/evidence/browser-verify-<phase>-step<NN>-<desc>.png" >&2
           echo "Then re-emit stage.passed(build) with the evidence list." >&2
           exit 1
         fi
       fi
     fi

     # Pre-emit parity check (orchestrator-side — symmetric with pre-bash-pr-gate.sh):
     # refuse to emit stage.passed when plan.md's evidence-flows declares flows
     # that have no matching files. Without this guard the orchestrator can emit
     # an evidence array containing only the files it captured, hash-validate
     # them, and fool the PR gate into believing the contract is satisfied.
     # The PR gate has its own parity check, but the orchestrator-side check is
     # the first defence — it surfaces the missing flow at the moment of emit
     # instead of at gh-pr-create time. Skipped for stage=review (no evidence).
     if [ "<STAGE>" != "review" ] && command -v check_evidence_parity >/dev/null 2>&1; then
       if ! _PARITY_ERR=$(check_evidence_parity "$STATE_DIR" "<STAGE>" 2>&1 1>/dev/null); then
         echo "ERROR: refusing to emit stage.passed(<STAGE>) — declared evidence-flows missing files:" >&2
         printf '%s\n' "$_PARITY_ERR" >&2
         echo "Resolve by capturing the missing evidence under \$STATE_DIR/evidence/, OR amend evidence-flows in \$STATE_DIR/plan.md to match what was actually produced." >&2
         exit 1
       fi
       if ! _CUTOVER_ERR=$(check_cutover_consistency "$STATE_DIR" 2>&1 1>/dev/null); then
         echo "ERROR: refusing to emit stage.passed(<STAGE>) — plan.md contradiction:" >&2
         printf '%s\n' "$_CUTOVER_ERR" >&2
         exit 1
       fi
     fi

     events_emit_stage_passed  "$STATE_DIR" "$TASK_ID" <AGENT> <STAGE> <ITER> "$DH" \
       "<SUMMARY>" "$STAGE_WRITER" "$STAGE_EV" 2>/dev/null || true

     # Phase 3 projector — mirror the just-emitted stage event to GitHub.
     # Idempotent (records mirror.posted per event); safe to re-run. On failure,
     # fall back to manually running `gh pr comment` with the gate marker body —
     # see the orchestrator narrative in commands/dev.md L560 for the fallback contract.
     bash "${CLAUDE_PLUGIN_ROOT}/scripts/project_events.sh" post "$STATE_DIR" \
       2>&1 | sed 's/^/projector: /' || true
   fi
   ```

   **Evidence glob-to-stage mapping** (used with `store_evidence_list_json`):

   | Stage | Writer | Logical-name glob |
   |-------|--------|-------------------|
   | build | builder | `browser-verify-*` (interactive [A]) + `s*` (automated [B] E2E webms per dev-plan scenario) |
   | review | — | (no evidence; emit `'[]'`) |
   | verify (builder / TIA) | builder | `tia-*` |
   | verify (tester / qa) | tester | `s*` (scenario evidence — `.webm` and screenshot overrides; see `commands/qa.md`) |

   Review summaries MUST contain `APPROVED` on the positive path and MUST NOT contain
   `NOT_APPROVED` / `UN_APPROVED` / `DIS_APPROVED` — `pre-bash-pr-gate.sh` enforces this
   with a two-stage regex. Verify events MUST carry `writer=builder` (BUILD-mode
   TIA owner) or `writer=tester` (/qa owner).

2. **Per-stage GitHub posting (by orchestrator, dual-authority during Phase 4):** the
   orchestrator also posts the `<!-- gate:<stage>:${TASK_ID} -->` marker via
   `gh pr comment "$PR_NUM"` (build/review/verify stages) or `gh issue comment "$ISSUE"`
   (dev-plan stage — before draft PR exists). This is redundant with the event log in
   Phase 4 and removed in Phase 5, but kept here so legacy tooling and human reviewers
   continue to see the markers. Until Phase 5, emit the event FIRST, then post the
   comment — that ordering lets a crash mid-step be recovered by the projector
   (`scripts/project_events.sh`) since the event precedes the mirror.

3. **Tool-use gate enforcement (by hooks):**
   - `hooks/gate-keeping/pre-bash-commit-gate.sh` blocks `git commit` unless a
     `stage.passed(build)` event exists in `events.jsonl`.
   - `hooks/gate-keeping/pre-bash-pr-gate.sh` blocks `gh pr create` unless
     `stage.passed(build)` + `stage.passed(review, APPROVED)` +
     `stage.passed(verify, writer=builder|tester)` events exist.
   - Emergency bypass: `CLAUDE_EVENTS_HOOK_SKIP=1` (logged to `events.jsonl` as `gate.skipped`).

Stage names: `setup` | `dev-plan` | `build` | `review` | `verify` | `finalize`

The `dev-plan` gate is informational (break-point artifact); it is NOT enforced by `pre-bash-pr-gate.sh` — the pipeline's own PLAN stage check is the enforcement point.

## Orchestrator Gate-Check Protocol

After each agent stage completes, the orchestrator verifies gate passage **in the main conversation** (not inside a subagent):

1. **Run stage verify command** from `$STATE_DIR/plan.md` (e.g., the `build:` command after BUILD stage):
   ```bash
   # Example: build gate verify — substitute `build:` from $STATE_DIR/plan.md (project-declared)
   eval "$(grep -E '^build:' "$STATE_DIR/plan.md" | sed 's/^build:[[:space:]]*//')"
   grep -qiE "passed|[0-9]+ pass" "$STATE_DIR/build-unit.log"
   ```
2. **Confirm gate marker posted on GitHub:**
   ```bash
   gh api "repos/$REPO/issues/$TARGET_NUM/comments" --jq '.[].body' \
     | grep -F "<!-- gate:<stage>:${TASK_ID} -->"
   ```
3. **PASS:** Verify command exits 0 AND gate marker present → proceed to next stage
4. **FAIL:** Either condition fails → trigger Ralph or halt with error

> **Critical:** Gate verification MUST run in the main conversation. A subagent's "passed" report does NOT constitute gate passage — the orchestrator must verify independently.

## Context Resume Protocol

When a session resumes after context compression:
1. **Re-initialize task context** — run the inline snippet below to restore `TASK_ID`, `STATE_DIR`, `REPO`:
   ```bash
   REPO_ROOT=$(git rev-parse --show-toplevel)
   . "${CLAUDE_PLUGIN_ROOT}/scripts/events.sh" || { echo "ERROR: scripts/events.sh missing"; exit 1; }
   STATE_DIR=$(events_state_dir) || { echo "ERROR: cannot resolve state dir"; exit 1; }
   [ -f "$STATE_DIR/events.jsonl" ] || { echo "ERROR: no events.jsonl — session cannot be resumed"; exit 1; }
   ISSUE=$(events_latest "$STATE_DIR" init 2>/dev/null | jq -r '.issue_num // empty' 2>/dev/null || echo "")
   [ -z "$ISSUE" ] && { echo "ERROR: cannot restore issue — no events.jsonl init event"; exit 1; }
   SLUG=$(git branch --show-current | sed 's|.*/||' | tr '/' '-')
   TASK_ID="${ISSUE}-${SLUG}"
   REPO=$(git remote get-url origin | sed -e 's#^.*github\.com[:/]##' -e 's#\.git$##')
   PR_NUM=$(gh pr view --json number -q '.number' 2>/dev/null || echo "")
   ```
2. **Query posted gate markers** — `gh api "repos/$REPO/issues/$ISSUE/comments" --jq '.[].body' | grep -oE '<!-- gate:[a-z-]+:[^ ]+ -->'` lists stages already completed. Also check the PR: `gh api "repos/$REPO/pulls/$PR_NUM/comments" --jq '.[].body' | grep -oE '<!-- gate:[a-z-]+:[^ ]+ -->'` (if `PR_NUM` is set).
3. **Do NOT assume completion** — a stage is complete only if its gate marker is posted on GitHub.
4. **Proceed from the first stage without a posted marker.**

## Rules

- MUST stop on critical gate failure — no partial pipelines
- Each stage MUST pass a verification gate before the next stage begins
- SETUP rejects if `$STATE_DIR/plan.md` lacks `## Verify Commands` or issue lacks complete plan
- `## Verify Commands` must NOT appear in the GitHub issue body
- **PR body MUST be substantive** — POST-BUILD composes `$STATE_DIR/pr-body.md` from the approved dev-plan + build artifacts (Summary / Root cause / Fix / Changes / Test plan / footer). A `--body "Closes #N"` one-liner is a PIPELINE FAILURE, not a tolerable default. FINALIZE augments the body with Evidence (vitest log, TIA report, reviewer verdict) and routes any image files to the PR. PR stays draft — do NOT run `gh pr ready`. If `evidence-mode != none` but no images can be uploaded to the PR, FINALIZE HALTS and requests manual user handoff — silent skipping is forbidden.

Standalone phases: `/qa`, `/ralph`.
