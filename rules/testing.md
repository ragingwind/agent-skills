---
paths:
  - "**/*.test.*"
  - "**/*.spec.*"
  - "**/tests/**"
  - "**/playwright.config.*"
  - "**/*.e2e.*"
---

# Testing Rules

For TDD methodology, use `/tdd`. For E2E testing, use `/playwright` or `/e2e`.
For test design patterns (Three-Group Taxonomy, Naming), see `rules/testing-patterns.md`.

## Read Local Rules First

Before running tests: read project CLAUDE.md, tests/README.md, playwright.config.ts.
Project-specific rules override these global defaults.

## Verify Commands (project-declared)

Pipelines (/dev, /qa) do NOT hardcode build/test commands. Each project declares them in its **project CLAUDE.md** under `## Verify Commands`. The orchestrator reads this section during SETUP and writes the values into `$STATE_DIR/plan.md`'s `Verify Commands` block; gate checks then execute those project-declared commands verbatim.

**Canonical phase names** (add entries only as needed):

| Phase | Purpose | Example |
|-------|---------|---------|
| `build` | Typecheck + lint gate for BUILD and REVIEW-fix stages | `pnpm tsc --noEmit && pnpm -r lint` |
| `unit` | Unit test execution for tester Phase 5 | `pnpm test` |
| `lint` | Lint-only (when separate from build) | `pnpm -r lint` |
| `e2e` | E2E test execution | `pnpm -r e2e` |

**Project CLAUDE.md example:**
```markdown
## Verify Commands
build: pnpm tsc --noEmit && pnpm -r lint
unit:  pnpm test
```

**Fallback when undeclared** — orchestrator detects the package manager from the lockfile and uses conventional defaults:
- `pnpm-lock.yaml` → `pnpm tsc --noEmit && pnpm -r lint` / `pnpm test`
- `package-lock.json` → `npm run typecheck && npm run lint` / `npm test`
- `yarn.lock` → `yarn typecheck && yarn lint` / `yarn test`
- `Cargo.toml` → `cargo check && cargo clippy` / `cargo test`

If neither declaration nor recognized lockfile is present, the orchestrator halts SETUP and asks the user to declare `## Verify Commands` in project CLAUDE.md.

## Unit Test Execution

**CRITICAL:** In monorepos, never use `<pkg-manager> --filter <pkg> test:run` for a specific file — it initializes ALL environments first.
Run vitest directly from the package directory for targeted runs (typically <1s vs tens of seconds).

## Core Policy

- MUST run tests if API-related code changes
- E2E tests MUST run for UI component/layout changes — **NEVER skip, NO EXCEPTIONS**
- NEVER claim "done" without running tests and showing output
- Don't cover up problems — keep working until fixed

## Test-First Gate (Autopilot/Build)

Builder MUST follow TDD order: (1) write failing tests, (2) confirm failure, (3) implement, (4) verify pass.
Skipping step 1 = BUILD gate fails. Re-dispatch builder to add failing tests first.

## Specification Coverage Check (Test Stage)

Each public function MUST have a test that would fail with an empty implementation.

Red flags requiring additional tests:
- Guard tested against only 1 sibling type → add cross-type matrix
- Output shape not asserted → assert exact structure
- Only valid input tested → add null/undefined/wrong-type cases
- All tests use `toBeTruthy()` → assert exact shape or value

## Tool Roles

| Tool | Role | Purpose |
|------|------|---------|
| **Playwright** | Verdict | Run specs, assertions, produce pass/fail results |
| **agent-browser** | Evidence | Visual verification, screenshots, video recording |

- Use both tools together: Playwright results are the **verdict**, agent-browser outputs are the **evidence**
- Agents are responsible up to leaving artifacts (logs, screenshots, videos) in `$STATE_DIR/`
- Evidence upload and gate-marker posting are performed by the **orchestrator**

## Browser Verification

**Required for:** `.tsx`, `.jsx`, `.css`, `.svg` changes; user-facing bug fixes; API routes triggered by user actions.

**Sequence:** Implement → Browser verify → E2E tests (never skip verify)

**Tools:** `agent-browser` CLI (primary), Chrome for Claude (fallback). Always check connection first.

**Pass conditions** (ALL must be true):
1. Declared test purpose outcome visible on screen
2. Zero error messages on page
3. Server logs clean (no ERROR/WARN for tested flow)
4. Controls returned to ready state

If error suggests alternative → MUST try it. Stop only when feature works or all alternatives exhausted.

## Evidence Capture

> **Pipeline note:** Agents produce evidence files in `$STATE_DIR/evidence/`. The **orchestrator** uploads evidence to GitHub and posts gate markers after each stage passes. BUILD → orchestrator uploads browser-verify screenshots; VERIFY → orchestrator uploads TIA screenshots; /qa → orchestrator uploads scenario recordings. There is no separate EVIDENCE stage.

### Evidence Modes

| Mode | Format | When to use | Storage |
|------|--------|-------------|---------|
| `screenshot` (default) | Multiple `.png` per scenario | Most UI features | `$STATE_DIR/evidence/` |
| `video` | `.webm` per scenario | Complex interactions, animations | `$STATE_DIR/evidence/` |
| `none` | N/A | Non-UI changes | N/A |

