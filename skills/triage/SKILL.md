---
name: triage
description: Issue evaluation, label management, and label sync.
---

# Triage

Evaluate issues, produce a detailed triage report, apply changes, recommend implementation order, and manage label sync.

> **Scope note: labels are user-local.** This is the only skill that writes labels to GitHub. Pipelines (`/dev`, `/qa`, `/plan-dev`, `/plan-qa`, `/epic`) do NOT depend on labels — they read `events.jsonl` for gate decisions and treat the GitHub issue body as user-authored content (read-only). Run `/triage` only when working in a repo whose label catalog matches `rules/labels.md`. In repos without that catalog, this skill will report "label does not exist" and stop without auto-creating.

## Usage

```
Skill(skill: "triage")
Skill(skill: "triage", args: "42")
Skill(skill: "triage", args: "42 55")
Skill(skill: "triage", args: "--dry-run")
Skill(skill: "triage", args: "--approved")
Skill(skill: "triage", args: "42 --approved")
Skill(skill: "triage", args: "label")
Skill(skill: "triage", args: "label 42 55")
Skill(skill: "triage", args: "sync")
Skill(skill: "triage", args: "sync 42")
```

Parse `$ARGUMENTS`:
- First word is a number, `--dry-run`, `--approved`, or empty → **Triage mode**
- First word is `label` → **Label Sync: batch labeling mode**
- First word is `sync` → **Label Sync: standardization mode**

Flags (Triage mode only):
- `--dry-run` — stop after Phase 2 (report only, no confirmation prompt)
- `--approved` — skip Phase 2 confirmation prompt and apply immediately after report

---

## Triage

Evaluate issues, produce a detailed triage report, then apply changes.

- Numbers specified: process those issues only
- No numbers: auto-detect via `gh issue list --state open --json number,title,labels --jq '.[] | select(.labels | length == 0)'`
- `--dry-run`: stop after report phase
- Auto-detect mode (no numbers): always runs Phase 5 (Implementation Recommendation) after completion — scans all `status:ready` open issues for ranking

When 2+ targets → use `/swarm` for per-issue parallel processing (issues are independent).
Model routing: simple issues → sonnet, complex issues (long body, architecture) → opus.

### Phase 1: Analyze

For each issue:

#### 1.1 Read & Classify

1. Read issue: `gh issue view <number>`
2. Classify type: feature request / bug report / question / chore / other
3. Assess validity: feature (value, feasibility, scope) · bug (reproducibility, severity) · other (appropriateness)
4. Assess information sufficiency: if the issue body lacks enough detail to fill the seed template (Summary, Goals, Constraints), ask the user targeted questions to fill the gaps before proceeding

#### 1.2 Investigate Codebase

1. Search related files: `Grep` / `Glob` for keywords from the issue
2. Identify impact scope: which modules, components, or APIs are affected
3. Note existing tests or prior work relevant to the issue

Purpose: inform verdict, priority, and edge case identification — NOT to design a solution (that's `/plan`'s job).

#### 1.3 Determine Verdict & Labels

1. Verdict: `valid` or `invalid` (with reason)
2. Recommended labels: `status:*` + `type:*` + `priority:*`
3. **QA label assessment:** Determine if `qa:e2e-required` should be applied. Two conditions must BOTH be true:

   **Condition A — E2E is genuinely necessary** (unit/smoke tests are not enough):
   - The change involves a multi-step user flow that is hard to verify in isolation
   - Visual correctness, layout, or interaction order cannot be confirmed by unit tests alone
   - A regression would only be caught by running the full app end-to-end
   Do NOT apply if: change is pure data model / persistence / utility logic with no user-visible flow

   **Condition B — E2E tooling exists and is executable for this project**:
   - Check for `playwright.config.ts`, `cypress.config.*`, XCUITest target, Espresso/Detox config, or equivalent
   - The project has a runnable E2E suite (not just unit tests)
   - CI can execute the E2E tests
   Do NOT apply if: the project has no E2E framework configured, or E2E execution is not feasible (e.g. macOS menubar app with no XCUITest target set up, hardware-dependent tests)

   Apply `qa:e2e-required` when **both A and B** are true.
   Do NOT apply for: pure backend/API changes, documentation, tooling/config, type-only refactors, or projects where E2E tooling is absent
