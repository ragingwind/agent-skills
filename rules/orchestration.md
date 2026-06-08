# Orchestration Rules

## Foundational principles

### Planner ≠ Reviewer (MANDATORY)

The agent (or skill) that **writes** an artifact (dev-plan, qa-plan, code, test) is NEVER the agent that **approves** that artifact for promotion to a downstream stage. Approval is the responsibility of an independent reviewer agent dispatched by the orchestrator.

**Specifically**:

| Artifact | Author | Approver |
|---|---|---|
| dev-plan | `planning-features` skill (`--mode dev`) | `reviewer` agent (planned) — currently user via `AskUserQuestion` |
| qa-plan | `planning-features` skill (`--mode qa`) | `reviewer` agent in qa-plan-review mode (`agents/reviewer.md` → QAPlanReviewMode) — MANDATORY Ralph loop, max 3 iterations |
| Implementation code | `builder` agent | `reviewer` agent (qualitative audit) |
| Test results | `builder` agent (Verify mode) / `tester` agent | orchestrator inline gate-check + hooks |
| Pipeline verdict (CONDITIONAL PASS / merge) | orchestrator | user (`AskUserQuestion`) — orchestrator alone cannot decide ship-readiness |

The orchestrator MUST NOT bypass the reviewer dispatch. There is no `--skip-review` flag for plan-review or code-review. The only ways to terminate a review loop are:
1. Reviewer issues `APPROVED` (loop exits naturally)
2. Ralph terminator triggers (max 3 cycles, same-findings 3x → HARD STOP, user resolves)
3. User aborts the pipeline

> **Why**: an agent that writes a plan and judges its sufficiency systematically misses the criteria it failed to think of. Writing and reviewing engage different decision trees. Combining them collapses the audit to "did I do what I told myself to do" instead of "does this satisfy the contract".

### Every pipeline validates production environment, not mock environment (MANDATORY)

The pipeline (/dev, /qa, /epic) exists to verify the application works as the user uses it. A pass that validates only the test harness against itself is not verification — it is unit testing with extra steps.

The plan, the execution, and the evidence MUST all reflect the production environment of the feature. See `commands/qa.md` → "Real-environment principle" for the full mock/real boundary table. The reviewer agent in qa-plan-review mode rejects qa-plans that violate this principle (CRITICAL findings QC-1, QC-5; see `agents/reviewer.md` → QAPlanReviewMode).

ENV-AUDIT (new stage between SETUP and PLAN in `/qa`) refuses to enter the pipeline if the declared production environment is unreachable.

### Every test produces evidence in the production path (MANDATORY)

Each scenario in the plan produces an evidence file (.webm or .png) AND a companion `<filename>.metadata.json` recording:
- `production_path_exercised: bool`
- `mocked_production_routes: string[]`
- `production_routes_exercised: string[]`
- `is_synthetic_fixture: bool`
- `harness: "agent-browser" | "claude-in-chrome" | "manual" | "unit-test-mock"`
- `auth: "real-user-session" | "test-mode-fallback" | "unauthenticated"`

Both `/qa` AND `/dev` verify gates require: `count(evidence with production_path_exercised: true AND harness != "unit-test-mock") ≥ 1` for any cutover phase (see "Cutover phase contract" below). `/qa` additionally requires `≥ count(P1 capabilities)`. Mismatch → BLOCKING.

This metadata is the audit trail — without it, "tests pass" claims cannot be reconciled against the production code path that ships.

### Cutover phase contract (MANDATORY)

A phase is a "cutover" when it changes which code path the user-facing flow takes:
flag flip on/off, mode collapse (e.g., embedded→single), transport swap,
sandbox token change, registry replacement, or any other path-swap that affects
how the deployed app routes requests or renders the UI.

**Cutover phases MUST declare themselves in `$STATE_DIR/plan.md`** with a top-level field:

```
cutover-phase: true | false
```

When `cutover-phase: true`:
1. At least one evidence file MUST have `production_path_exercised: true` AND `harness != "unit-test-mock"` in its `.metadata.json`
2. Round-trip / fetch-mocked / `InMemoryTransport` evidence is rejected as cutover proof — these mock the very boundaries (CSRF, cookies, undici header behavior, Next.js routing) where cutover bugs live
3. The `pre-bash-pr-gate.sh` hook enforces this automatically — there is no honor system; failed declarations block PR creation

When the field is missing or `cutover-phase: false`, the existing checks apply unchanged. Builders MUST declare the field — defaulting to absent IS NOT a way to skip the check. The reviewer MUST flag missing or incorrect `cutover-phase` declarations as HIGH severity.