All evidence — screenshot and video alike — lives under `$STATE_DIR/evidence/`. The orchestrator's `store_evidence_migrate` + `store_evidence_list_json` scan only that directory (see File Naming Authority below).

### Screenshot Mode (default)

- Capture one screenshot per user action step in the QA scenario
- File naming (logical — pre-migrate): `$STATE_DIR/evidence/s<N>-step<NN>-<description>.png`
- After `store_evidence_migrate` the on-disk name becomes `s<N>-step<NN>-<description>.<hash8>.png` (orchestrator runs migrate before emitting `stage.passed`)
- Example logical name: `s1-step01-settings-page.png` → stored as `s1-step01-settings-page.4c2a11e9.png`
- Use `agent-browser screenshot --path <path>` or Playwright `page.screenshot()`
- Minimum: screenshot count ≥ scenario step count
- See File Naming Authority below for the full hash8 contract.

### Video Mode

- UI E2E: `RECORD_VIDEO=true npx playwright test --project=chromium <file>`
- Save webm files to evidence directory immediately (webm overwritten on next run)
- Use webm directly — GitHub Video Player extension plays webm inline
- `browser.newContext()` tests need explicit `recordVideo` option (doesn't inherit from config)
- **Warm-up before recording (MANDATORY):** Before creating a `recordVideo` context, navigate to the target page in a plain context and `waitForLoadState('networkidle')` first.
  ```typescript
  // 1. warm-up — triggers dev server compilation, no recording
  const warmup = await browser.newPage();
  await warmup.goto(PAGE_URL);
  await warmup.waitForLoadState('networkidle');
  await warmup.close();

  // 2. recording context — page loads instantly
  const ctx = await browser.newContext({ recordVideo: { dir: videoDir } });
  const page = await ctx.newPage();
  await page.goto(PAGE_URL);
  ```

### Evidence PR Comment Context

When calling `upload-evidence`, pass context as parameters — no sidecar files needed:

```bash
# Screenshot mode (/dev)
Skill("upload-evidence", args: "--section '[A] Browser Verify — Phase 1' --description 'Purpose: verify settings page rendering'")

# Video mode (/qa)
Skill("upload-evidence", args: "--pipeline qa --mode video --section 'S1: Chat flow' --description 'Verify new-conversation creation and message send'")
```

`--section` → PR comment section header (`###` heading)
`--description` → blockquote context line (`> ...`)

## File Naming Authority

Single source of truth for evidence file naming. Other docs (`agents/builder.md`, `agents/tester.md`, `rules/orchestration.md`) link here.

Evidence filenames follow the pattern `<logical_name>.<hash8>.<ext>` where `hash8` is the first 8 hex chars of SHA-256(file contents). The hash suffix is inserted between `logical_name` and `ext`.

| Stage | Owner | Logical-name pattern | Full filename example | Location |
|-------|-------|----------------------|------------------------|----------|
| /dev build browser-verify | builder (Build mode) | `browser-verify-<phase>-step<NN>-<desc>` | `browser-verify-phase1-step01-settings.a3f9b2c1.png` | `$STATE_DIR/evidence/` |
| /dev verify TIA | builder (Verify mode) | `tia-<spec>-step<NN>-<desc>` | `tia-auth-step01-login.7e4d2f90.png` | `$STATE_DIR/evidence/` |
| /qa scenario (video) | tester agent | `s<N>-<slug>` | `s1-chat-flow.b8c5a1e2.webm` | `$STATE_DIR/evidence/` |
| /qa scenario (screenshot override) | tester agent | `s<N>-step<NN>-<desc>` | `s1-step01-settings.4c2a11e9.png` | `$STATE_DIR/evidence/` |

**How to write evidence:** source `scripts/store_evidence.sh` and call `store_evidence "$STATE_DIR" "$SOURCE_FILE" "$LOGICAL_NAME"` — it returns the final filename (with hash8 suffix) on stdout and places the file under `$STATE_DIR/evidence/`. The helper is idempotent; repeated calls for the same content are no-ops.

**Enforcement:** `hooks/gate-keeping/pre-bash-pr-gate.sh` guards PR creation in two passes:

1. **Per-event pass** — reads the `evidence` array of each `stage.passed` event and calls `store_evidence_verify` on every filename. The hook re-hashes the file and compares against the embedded `<hash8>` suffix.
2. **Directory pass** — enumerates every file under `$STATE_DIR/evidence/` and re-verifies. This catches writers whose logical names escaped the per-stage glob (prefix drift) — such files would otherwise be invisible to pass 1 but still live on disk as unhashed evidence.

Each filename MUST carry a `<hash8>` suffix (`<logical>.<hash8>.<ext>`, or `<logical>.<hash8>` with no extension). A missing file, a filename without a `<hash8>` suffix, or a hash mismatch blocks PR creation with an actionable error pointing at the offending filename.

## Dev Server

Dev-server lifecycle, URL conventions, and multi-worktree concerns are **project-owned**. Follow the target project's CLAUDE.md for how to start/stop the dev server and obtain the base URL. Global rules do not presume that any project has a dev server.