4. Draft rewritten body (type-specific template — for features, write a minimal seed; solution design deferred to `/plan`)

### Phase 2: Report

Present a detailed triage report **in the same language the user used** when invoking the skill (e.g. Korean request → Korean report). GitHub artifacts (issue body, title, labels) are always written in English regardless.

Per-issue fields: Verdict, Reason, Recommended Labels, Related Files (`file:line`), Impact.

Summary table: `| # | Title | Verdict | Recommended Labels | Action |`

After the summary table, show the **complete proposed changes** for each issue so the user can review the exact content. The preview is shown **in the user's language** — translate section headings and body content for display. Phase 3 will write the English version to GitHub.

```
### 적용 예정 변경사항 — #<number>

**제목**
<normalized title — shown in English as-is, titles are not translated>

**레이블**
<label1>, <label2>, ...

**본문 미리보기** (검토용 — 사용자 언어로 번역)
---
<full rewritten body translated into the user's language — Korean if user wrote in Korean>
---

**GitHub 저장 내용** (영어 원본 — Phase 3에서 그대로 포스팅)
---
<full rewritten body in English — this is what gets written to GitHub verbatim>
---
```

Show one such block per issue. Both versions MUST always be present: the user reviews the translated preview; Phase 3 writes the English original to GitHub verbatim. Never show only one version.

**With `--dry-run`, stops here — no confirmation prompt.**

**Without `--dry-run`:** after showing the complete proposed changes, end with a plain-text confirmation prompt and wait for the user's text reply. Do NOT use `AskUserQuestion` UI buttons.

Phrase the prompt in the same language as the user's request. Example for Korean:

```
위 내용을 적용하려면 **apply**, 취소하려면 **cancel** 을 입력해주세요.
```

If the user replies with anything other than "apply" (or equivalent affirmative), skip Phase 3 and end.

**With `--approved`:** skip the confirmation prompt and proceed to Phase 3 immediately after showing the complete proposed changes.

### Phase 3: Apply

Runs after user confirms (default mode) or immediately with `--approved`. Skipped on `--dry-run` or user Cancel.

#### Valid Issues

1. Rewrite body with type-specific template:

**Bug Report (`type:bug`):**

```markdown
## Summary
[one-line summary]
## Steps to Reproduce
1. [step]
## Expected Behavior
[what should happen]
## Actual Behavior
[what actually happens]
## Edge Cases
- [condition → expected result]
**Related Files:**
- `file:line` — description
<details><summary>Original Issue</summary>
[original body preserved as-is]
</details>
```

**Feature Request (`type:feature`):**