**Acceptable harness values for cutover evidence (in priority order):**
1. `agent-browser` — automated, against `pnpm dev` server WITHOUT `PLAYWRIGHT_TEST_MODE`
2. `claude-in-chrome` — against an authenticated tab the user already has open
3. `manual` — user-manual stop-the-line handoff: orchestrator posts a step-by-step manual scenario and HALTS until user confirms PASS

If all three are blocked, the cutover phase HALTS — `gate:build` is NOT posted. "Pre-existing harness blocker out-of-scope" is NEVER acceptable as cutover gate evidence.

> **Why this exists:** Issue #811 Phase 7 shipped a cutover where `agent-browser` failed under `PLAYWRIGHT_TEST_MODE` (`useMCPServers()` returned empty allowlist → widget never invoked). The builder reported "server-side wiring fully proven by round-trip tests" and the orchestrator accepted it. The round-trip tests mocked `global.fetch` and never reached the real route handler — they could not catch the actual production breakage. The hook now enforces what the rule requires — single source of truth.

### Identity Lock at SETUP (MANDATORY)

Once `events_emit_init` writes the init event, `TASK_ID` and `STATE_DIR` are immutable for the run. Identity-affecting decisions (branch name, base branch) MUST be confirmed before init.

If discovered after init: HARD STOP → `rm $STATE_DIR/events.jsonl` → apply the change → re-run SETUP. Workarounds (symlink, manual relocation, slug pinning while branch drifts) are FORBIDDEN.

`events_state_dir` is worktree-pinned: once init exists, it returns the same path regardless of branch renames.

### Stage Gate Atomicity (MANDATORY)

Within a stage, three steps are atomic in order: (1) evidence upload, (2) `stage.passed` event, (3) gate marker comment. If any step fails, the stage is incomplete — do not proceed.

Once the gate marker is posted, the stage is closed. Retroactive evidence additions to a closed stage are FORBIDDEN — open a follow-up issue instead.

## Pipeline Lifecycle

```
/plan-dev: setup → plan(skill) → post (standalone, no break-point)
/plan-qa:  setup → plan(skill) → REVIEW(reviewer agent + Ralph max-3) → post
/dev:      setup → [plan(skill + AskUserQuestion break-point) → build → review → verify] → finalize
/qa:       setup → ENV-AUDIT → [plan(skill + REVIEW Ralph + AskUserQuestion break-point) → qa] → finalize
```

- **Plan** (embedded in /dev and /qa): orchestrator runs `Skill("planning-features", args: "--mode dev")` or `Skill("planning-features", args: "--mode qa")`, presents result via `AskUserQuestion` (Approve / Revise / Abort). Auto-skips if a matching `gate:<plan>` marker with current body hash already exists, if `--skip-plan` is set, or — for /qa — if a release tag triggers regression mode. Hash mismatch = HARD STOP (no `--force-stale` bypass).
- **Build**: builder (Build mode) implements + runs dev tests (unit, integration, related E2E) + browser-verify
- **Review**: reviewer audits builder output (code quality, security)
- **Verify**: builder (Verify mode) runs dev-level testing — **TIA (Test Impact Analysis) on affected specs only**. Full regression is NOT builder's job — it is owned by `tester` in `/qa`.
- **QA**: tester agent runs full pipeline — qa-plan, **TIA-gap regression (specs NOT already covered by /dev TIA)**, user scenarios, evidence. Full-suite regression runs only in Regression mode (release tag).
- **Finalize**: commit, PR ready, CI check, issue closure (inline orchestrator)

### Standalone plan commands

`/plan-dev` and `/plan-qa` let users generate a plan ahead of time (e.g., for review across sessions) and post it as an issue comment with `gate:<plan>` + `plan-hash` markers. The markers are the single source of truth — `/dev` and `/qa` auto-skip their embedded PLAN stage when they see a valid marker. Re-runs post new comments; prior comments are preserved as history.

## Evidence Gate

Every pipeline run requires explicit declaration of evidence requirements in the task file's `## Verify Commands` section:

- `evidence-mode: screenshot` — (default) UI changes; multiple `.png` screenshots per scenario. Each user action step gets its own screenshot. Stored in `$STATE_DIR/evidence/`.
- `evidence-mode: video` — UI changes with complex interactions; `.webm` recordings per scenario.
- `evidence-mode: none <reason>` — non-UI changes; evidence gate auto-passes.
- **Field must always be set explicitly** — absence defaults to `screenshot` for backward compatibility.
- Legacy `video-required: true/false` still supported: `true` → `video`, `false` → `none`.

`evidence-flows:` lists each expected flow name (prefix convention: `browser-verify-*` for [A], `s<N>-*` for [B]; see `rules/testing.md` → File Naming Authority for the canonical set).
Gate enforcement: GitHub comment markers (`<!-- gate:<stage>:${TASK_ID} -->`) verified by `hooks/gate-keeping/pre-bash-commit-gate.sh` and `pre-bash-pr-gate.sh`.

### Per-pipeline evidence defaults

| Pipeline stage | Evidence format | Scope | Gate owner |
|----------------|----------------|-------|-----------|
| /dev build (browser-verify) | `.png` screenshots | manual builder verification | build gate |
| /dev verify (TIA) | `$STATE_DIR/<name>-tia.md` (always) + `tia-<spec>-step<NN>.png` **only for Playwright E2E specs** (browser state is not capturable as text) | ONLY specs affected by the diff (Test Impact Analysis) — NOT full regression | verify gate (TIA gate) |
| /qa scenarios | **`.webm` video per scenario (default)** | qa-plan acceptance/UAT scenarios | qa gate |
| /qa full regression (release-tag mode) | `.webm` video per scenario | ALL specs in suite | qa gate (Regression mode) |

### Gate rules added

- **TIA gate** (in /dev verify stage): `$STATE_DIR/<name>-tia.md` MUST exist. `tia-*.png` is required ONLY when the affected specs include Playwright E2E tests — for those, a browser screenshot proves real UI state that text cannot capture. For vitest unit tests, `tia.md` is the sole evidence artifact; capturing a terminal screenshot adds no information and is forbidden (the structured pass/fail data is already in `tia.md`). If builder (Verify mode) ran no affected specs, the TIA report must declare the gap explicitly — silent empty TIA is not allowed.
- **QA evidence gate** (in /qa stage): scenario evidence MUST be `.webm` (not `.png`, not `.gif`), one per scenario. The /qa default is `video` even when the task file leaves `evidence-mode: screenshot`; the tester agent is responsible for the override. Explicit screenshot override requires a written rationale in the QA report.

## Agent Responsibilities

### builder
Operates in two modes depending on the orchestrator's invocation:

**Build mode** — BUILD stage of /dev:
- Code implementation
- Unit tests (vitest) — test-first (TDD) — MANDATORY deliverable
- **Integration tests — MANDATORY deliverable equal to unit tests** when the change crosses ≥2 layers, depends on real DB/network/filesystem, or validates a wiring contract between modules. Unit tests alone are insufficient for any change that exercises an integration boundary.
- Related E2E specs (directly affected by the change)
- Browser screenshot verification for UI changes
- **Build verification evidence (MANDATORY for UI changes):**
  - Screenshots saved to `$STATE_DIR/evidence/browser-verify-<phase>-step<NN>-<desc>.png`
  - Verification details written to `$STATE_DIR/build.log` (URL, steps, pass/fail, screenshot paths)
- Posts `<!-- gate:build:${TASK_ID} -->` directly.

**Verify mode** — VERIFY stage of /dev (after REVIEW):
- **TIA (Test Impact Analysis)** — executes ONLY specs affected by the git diff (identified via import graph + co-located `*.test.*`). Full regression is NEVER builder's job.
- Writes `$STATE_DIR/<name>-tia.md` + `$STATE_DIR/evidence/tia-*.png`. Does NOT post any gate marker — orchestrator posts `<!-- gate:verify:${TASK_ID} -->` with `writer: builder`.
- Post-review re-run: if reviewer requests CHANGES_REQUIRED, builder fixes in Build mode, then re-runs TIA in Verify mode over the refreshed diff.

**Skills & references:**
- Skills: `tdd` (Build mode)
- Reference skills (load for methodology): `agent-browser`, `playwright`, `e2e`
  - `agent-browser` — UI change screenshots (Screenshot Workflow; no recording in /dev)
  - `playwright` — E2E spec writing/running for directly affected flows (Build mode) and TIA spec execution (Verify mode)
  - `e2e` — POM and wait patterns when designing or running specs