````markdown
## Summary
[one-line summary of the user's request]
## Goals
- [what the user wants to achieve — extracted from the issue]
## Constraints
- [known limits, requirements, or technical boundaries discovered during codebase investigation]
**Related Files:**
- `file:line` — description
> **Next:** Requires `/plan` to produce a full implementation plan.
<details><summary>Original Issue</summary>
[original body preserved as-is]
</details>
````

**Other (`type:question` / `type:chore` / etc.):**

```markdown
## Summary
[one-line summary]
## Background
[context and relevant information]
**Related Files:**
- `file:line` — description
<details><summary>Original Issue</summary>
[original body preserved as-is]
</details>
```

2. Normalize title to `type(scope): imperative description` format if it does not already follow it:
   - `type`: `feat` | `fix` | `chore` | `docs` | `refactor` | `test` | `perf`
   - `scope`: optional, lowercase module/component name (e.g., `auth`, `api`, `ui`)
   - `description`: imperative mood, lowercase, no trailing period
   - Examples: `feat(auth): add OAuth2 login`, `fix(api): handle null response`, `chore: bump pnpm to 9.x`
   - `gh issue edit <number> --title "<normalized title>"`
3. Update body: `gh issue edit <number> --body "<rewritten body>"`
3. Apply labels: `status:ready` + `type:*` + `priority:*` + (if applicable) `qa:e2e-required` — reference `references/labels.md`. If label does not exist, report (never auto-create).
   - Include `qa:e2e-required` in the `--add-label` list when the QA label assessment (Phase 1.3) determined it should be applied.
   - Example: `gh issue edit <number> --add-label "status:ready,type:enhancement,priority:medium,qa:e2e-required"`
4. Verify labels applied: `gh issue view <number> --json labels`

#### Invalid Issues

1. Post reason comment: `gh issue comment <number> --body "Closing: <reason>"`
2. **Pause for user confirmation**: Present the verdict and reason, then ask the user: "Close issue #<number> as invalid — reason: <reason>. Confirm?" — do NOT apply `status:wontfix` or close the issue until the user explicitly confirms.
3. Apply `status:wontfix` label: `gh issue edit <number> --add-label "status:wontfix"`
4. Close issue: `gh issue close <number>`

### Phase 4: Completion Report

Output final table: `| # | Title | Verdict | Labels | Action | Status |`

### Phase 5: Implementation Recommendation

Runs in auto-detect mode (no issue numbers specified) after Phase 4 completes.

**Target collection:** Gather ALL open issues with `status:ready` label — not just the issues triaged in this run:
```bash
gh issue list --state open --label "status:ready" --json number,title,labels,body
```

- **0 ready issues** → skip Phase 5
- **1 ready issue** → show as single recommendation (no ranking table, just the issue with scope estimate)
- **2+ ready issues** → full ranking table with scores

#### 5.1 Estimate Scope

For each ready issue, investigate the codebase (use Phase 1.2 data if available from this run, otherwise run `Grep`/`Glob` for keywords from the issue title/body):

1. **Related files count**: number of files identified in Phase 1.2
2. **Change scope**: single function / single module / cross-module / cross-system
3. **Module complexity**: is the affected code simple utilities or complex stateful logic?
4. **Size class**:
   - **S** — 1-2 files, < 50 LOC, isolated change
   - **M** — 3-5 files, 50-200 LOC, single module
   - **L** — 6-10 files, 200-500 LOC, cross-module
   - **XL** — 10+ files, 500+ LOC, cross-system or architectural

#### 5.2 Assess Dependencies

For each valid issue pair, check:

1. Does issue A touch files that issue B also touches? (file-level conflict)
2. Does issue A's change logically require issue B to land first? (semantic dependency)
3. Mark dependencies as `blocks #N` or `blocked by #N` where applicable
4. Issues with no dependencies: `—`

#### 5.3 Compute Recommendation Order

**Two-pass ranking: topology first, score second.**

**Pass 1 — Topological sort (hard constraint):**
If issue A blocks issue B, then A MUST appear before B in the final ranking — regardless of score. Build a dependency DAG from Phase 5.2 and produce a topological order. Issues with no dependency relationship are peers (ordered by score in Pass 2).

**Pass 2 — Score within topological tiers:**
Group issues into topological tiers (tier 0 = no blockers, tier 1 = blocked only by tier 0, etc.). Within each tier, rank by weighted composite score (higher = do first):

| Factor | Weight | Scoring |
|--------|--------|---------|
| Priority label | 45% | critical=5, high=4, medium=3, low=2, backlog=1 |
| Effort/Impact ratio | 35% | S=5, M=4, L=3, XL=1 (smaller effort = higher score) |
| Blocks count bonus | 10% | +1 per issue this blocks (max +3) |
| Type bonus | 10% | bug=+1, security=+2, other=0 |

Final score = `(priority × 0.45) + (effort_impact × 0.35) + (blocks_bonus × 0.10) + (type_bonus × 0.10)`, scaled to 1-10.

Tie-breaking within same tier: lower issue number (older) first.

**Rationale:** A blocked issue cannot start until its blockers land. Scoring alone may rank a blocked issue above its blocker, producing an unexecutable order. Topological sorting guarantees the recommendation is actionable.

#### 5.4 Output

**Max 5 issues.** Show the top 5 from the topological ranking. If more than 5 exist, truncate and note the total count.

Place the recommendation at the **bottom** of the triage output (after the Phase 4 Completion Report).

One line per issue, compact format: `rank. #number title — size priority score [blocked by]`

Show `blocked by #N, #M` for issues that have blockers. Omit dependency info for tier 0 issues (no blockers).

```markdown
## Implementation Recommendation (top 5)

1. **#42** fix(api): handle null response — S / high / 8.7
2. **#55** feat(auth): add OAuth2 login — M / medium / 6.2 — blocked by #42
3. **#61** chore: bump pnpm to 9.x — S / low / 4.1

> **Top pick: #42** — High priority bug with small scope that unblocks #55.
```

For single issue (1 ready):
```markdown
## Implementation Recommendation

→ **#42** fix(api): handle null response — S / high / 8.7
  Recommendation: [1-2 sentences why and what to do next]
```

Top pick reasoning: 1-2 sentences explaining why the #1 ranked issue should be tackled first, referencing its score factors.

---

## Label Sync

Batch labeling and label standardization/sync.

### `label` — Batch Labeling

Assign `priority:*` + `status:*` + `type:*` to unlabeled issues/PRs.

1. Collect targets: find issues/PRs with insufficient labels
   - `--open`: open items only
   - `--closed`: closed items only
   - Numbers specified: those items only
   - Default: both open and closed
2. Analyze issue content (title, body, comments) to classify
3. Reference `references/labels.md` to determine appropriate labels
4. Apply labels

```bash
# Find unlabeled issues
gh issue list --state all --json number,title,labels --jq '.[] | select(.labels | length == 0)'

# Apply labels
gh issue edit <number> --add-label "status:ready,type:enhancement,priority:medium"
```

### `sync` — Label Standardization

Inspect and clean up existing labels.

1. Replace non-standard labels with standard ones (e.g., `bug` → `type:bug`)
2. Copy issue labels to linked PRs (propagate labels from issue to PR)
3. Apply `status:done` to closed items missing a status label
4. Resolve duplicate `status:*` labels (keep most recent state only)
5. Infer missing labels from body/title analysis

```bash
# Check for non-standard labels
gh label list --limit 50 --json name -q '.[].name'

# Check linked PRs for an issue
gh issue view <number> --json closedByPullRequestsReferences

# Replace labels
gh issue edit <number> --remove-label "bug" --add-label "type:bug"
```

### Parallel Processing

When 2+ targets → use `/swarm` for per-item parallel processing (items are independent).

### Workflow

1. **Verify standard labels exist**: `gh label list --limit 50` → compare with `references/labels.md` definitions. Report missing labels to user (never auto-create)
2. **Determine targets**: collect issue/PR list based on mode and arguments
3. **Execute mode**: run `label` or `sync` processing
4. **Verify labels applied**: `gh issue view <number> --json labels` to confirm
5. **Summary table**: report results

```markdown
## Label Sync Summary

| # | Title | Before | After | Action |
|---|-------|--------|-------|--------|
| 42 | Fix login bug | — | status:ready, type:bug, priority:high | labeled |
| 55 | Add dark mode | bug | type:enhancement, priority:medium | synced |
```

---

## Rules

- **Language Policy (CRITICAL):** Two distinct language targets:
  1. **Chat output (Phase 2 report, confirmation prompt, completion report)** — MUST be in the **same language the user used** when invoking the skill. Korean request → Korean report and prompt. English request → English report and prompt.
  2. **GitHub artifacts (issue title, body, comments, labels)** — MUST always be written in **English**, regardless of the user's language. Translate the understood intent into English before writing to GitHub.
  - If the original issue body is in Korean, preserve it verbatim inside `<details><summary>Original Issue</summary>...</details>` — do NOT translate the preserved original
- MUST present triage report before applying changes (always, including default mode)
- MUST pause for user confirmation after Phase 2 report **unless** `--approved` or `--dry-run` is set
- MUST preserve original issue body in `<details>` block
- MUST investigate codebase before rewriting (find related files, assess impact)
- MUST get user confirmation before closing any issue (this applies even with `--approved`)
- MUST include related files with `file:line` references in report
- MUST reference `references/labels.md` for label definitions
- NEVER auto-create labels — report missing labels to user
- MUST verify labels after applying
- MUST report completion table after all changes applied
- MUST NOT remove labels without replacement (sync mode)
- MUST preserve `area:*` and `platform:*` labels during sync