### tester
Owns professional QA — runs after builder + reviewer, typically in /qa (independent pipeline after PR):
- QA plan generation — regression scope + user scenarios (SFDPOT matrix, C-number capability mapping)
- **TIA-gap regression E2E** — runs ONLY the specs that /dev TIA did NOT cover (read from qa-plan `## Scope Boundary → TIA gap`). NEVER re-runs TIA-covered specs.
- **Full-suite regression** — ONLY in Regression mode (release tag like `v1.2.0`): `git diff <tag>...HEAD`, runs all unit + all E2E.
- User scenario validation (real browser, real API) — video recording
- Video evidence collection (tester agent auto-overrides task-file `evidence-mode: screenshot` to video; explicit screenshot override requires written rationale)
- Release gate validation — PASS / CONDITIONAL PASS / FAIL
- Skills: `planning-features` (evidence upload is orchestrator's responsibility, not the tester agent's)
- Reference skills (load for methodology): `agent-browser`, `playwright`, `e2e`
  - `agent-browser` — QA scenario Recording Workflow (`.webm` evidence)
  - `playwright` — TIA-gap regression + Regression-mode full-suite execution
  - `e2e` — E2E architecture and scenario design based on qa-plan

### reviewer
Complements builder — code audit only:
- Code quality, security, anti-patterns
- Runs after BUILD, before QA
- Skills: `review`

## Skill Integration Pattern

Skills are technology-focused — they document how to use a tool, not where to save output or which project they are in. The **caller** (agent) is responsible for providing all context.

### Caller Responsibilities

When invoking a skill, the calling agent MUST provide:
- **Output paths** — e.g., `$STATE_DIR/evidence/`, `$STATE_DIR/evidence/<flow>.webm`
- **URLs** — resolved from project config (per the target project's CLAUDE.md) before passing to the skill
- **File naming conventions** — e.g., `browser-verify-<phase>-step<NN>-<desc>.png`, `tia-<spec>-step<NN>.png`
  > See rules/testing.md#file-naming-authority for the single source of truth.
- **Workflow selection** — which skill workflow to use (e.g., Screenshot Workflow vs Recording Workflow)

### Skill Responsibilities

Skills MUST NOT contain:
- Hardcoded `$STATE_DIR` or absolute output paths
- Project-specific script names, env vars, or URL schemes (these belong in the target project's CLAUDE.md)
- Pipeline stage names or `/dev` vs `/qa` branching logic inside the skill body
- File naming conventions that belong to the caller

### Example: Invoking agent-browser

```bash
# 1. Caller resolves project-specific context
#    Resolve DEV_URL via the mechanism declared in the target project's CLAUDE.md
#    (e.g., a local script, a package-manager command, or an env var).
DEV_URL=<project-declared resolution command>
OUTPUT_DIR="$STATE_DIR/evidence"

# 2. Caller selects the workflow and passes context as arguments
# Follow agent-browser Screenshot Workflow with:
#   <url>         = $DEV_URL
#   <output-dir>  = $OUTPUT_DIR
#   File naming   = browser-verify-<phase>-step<NN>-<desc>.png  (caller's convention)
```

## Persistence Contract

### Phase 1 — Ghost event recording (additive, in progress)

The system is migrating to a local-authoritative event log (`events.jsonl`) under plugin-scoped storage:
`$HOME/.local/state/agent-skills/<hostname>/<project-slug>/<branch-slug>/events.jsonl`.

During Phase 1 the log is **additive** — orchestrator stages record events alongside the pre-existing `$STATE_DIR/*` artifacts + GitHub gate-marker paths, and event-recording failures MUST NOT block the pipeline. Gate enforcement continues to come from GitHub comments in this phase.

Helpers live in `scripts/events.sh` (source as `. "$HOME/.claude/scripts/events.sh"`). Ghost blocks are embedded in `commands/dev.md`, `commands/qa.md`, `commands/plan-dev.md`, `commands/plan-qa.md`, and `commands/epic.md`. Gate-comment posting (and the corresponding `mirror.posted` event) is handled centrally by `scripts/project_events.sh`.

### Three Storage Tiers

| Tier | Location | Content | Writer | Reader |
|------|----------|---------|--------|--------|
| **Per-branch state** | `$STATE_DIR/` (resolved by `events_state_dir` — under `$HOME/.local/state/agent-skills/<hostname>/<project-slug>/<branch-slug>/`) | events.jsonl + stage logs, test output, videos, plans | Each agent during its stage | orchestrator (finalize) |
| **GitHub** | Issue, PR comments | Per-stage gate markers + final published state | Each stage (gate marker) + orchestrator (finalize, final PR comment) | Humans, CI, gate hooks |

### One-Way Flow

```
Agent → $STATE_DIR/<stage>.log (artifact) → gh pr comment with <!-- gate:<stage>:${TASK_ID} --> → finalize (orchestrator) → final PR comment
```

Each stage posts its own gate comment directly to GitHub. Finalize (inline orchestrator) aggregates logs from `$STATE_DIR/` into a single final PR comment.

### Agent Persistence Pattern (unified)

Every producing agent follows the same pattern:
1. Orchestrator computes TASK_ID, STATE_DIR, REPO in SETUP (inline bash) and passes them explicitly in every agent prompt.
2. Write artifact to `$STATE_DIR/<stage>.log` (or `$STATE_DIR/<name>-<type>.<ext>`).
3. Post a GitHub comment containing `<!-- gate:<stage>:${TASK_ID} -->` with the stage summary.
4. Done. Finalize (inline orchestrator) reads `$STATE_DIR/` to assemble the final PR comment.

### Gate Markers

| Stage | Marker | Writer | Required contents | Hook enforcement |
|-------|--------|--------|-------------------|------------------|
| build | `<!-- gate:build:${TASK_ID} -->` | builder (/dev) | Unit/integration test results; browser-verify screenshot paths if UI changed | `pre-bash-commit-gate.sh` (blocks `git commit`) + `pre-bash-pr-gate.sh` (blocks `gh pr create`) |
| review | `<!-- gate:review:${TASK_ID} -->` | reviewer (/dev) | Body MUST contain `APPROVED` (or `CHANGES_REQUIRED`) | `pre-bash-pr-gate.sh` (APPROVED required) |
| verify | `<!-- gate:verify:${TASK_ID} -->` | orchestrator (after builder Verify mode in /dev or tester in /qa) — body MUST include `writer: builder` or `writer: tester` on its own line | TIA report + `tia-*.png` (writer=builder) OR QA report + `.webm`/`.png` scenario evidence (writer=tester) | `pre-bash-pr-gate.sh` (blocks `gh pr create`); branches on `writer:` field — builder → `<name>-tia.md` + `tia-*.png` (when UI changed); tester → `.webm` or scenario `.png` |
| dev-plan | `<!-- gate:dev-plan:${TASK_ID} -->` + `<!-- plan-hash:<sha> -->` | `/plan-dev` (standalone) OR `/dev` PLAN stage (embedded) | Implementation plan body | Informational — enforced by `/dev` PLAN stage check (hash match), not by hooks |
| qa-plan | `<!-- gate:qa-plan:${TASK_ID} -->` + `<!-- plan-hash:<sha> -->` | `/plan-qa` (standalone) OR `/qa` PLAN stage (embedded) | Scenario list + regression scope (`## Scope Boundary`) | Informational — enforced by `/qa` PLAN stage check (hash match), not by hooks |

**Why `verify` marker is reused by both builder (Verify mode) and tester**: There is a single "testing has passed" gate per PR, regardless of whether the evidence came from /dev TIA or /qa full QA. Reusing the marker keeps the PR-creation hook (`pre-bash-pr-gate.sh`) simple and avoids a second hook for the /qa path. Stage NAMES (`verify` vs `qa`) are distinct for pipeline bookkeeping; MARKER NAMES collapse to `verify` because the hook only cares whether testing evidence was posted.

## Bookkeeping Principle

Agent prompts should focus on the primary task. Persistence is minimal — append to `$STATE_DIR/<stage>.log`, post gate comment, done.

- **`events.jsonl` is the source of truth for pipeline state and stage summaries (Phase 2+).** `$STATE_DIR/` holds the event log plus large artifacts (logs, test output, screenshots) under `$STATE_DIR/evidence/`. Evidence filenames are content-addressed: `<logical_name>.<hash8>.<ext>` (hash8 = first 8 hex chars of SHA-256; see `rules/testing.md` → "File Naming Authority"). Orchestrators stamp the suffix via `store_evidence_migrate` before emitting `stage.passed`; `pre-bash-pr-gate.sh` verifies the hash on PR creation.
- **GitHub gate markers are a one-way projection** of `events.jsonl` — used by legacy tooling and humans; they do NOT authoritatively declare state.
- Finalize (inline orchestrator) aggregates per-stage logs from `$STATE_DIR/` into the final PR comment.

### Progressive Reporting (per-stage direct posting)

Each stage posts its own comment to the PR (or issue when no PR exists yet) at the end of its run. No central hook, no progress table diffing — the gate marker IS the progress signal.

- **Who posts**: the stage itself, immediately after writing its `$STATE_DIR/<stage>.log`.
- **What**: one comment per stage, containing the `<!-- gate:<stage>:${TASK_ID} -->` marker and a one-section summary.
- **Verification**: `hooks/gate-keeping/pre-bash-commit-gate.sh` and `pre-bash-pr-gate.sh` read these markers to enforce gates at tool-use time.
- **Failure policy**: if a stage fails, it does NOT post its gate marker; the next gate-enforced action (`git commit`, `gh pr create`) is blocked automatically.

## Large Project Protocol

Issue > 2,000 LOC or > 2 implementation phases → apply this protocol instead of standard /dev pipeline.

### Core Rules
- **One Epic per session** — never chain multiple Epics in a single dev pipeline run
- **epic branch is the merge target** — Epic sub-issue PRs target the epic branch (`epic/<topic>`), NOT canary directly
- **Merge is the gate** — next layer must NOT start until previous layer's PR is merged to the epic branch
- **Final PR to canary** — after all sub-issues merge to the epic branch, create one final PR: `epic/<topic>` → `canary` (epic issue closes on merge)
- **CI is the final truth** — `gh pr checks` green = done. Agent reports are informational only
- **Epic size limit** — each sub-issue: < 2,000 LOC, < 2 phases, single focused concern

### Epic Branch Workflow
```
canary  (main branch, single source of truth)
  └─ epic/<topic>                              ← epic branch, accumulates sub-issue PRs
       ├─ epic/<topic>/<sub1>-<slug>          ← Layer 0 PR → epic branch
       ├─ epic/<topic>/<sub2>-<slug>          ← Layer 1 PR → epic branch (after Layer 0 merges)
       └─ epic/<topic>/<sub3>-<slug>          ← Layer 2 PR → epic branch (after Layer 1 merges)
                ↓
       Final PR: epic/<topic> → canary  (epic issue closes on merge)
```

> **Git ref constraint:** A branch `epic/<topic>` and `epic/<topic>/<sub>` cannot coexist
> because git refs treat the first as a file and the second as a directory.
> The epic branch must be created **before** sub-issue branches.
> Sub-issue branches nest under the epic branch name for logical hierarchy.

### Pre-flight (before any dev pipeline on a large issue)
1. Check for already-merged PRs: `gh pr list --search "closes #N" --state merged`
2. If work already exists on the canary branch: do NOT redo it, build on it
3. Confirm Epic scope fits within one session before starting

### Epic decomposition order
Infrastructure → Non-security pages/logic → Security-critical logic → Verification

Never compress all Epics into one session. One session = one Epic = one PR.

## Subagent Safety

- NEVER use `run_in_background: true` for test commands in subagents
- **Gate verification independence** — orchestrator MUST run verify commands directly in the main conversation, not inside subagents. Subagent's "passed" report does NOT constitute gate passage.
- Tester agent's green phase (confirming implementation passes) requires orchestrator mediation — tester reports results, orchestrator decides whether gate passes

## Failure Recovery

### Ralph Integration

Ralph (`commands/ralph.md`) is a **domain-agnostic retry loop primitive**. Each pipeline stage that needs retry-on-failure behavior invokes Ralph with injected parameters (executor/verifier/fixer/terminator).

- Ralph itself MUST NOT know which agent runs, what it checks, or which gate it serves.
- Stage-specific Ralph parameterizations are declared in each pipeline command (`commands/dev.md`, `commands/qa.md`).
- Ralph guarantees bounded iteration; default policy is max 5 + same-failure 3.

| Failure | Recovery | Escalation |
|---------|----------|------------|
| Build gate | `/dev` BUILD stage Ralph loop (see `commands/dev.md`) | No fixed max (3 identical OR 3 consecutive = STOP) |
| **Review gate (CRITICAL/HIGH)** | **`/dev` REVIEW stage Ralph loop (see `commands/dev.md`)** | **Max 3 full cycles (3 identical findings = STOP)** |
| Plan stage (embedded) | User chooses Revise → orchestrator collects freeform feedback → re-invokes `Skill("planning-features", args: "--mode dev")` / `Skill("planning-features", args: "--mode qa")` → re-asks AskUserQuestion | No fixed max (break-point = user judgment) |
| tester agent Phase 1 invalid plan | ABORT. tester agent does NOT regenerate. Orchestrator deletes plan file, reports to local log, user re-runs /plan-qa | — (decision 3) |
| QA gate | `/qa` QA stage Ralph loop (see `commands/qa.md`) | Max 5 iterations (3 identical = STOP) |
| Verify gate | `/dev` VERIFY stage Ralph loop (see `commands/dev.md`) | Max 5 iterations (3 identical = STOP) |
| Test-first gate skip | Re-dispatch builder for failing tests | 3 failures → STOP |
| Spec gap | Re-dispatch tester for spec tests | 1 retry → flag in PR |
| Review file missing | Re-dispatch reviewer | 1 retry → note in PR |
| CI failure (FINALIZE) | PIPELINE HALT → builder fixes → test reruns → retry | 3 cycles → HARD STOP |
| Builder 3-failure STOP | Escalate to debugger (dedicated debug investigation loop; see `agents/debugger.md`) | 5 cycles (angle rotation each) → STOP |

### Qualitative Review Remediation (`/dev` REVIEW stage Ralph loop — operational detail)

When `/dev`'s REVIEW stage Ralph loop triggers (verdict FAIL with CRITICAL or HIGH findings), the orchestrator MUST follow the semantics below. The Ralph parameter block itself is declared in `commands/dev.md` → "REVIEW stage — Ralph invocation"; this section specifies the operational semantics callers must enforce around that loop — NEVER fix code inline.

**Flow (matches the injected executor/fixer pattern):**
```
iteration N executor  = reviewer (full qualitative audit) → gate-check(review) → FAIL(CRITICAL/HIGH)
  → orchestrator reads review report, extracts action items
  → iteration N fixer = builder: receives specific findings + file:line + fix suggestions
  → iteration N+1 executor = reviewer (full qualitative re-review of the whole diff, NOT just action items)
  → gate-check(review) → PASS or loop continues
```

**Orchestrator responsibilities:**
1. Read `$STATE_DIR/<name>-review.md` and extract all CRITICAL (🔴) and HIGH (🟠) findings
2. For each finding, extract: severity, description, `file:line`, and suggested fix
3. Dispatch builder with structured fix instructions (one agent call per iteration)
4. After builder completes: run the project-declared `build:` command (`$STATE_DIR/plan.md` → `Verify Commands` → `build:`; see `rules/testing.md` → Verify Commands) to verify build still passes
5. Remove old review log (`rm $STATE_DIR/<name>-review.md`). The previous GitHub gate comment is NOT deleted — gh CLI has no comment-delete command. The new review comment supersedes it; the gate hook (`pre-bash-pr-gate.sh`) validates the most recent APPROVED marker. Dispatch reviewer for full qualitative re-review.
6. Check for re-posted `<!-- gate:review:${TASK_ID} -->` marker containing `APPROVED` — if missing, repeat from step 3

**Qualitative re-review requirements:**
- Reviewer MUST re-examine the entire diff — not just the lines changed by the fix
- Reviewer MUST verify fixes are semantically correct (correct logic, not just syntactically valid)
- Reviewer MUST check for new issues introduced by the fix (regression, side effects)
- The re-review produces a fresh `$STATE_DIR/<name>-review.md` AND a fresh posted review gate comment — it is NOT an incremental check

**Termination:**
- PASS: review verdict is APPROVED with 0 CRITICAL and 0 HIGH → proceed to TEST
- Max 3 iterations: if 3 review-fix cycles complete without APPROVED → HARD STOP
- 3 identical findings: same finding persists across 3 iterations → HARD STOP (builder cannot resolve)

**Anti-patterns (FORBIDDEN):**
- Orchestrator fixing code directly in main conversation instead of dispatching builder
- Skipping re-review after builder fix (mechanical gate-check alone is insufficient)
- Marking review gate as passed when CRITICAL/HIGH findings exist
- Running reviewer with "just check these specific items" — MUST be full re-review

### Ralph Termination Conditions

| Condition | Action |
|-----------|--------|
| Goal achieved | Exit loop, post gate marker to GitHub |
| Max iterations reached (QA/Test: 5) | HARD STOP, report to user |
| 3 identical failures | HARD STOP — same error, no progress |
| 3 consecutive failures | HARD STOP, report to user |

### Gate Result Persistence (Mandatory)

Each stage posts exactly one comment to the associated PR (or issue) containing its `<!-- gate:<stage>:${TASK_ID} -->` marker. Posting is non-optional and signals stage completion:

- **On pass**: stage posts the gate marker comment; downstream gate hooks (`pre-bash-commit-gate.sh`, `pre-bash-pr-gate.sh`) see the marker and allow the next tool use.
- **On fail**: stage does NOT post the marker; downstream actions (`git commit`, `gh pr create`) are blocked by the gate hooks.

The orchestrator MUST ensure each stage posts its marker after every attempt (including Ralph retries). Ralph queries posted markers via `gh api repos/$REPO/issues/$NUM/comments` to decide whether to retry or stop.

## Parallelization

- Verify task independence before parallelizing
- NEVER parallelize tasks modifying the same files
- Aggregate results before dependent tasks begin

## Routing

Triage produces a **recommendation only** — it never triggers the next step automatically.

After triage, the orchestrator presents the recommendation to the user and waits for confirmation:

| Triage result | Recommendation | Orchestrator action |
|---------------|----------------|---------------------|
| `valid` + enhancement classification | "Run `/plan` to create implementation plan?" | Wait for user confirmation |
| `valid` + other classifications | "Run `/dev` directly?" | Wait for user confirmation |
| `invalid` | Close issue | Wait for user confirmation (always) |

> Classification refers to triage's own categorization of the issue (its in-memory result), not a GitHub label read. The orchestrator MUST NOT query labels to make this decision.

The user may override the recommendation (e.g., skip `/plan` if a plan already exists).

## Labels

Labels are a **user-local convention**, not a pipeline dependency. The `/dev`, `/qa`, `/plan-dev`, `/plan-qa`, and `/epic` pipelines do NOT read or write labels — gate-keeping is local-only via `events.jsonl`. Label catalog (for users who maintain one): see `rules/labels.md`. Labels are applied through the explicit `/triage` workflow, not as a side effect of plan/dev/qa runs.

## Issue Obligation

### Issue Context Capture
When working on a GitHub issue, pass the issue number as the first positional
argument to the pipeline (`/dev 123`, `/qa 123`, `/plan-dev 123`, …). The SETUP
stage records it in the `events.jsonl` init event — the single source of truth
for issue lookup. On re-entry (after compression or retry), commands resolve
the issue via `events_latest "$STATE_DIR" init | jq -r '.issue_num'`.

### Commonly Forgotten Items
- **Dev server** — follow the project's CLAUDE.md for start/stop commands and URL resolution; global rules do not mandate a specific dev-server mechanism
- E2E test evidence (webm capture — NOT gif)
- Review report **posted as `gh pr comment`** — a report file in `$STATE_DIR/` is invisible to reviewers; MUST be posted to the PR and verified with `gh api .../comments`
- Issue checklist sync
- Manual test checklist in PR body (read from test plan `## Manual Tests` section)
- Browser verify warm-up: `snapshot` before `record start` to let the dev server compile the page (avoids recording a long loading screen)

## Migration Status

The orchestration system is mid-migration from dual-authority (GitHub + legacy `.workstate/` + per-task `/tmp/claude-${PROJECT_HASH}/${TASK_ID}/`) to local-authoritative `events.jsonl` under the plugin-scoped `$STATE_DIR`:

- Phase 0-3 (complete): event log + dual-read hooks + projector.
- Phase 4 (complete): pre-entry hardening — absent events.jsonl denies by default.
- Phase 5 (complete): all state reads/writes collapsed under `$STATE_DIR` resolved via `events_state_dir` + `events_latest`; legacy `.workstate/` and per-task `/tmp/claude-*/` paths eliminated; `$WORK_DIR` → `$STATE_DIR` renamed throughout commands, agents, skills, and rules. Gate hooks are events-authoritative only — `CLAUDE_EVENTS_HOOK_SKIP=1` is the only remaining emergency bypass (logged to events.jsonl).
- Phase 6 (complete): content-addressed evidence under `$STATE_DIR/evidence/<logical>.<hash8>.<ext>`.
  - 6a: `scripts/store_evidence.sh` helper + `pre-bash-pr-gate.sh` re-hash verification.
  - 6b: orchestrator emission templates in `commands/dev.md` + `commands/qa.md` call `store_evidence_migrate` + `store_evidence_list_json` before `events_emit_stage_passed`; agents continue to write logical names.
  - 6c: `store_evidence_verify` rejects filenames without a `<hash8>` suffix; the backward-compat pass-through from 6a is removed. All writers must call `store_evidence` or `store_evidence_migrate` first. All agent/skill writers (builder browser-verify + TIA, tester QA video/screenshot, planning-features scaffolds, upload-evidence collector) now land files under `$STATE_DIR/evidence/` with canonical `browser-verify-*` / `tia-*` / `s<N>-*` prefixes so the orchestrator's per-stage globs capture them before emission.
