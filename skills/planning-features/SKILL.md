---
name: planning-features
description: Planning skill for development implementation and QA scenario plans. Called with --mode dev for implementation roadmaps (used by /plan-dev and /dev) or --mode qa for QA scenario plans (used by /plan-qa and /qa).
---

# Planning Features Skill

## Mode Selection

This skill operates in two modes. Read the `args` value passed by the caller:

- **`--mode dev`** — Development planning. Execute only the [Dev Planning](#dev-planning---mode-dev) section below.
- **`--mode qa`** — QA planning. Execute only the [QA Planning](#qa-planning---mode-qa) section below.

Do not execute both sections. The mode is always specified by the caller.

## Reviewer feedback handling (Ralph loop iterations)

When invoked from the REVIEW Ralph loop in `/plan-qa` or `/dev` (iteration ≥ 2), the orchestrator will:

1. Set `args` to include `--feedback <path-to-feedback-log>` AND/OR
2. Place the previous reviewer's findings file at `$STATE_DIR/${TASK_ID}-{qa,plan}-feedback.log`

If a feedback log exists:

- Read it **before** doing any other planning work.
- Treat every CRITICAL and HIGH finding as a hard requirement to address. The output qa-plan or dev-plan MUST visibly resolve each numbered finding (QC-N / QH-N for qa-plan; H-N / C-N for dev-plan).
- At the bottom of the regenerated plan, add a `## Iteration {N} — Reviewer Feedback Resolution` section listing each finding ID, the change made, and the qa-plan section/line where the change applies.
- Do NOT silently re-emit a similar plan. Re-emission without addressing findings causes Ralph terminator to trigger ("same-findings 3x → HARD STOP").

The reviewer is the audit authority. The skill is the plan author. **Planner ≠ Reviewer** (`rules/orchestration.md` → "Foundational principles"). The skill MUST NOT self-approve, MUST NOT post `gate:qa-plan`/`gate:dev-plan` markers, and MUST NOT publish to GitHub. Posting is the orchestrator's POST stage, gated on REVIEW APPROVED.

## qa-plan: production environment requirement

When `--mode qa`, the skill MUST follow `commands/qa.md` → "Real-environment principle". Concretely:

- Every P1 scenario's `Required state` MUST describe **real services** (URL, account, running process). Mock-only `Required state` is REJECTED by the reviewer (QC-1 in `agents/reviewer.md` → QAPlanReviewMode).
- Acceptable form for production env scenarios:
  - `Required state: Test User logged in. MCP server X reachable at localhost:9001 with widget configured. dol dev server running on http://<branch>.dol.localhost:1355.`
- If the production env is genuinely unavailable, the scenario MUST be marked `mock_only: true` with:
  - `BLOCKED` companion scenario describing the missing infrastructure
  - explicit rationale (1-2 sentences) why mock is the only currently-feasible validation
  - a `gap.opened` event the orchestrator emits with `close_by` deadline

The skill MUST NOT default to mock-only. Default = production env. Mock-only is exception with audit trail.

---

# Dev Planning (`--mode dev`)

# Dev Planning Skill

> **ultrathink** — Extended thinking is REQUIRED for this skill. Every invocation of dev-plan MUST trigger deep reasoning mode. Do not proceed with shallow analysis.

Elite specialist in transforming user requirements into comprehensive, production-ready implementation roadmaps. Your expertise lies in deep analytical thinking, architectural design, and creating crystal-clear divide-and-conquer plans.

## Modes

- **Interactive mode** (default): user is present in the conversation. Use `AskUserQuestionTool` to interview and refine requirements iteratively.
- **Headless mode**: no user interaction is possible — triggered from an automated pipeline (e.g., dev pipeline) with a GitHub issue as the sole input. Skip all interview steps; derive requirements from the issue body. Document all assumptions in Section 8 (Open Questions).

## Step 1: Gather & Strengthen Requirements

### Interactive Mode (default)

Use AskUserQuestionTool to interview user in detail about:

- Implicit and explicit requirements
- Use cases and user workflows
- Features and constraints
- Technical implementation concerns
- UI & UX considerations
- Tradeoffs and priorities
- Performance requirements and constraints
- Accessibility requirements
- Target browsers/environments

Make sure questions are not obvious — be in-depth. Continue interviewing until complete.

### Requirement Sufficiency Check (Interactive Mode only)

Before proceeding to Step 2, evaluate whether the gathered requirements are sufficient:

- **Use cases**: Are there at least 2-3 concrete user scenarios? If not, propose additional use cases and ask the user to confirm or refine.
- **Edge cases**: Are error scenarios, empty states, and boundary conditions covered? If not, ask about them.
- **Scope clarity**: Is it clear what is in scope and out of scope? If ambiguous, ask the user to draw the line.
- **Acceptance criteria**: Can you define measurable success criteria? If not, interview further until you can.

If requirements are insufficient, do NOT proceed. Instead:
1. Summarize what you have so far
2. Identify specific gaps (e.g., "No error handling use case", "Missing mobile scenario")
3. Ask targeted questions to fill each gap
4. Repeat until requirements are solid enough for a complete plan

## Step 2: Analyze

1. If GitHub issue: fetch and analyze issue details, comments, and linked references
   - If the issue was previously triaged (has `## Goals`, `## Constraints`, and `**Related Files:**` sections): **use the triage body as the requirements baseline**. Extract Goals, Constraints, and Related Files directly — do NOT re-investigate files already catalogued by triage. Build on those findings with deeper analysis relevant to implementation design.
2. If prompt: analyze the requirements directly
3. Review project structure, codebase, and existing documentation
4. Read any existing SPEC.md or requirements files if provided
5. Identify current features and limitations
6. Extract implicit user needs from code patterns and comments
7. Highlight gaps between current state and requirements
8. Identify existing libraries, frameworks, and patterns already in use
9. Assess impact on existing codebase and potential breaking changes

### Deep Analysis

> **ultrathink** — Before forming any conclusion, exhaust all angles. Poor planning compounds through every downstream stage.

- Think deeply and comprehensively before proposing solutions
- Consider multiple implementation approaches from different angles
- Evaluate trade-offs between complexity, maintainability, performance, and user experience
- Identify the most elegant, intuitive, and efficient implementation approach — balance simplicity with robustness
- Think beyond the user's initial proposal to identify potentially superior solutions
- If you discover a better approach than what the user suggested, present it alongside their original idea with clear reasoning

### Parallel Research (when complexity warrants)

When the feature involves non-trivial technical decisions, investigate multiple angles **in parallel** using the Task tool. Launch concurrent research agents to explore different dimensions simultaneously:

| Angle | What to investigate |
|-------|-------------------|
| **Existing patterns** | How does the current codebase solve similar problems? |
| **Library/API options** | What libraries, frameworks, or platform APIs are available? |
| **Prior art** | How do other projects or the ecosystem solve this? |
| **Constraints** | What are performance, security, or compatibility limitations? |

Rules:
- Launch 2-4 parallel research agents depending on complexity
- Each agent explores one angle independently and returns findings
- Aggregate results before forming the Technical Approach
- Not every angle is needed every time — select the most relevant ones for the task

## Step 3: Create Plan (Divide & Conquer)

Generate a structured plan following the **Required Report Structure** below.

### Collaborative Refinement

- Present your analysis and recommendations to the user in a clear, structured format
- Actively seek and incorporate user feedback
- Iterate on the plan until it perfectly aligns with the user's vision and constraints
- Always confirm with the user before finalizing and saving the plan

## Required Report Structure

The output plan MUST contain ALL of the following sections:

### 1. Overview
- High-level summary of the feature (2-3 paragraphs)
- What problem it solves and why it matters
- Scope boundaries (what is and is NOT included)

### 1a. Visual Reference (REQUIRED for UI work)

**When required**: if ANY implementation phase modifies `.tsx`, `.jsx`, `.css`, or `.svg` files, OR adds/changes a user-observable surface (new dialog, new page, new component, new layout, changed routing, changed empty state, etc.), this section MUST be present.

**When omitted**: pure non-UI work (API-only, type refactor, build config, server logic with no user-visible change). When omitting, replace the section body with one line: `Not applicable — non-UI change.` Do not delete the heading.

**What to include**: For each user-observable state of the feature, an ASCII/ANSI mockup OR a Mermaid diagram showing layout and key elements. Cover at minimum:

- The **primary success state** (the happy-path "this is what it looks like when it works")
- The **empty state** (when no data / no rows / first time)
- Any **mode toggles or alternate views** (edit mode, paste mode, drawer open, etc.)
- The **error or confirmation state** (validation message, AlertDialog body, destructive confirm)

Each mockup MUST be in a fenced code block (```` ``` ````) so GitHub renders it monospaced.

Each mockup MUST include a one-line `Notes:` directly below it pointing out non-obvious behavior (e.g., "active tab uses underline matching component X", "lock icon uses `text-amber-600 dark:text-amber-500`", "12 fixed dots — never derived from real value length").

**Why this matters**: builder agents read the plan comment as the single source of truth. Without a visual reference, builders synthesize the UI from prose — which produces drift from the user's actual intent. A 30-line ASCII mockup compresses 300 lines of "the button should be on the right, slightly smaller than the input, with…" into something the reader's eye parses instantly. Drift is also reviewer's #1 source of "this doesn't match what I asked for" findings; visual mockups in the plan make the contract explicit.

**Format guidance**:
- Use box-drawing chars (`┌─┐│└─┘╔═╗║╚═╝`) for outlines, not markdown tables (markdown tables can't represent layout).
- Use Unicode chips/dots/icons (`🔒 👁 ✎ 🗑 ⌜⌟ ◉ ◯ ✕ ▶`) sparingly — they communicate fast but must render consistently in monospace.
- One mockup per user-observable state. Don't combine 3 states into one diagram; the reader has to mentally diff them.
- Mockups are **specifications, not suggestions**. Builder deviations require explicit justification in the PR description.

### 1b. User Experience — what ships (REQUIRED)

Heading always present. §1a covers visual layout for UI work; §1b covers observable UX for CLI/SDK/MCP-host/HTTP/library surfaces so the builder targets the right shipped behavior and the reviewer can audit against it.

**MUST**:
- Cover EVERY user-facing access mode this PR creates or changes (one subsection each). Skip modes that don't apply.
- Show what the user **types** and what they **see** in fenced blocks. No prose paraphrase.
- Include at least one error-path example for each mode that can fail.
- Include a Before vs. After block (≤ 6 lines per side) showing what now succeeds.
- List v1 carve-outs as a final bullet list (cross-link to §8 OQs for deferrals).

**MUST NOT**:
- Replace transcripts with prose ("the CLI now supports X").
- Defer to §7 Code Examples (§7 = how the lib composes; §1b = what the user encounters).
- Invent UX not agreed in the issue. Every transcript in §1b is a contract the impl must match.

**Pure UI PR exception**: §1b body MAY be `See §1a — no CLI/SDK/MCP-host surface changed.` (heading still present).

### 2. Technical Approach
- **Framework/Library strategy**: What tools will be used and why
- **Architecture decisions**: How components/modules are organized
- **Core design principles**: Guiding rules for implementation (e.g., easing standards, duration scales, naming conventions)
- **Key patterns**: Reusable patterns that will be established
- **Alternatives considered**: At least one alternative approach and why it was rejected
- **Tradeoffs**: Explain tradeoffs made (performance vs. simplicity, etc.)
- **Existing patterns**: Reference project patterns that influenced the decision

### 3. Implementation Plan (Phases)
- **MUST split into multiple phases using a divide-and-conquer approach**
- Mark parallelizable tasks with `[PARALLEL]` tag
- Each phase MUST follow the "Phase Rules" below

### 4. Dependencies
- **Required packages**: Name, version, purpose (note if already installed)
- **Configuration files to update**: List every config file that needs changes
- **New files to create**: List with path and purpose
- **Existing files to modify**: List with description of changes

### 5. Success Criteria
- **Performance metrics**: Measurable targets (e.g., 60 FPS, bundle size < X KB)
- **User experience**: What the user should see/feel
- **Accessibility**: WCAG compliance, screen reader support, reduced motion
- **Developer experience**: API quality, documentation, maintainability

### 6. Implementation Notes
- **Priority order**: High / Medium / Low with justification
- **Testing Strategy for Dev** — Behavior coverage mapping and test design: enumerates every implemented behavior, ensures each maps to at least one test case, defines E2E spec file structure and evidence artifact inventory (audience: developers and qa agents)
- **Rollout strategy**: Feature flags, A/B testing, gradual rollout if applicable

**E2E quality rules** — the following patterns produce tests that always pass regardless of whether the feature works. They are forbidden:

| Anti-pattern | Why it fails | Required replacement |
|---|---|---|
| `if (visible) { assert } else { test.skip() }` | Skips when condition isn't met → always PASS | Fix State Setup so the condition is reliably true |
| `await waitForTimeout(N)` for time-sensitive state | N is always wrong on some machines | `waitForFunction`, `waitForResponse`, or a Mock that gives explicit control |
| "button appears" as the entire assertion | Doesn't verify the animation, only DOM presence | Specify what property changes and how to observe it (e.g., `getComputedStyle().opacity` during transition, `toBeVisible` after `waitForFunction(() => opacity > 0)`) |
| Real API call when behavior is gated on timing | Non-deterministic: streaming may end before scroll | Mock with controlled `chunkDelay` so the timing window is wide and reliable |

### 7. Code Examples (when applicable)
- Include 2-3 concrete code examples showing the intended API/usage
- Show both simple and complex use cases
- Demonstrate how the feature integrates with existing code

### 8. Open Questions & Assumptions (required in headless mode)

This section captures all decisions made without user input. Each entry MUST include:

- **Question**: What was unclear or ambiguous
- **Assumption**: The default decision made to proceed
- **Rationale**: Why this default was chosen
- **Impact**: What changes if the user decides differently (LOW / MEDIUM / HIGH)
- **Alternatives**: Other valid options the user could choose instead

Example format:
```markdown
#### OQ-1: Authentication method
- **Question**: Should we use JWT or session-based auth?
- **Assumption**: JWT (stateless)
- **Rationale**: Aligns with existing API patterns in `src/middleware/auth.ts`
- **Impact**: HIGH — switching to sessions requires adding Redis dependency
- **Alternatives**: Session-based auth (server-side state, requires session store)

#### OQ-2: Mobile breakpoint
- **Question**: What is the mobile breakpoint?
- **Assumption**: 768px
- **Rationale**: Matches existing Tailwind `md` breakpoint used in project
- **Impact**: LOW — easily adjustable in CSS
- **Alternatives**: 640px (sm), 1024px (lg)
```

In interactive mode, this section may be omitted if all questions were resolved during the interview.

## Phase Rules

### Project-Level Testing & Planning Rules

Before generating implementation phases, check the project for testing and planning rules:

1. Read the project CLAUDE.md for references to testing rules (e.g., `rules/testing-guide.md`)
2. If found, read and apply those project-specific settings to customize: dev server startup/URL resolution, test runner commands, evidence format, test paths
3. These project rules override the generic defaults in the commands below (e.g., URL resolution mechanism, evidence format preferences) — project CLAUDE.md is authoritative

**MUST split the plan into multiple phases using a divide-and-conquer approach.**

Each phase MUST:

1. Be independently **testable** — verifiable with tests at the end of the phase
2. Be **rollbackable** — revertable without breaking other phases (each phase = separate commit(s))
3. Have a clear **completion criteria**

Each implementation phase's steps MUST follow this order:

1. **Implement** — Write the actual code
2. **[A] Browser verify during development (UI changes only)** — Interactive manual verification in a real browser. Purpose: confirm the UI renders and behaves correctly as a fast visual feedback loop. Use **`agent-browser` CLI** (primary) or Chrome for Claude (fallback).
   - Start the dev server and resolve the base URL using whatever mechanism the project's CLAUDE.md declares (projects may wrap this in a local script, a package.json command, or a Makefile target — there is no global convention). Never hardcode URLs or assume a specific script name. Pass the resolved URL to `agent-browser open "$DEV_URL/<path>"`.
   - **WARM-UP before recording**: `agent-browser snapshot` (waits for dev server lazy page compilation to finish — avoids recording a long loading screen). If the feature requires pre-existing state (e.g., messages already in chat), set up that state NOW, before `record start`.
   - `agent-browser record start <feature>-<flow>.webm` ← only after warm-up completes
   - `agent-browser snapshot -i` → inspect interactive elements (also paces the recording so each state change is visible to reviewers)
   - Interact with changed UI; `agent-browser screenshot` before/after state change
   - `agent-browser snapshot -i` again after interaction (re-snapshot required — DOM refs change; also provides pacing)
   - `agent-browser record stop` → use the .webm directly (no conversion needed)
   - `agent-browser close`
   - **Verification failure rule**: If the feature does not work correctly, **stop** — return to the Implement step, fix, and re-verify. Do NOT advance to the next phase until verification passes.
   - **This step is MANDATORY for any change touching `.tsx`, `.jsx`, `.css`, or `.svg` files**
   - **Also MANDATORY for bug fixes and API changes that affect user-facing flows** (e.g., fixing an API route that a user action triggers — the file may be `.ts` but the user impact requires browser verification)
   - **Apply the Browser Test Completion Criteria from `rules/testing.md`** — all conditions must be satisfied before advancing
   - For non-UI changes that do NOT affect user flows, skip this step and note "non-UI: skip browser verify" in the phase
3. **Commit** — Create a commit for this phase

> **Tests are NOT written per implementation phase.** All unit tests, E2E specs, and the full E2E run with evidence capture belong in the **Final Testing Phase** (see below), after all implementation phases are complete.

### Final Testing Phase

The last phase in every plan MUST be a dedicated testing phase. It runs after all implementation phases are committed.

Steps:

1. **Write unit tests** — Cover all new/changed functions (schema validation, persistence transforms, UI component behavior). Save output to `$STATE_DIR/<feature>-unit.txt`.
2. **Write E2E specs** — Use the **Scenario-First → Behavior Inventory → Persona Brainstorm → Unified List** protocol.

   ### Step 2a-pre: Scenario-First Anchoring (MANDATORY — before Behavior Inventory)

   Before listing behaviors, derive **user-facing test scenarios from the plan's Section 5 Success Criteria**. Each scenario must represent a complete user journey that a real person would perform — not a code path. A test that doesn't map to something a human would actually do is testing the wrong thing.

   **OUTPUT REQUIREMENT:** Write the scenarios as a `## E2E Scenarios` section inside the plan file at `$STATE_DIR/${TASK_ID}-plan.md` FIRST, BEFORE writing any test code. The plan file is later posted as a GitHub issue comment by the orchestrator (`/plan-dev` POST stage) with the `<!-- gate:dev-plan:${TASK_ID} -->` marker — that posted comment is the canonical plan document. The GitHub issue body is NOT modified by this skill. This is a hard gate — test writing MUST NOT begin until the plan file contains a non-empty `## E2E Scenarios` section.

   **How to derive scenarios from Success Criteria:**
   1. Read every item in Section 5 Success Criteria
   2. Group criteria that a user would verify in a single sitting into one scenario
   3. Write the scenario from the user's perspective (what they do, what they see)
   4. Each scenario's success conditions MUST map back to one or more Success Criteria items

   For each scenario:
   - **Scenario**: short name describing the user goal
   - **User Action**: what the user does (one sentence)
   - **Detailed Steps**: numbered steps a human tester would follow
   - **Success Conditions**: observable outcomes that prove the feature works (bullet list, traceable to Success Criteria)
   - **Evidence**: webm filename that will capture this scenario (`pr{N}-s{N}-<slug>.webm`)

   For each scenario, also document the **State Setup**: *how to reliably put the system into the required state for an automated test.*

   If the state is **time-sensitive** — streaming, animation mid-flight, pending async — you MUST specify which Mock or Fixture creates it deterministically. `waitForTimeout(N)` is NOT acceptable for time-sensitive state.

   **Example `## E2E Scenarios` section (written into the plan file; posted to GitHub as the plan comment by the orchestrator):**
   ```markdown
   ## E2E Scenarios

   > For QA and manual testers. Each scenario is a step-by-step procedure derived from Section 5 Success Criteria, focused on "what the user does and what they should see." All scenarios must pass for the feature to ship.

   ### S1: First entry into chat history
   **User Action:** Visit the /history page for the first time
   **Detailed Steps:**
   1. Navigate to /history in the browser
   2. Confirm the page-load completion timing
   3. DevTools → Network tab → verify API calls
   4. View HTML source via view-source

   **Success Conditions:**
   - Loading spinner never appears ← Success Criteria: "First Contentful Paint"
   - HTML source contains actual chat titles ← Success Criteria: "view-source /history"
   - No `/api/chats` XHR call on mount ← Success Criteria: "Network XHR on load"
   - No JS errors

   **State Setup:** DB contains at least 1 chat record for the test user
   **Evidence:** `pr{N}-s1-initial-render.webm`

   ### S2: Chat search and reset
   **User Action:** Type a keyword into the search box, verify results, then clear the keyword
   **Detailed Steps:**
   1. Visit /history and confirm the full list
   2. Type a specific keyword into the search box
   3. Verify the filtered result
   4. Clear the entire search keyword
   5. Verify the full list is restored

   **Success Conditions:**
   - Only matching items are shown immediately on keyword input
   - Empty State is shown when there are no matches
   - Full list is restored immediately when the keyword is cleared
   - No API re-fetch during search (client-side filter)

   **State Setup:** DB contains at least 3 chat records with distinct titles
   **Evidence:** `pr{N}-s2-search.webm`
   ```

   These scenarios — not the taxonomy groups — become the primary structure of the test suite.

   ### Step 2a: Behavior Inventory (MANDATORY — before any brainstorming)

   For EACH implementation phase, enumerate EVERY behavioral change. For each behavior, capture three things:

   | Behavior | State Setup | Time-sensitive? |
   |----------|------------|----------------|
   | What the **user sees or can do** (not what the code does internally) | How to put the app in the right state for an automated test | ⏱ if streaming/animation/async |

   > **Time-sensitive behaviors (⏱) require a Mock/Fixture** — `waitForTimeout` is not a substitute. Identify which mock achieves deterministic control before writing the test case.

   This produces the **coverage matrix** — every row must trace to at least one test case.

   > **Minimum coverage rule:** `test_count_for_phase ≥ behavior_count_for_phase`. Count explicitly and match. A phase introducing 8 behaviors with 0 test cases is a hard failure.

   ### Step 2b: Persona Brainstorm (generate test ideas from 3 angles)

   Apply each persona mindset to the behavior inventory and generate test case ideas. Personas are the *personality of the person extracting tests* — not user archetypes, not file categories.

   - **Meticulous** — Checks every detail one by one. Asks: "Is this specific element visible? Is its bounding box correct? Does it persist after reload?" Generates: individual assertion-level test cases.
   - **Average** — Follows the most common path. Asks: "What does a normal user do first, second, third?" Generates: end-to-end flow test cases spanning multiple behaviors.
   - **Loose** — Pushes edges and acts unexpectedly. Asks: "What if I resize mid-session? Go directly to a deep URL? Click rapidly?" Generates: boundary, stress, and edge-case test cases.

   Run all three mindsets over the behavior inventory. Capture every idea.

   ### Step 2c: Merge, Deduplicate, and Classify

   1. Combine all ideas from all three persona passes into one list.
   2. Remove duplicates — keep the most specific formulation of each case.
   3. Classify each test case by type:
      - **Assertion** — verifies a specific element, value, or state at a point in time
      - **Flow** — exercises a multi-step user journey end-to-end
      - **Boundary** — targets exact threshold values, stress, or unexpected sequences

   ### Step 2d: Write spec files based on dev test-plan scenarios (one file per scenario)

   Read `$STATE_DIR/<task-name>-dev.md`. For each scenario (S1, S2, S3, …), create one spec file:

   - **`<feature>-s<N>-<slug>.spec.ts`** — one file per scenario, named after the scenario slug from the test plan.
     - Example: `chat-s1-initial-render.spec.ts`, `chat-s2-search.spec.ts`
   - Each spec file contains one `describe` block named after the scenario.
   - Test names follow Actor-Based convention: `User can [action]` / `User cannot [action] when [condition]`.
   - Each test case maps to one or more success conditions from the scenario.
   - Assertion / Flow / Boundary classification from Step 2c is used to **organize tests within** the spec file — NOT to split into separate files.

   Each scenario spec is recorded separately for video evidence (one webm per scenario). The per-scenario split exists so evidence maps directly to user-verifiable outcomes.
3. **[B] Full E2E run with automated evidence capture** — Run each scenario spec file separately and record video evidence for the PR audit trail. Each scenario spec produces a separate webm.
   - **HARD RULE: The feature is NOT complete until ALL tests pass. No exceptions.**
   - **Run each scenario spec file separately** with `RECORD_VIDEO=true`:
     - `RECORD_VIDEO=true npx playwright test <feature>-s1-<slug>.spec.ts --project=chromium`
     - `RECORD_VIDEO=true npx playwright test <feature>-s2-<slug>.spec.ts --project=chromium`
     - (repeat for each scenario)
   - **Move `.webm` files to evidence directory** — webm files are overwritten on the next run:
     - `mv <file>.webm $STATE_DIR/evidence/s1-<slug>.webm`
     - `mv <file>.webm $STATE_DIR/evidence/s2-<slug>.webm`
   - **Upload scenario evidence** via `Skill(skill: "upload-evidence")` — do NOT use raw `gh release upload`
   - **Post evidence table in PR comment** listing all [A] videos (from implementation phases) and [B] videos (per scenario) with columns: Evidence, Scenario, File
4. **Commit** — Commit the test files

### Phase Format

Each phase MUST use this checkbox format for GitHub tracking:

```markdown
### Phase 1: [Phase Name]

- [ ] Implement [feature]
  - [ ] [Sub-task 1 with specific detail]
  - [ ] [Sub-task 2 with specific detail]
- [ ] **[A] Browser verify during development** — `agent-browser` (primary) or Chrome for Claude (fallback)
  > Purpose: interactive manual check that the UI renders correctly. Not a test runner.
  > **Verification failure rule**: if the feature does not work correctly, return to Implement, fix, and re-verify. Do NOT advance to the next phase until verification passes.
  - [ ] Start the dev server using the mechanism declared in the target project's CLAUDE.md (if not already running)
  - [ ] Resolve `DEV_URL` via the project's declared mechanism, then `agent-browser open "$DEV_URL/<path>"`
  - [ ] **Warm-up**: `agent-browser snapshot` → wait for page to fully load (dev server compiles lazily; recording before this produces a long loading-screen video)
  - [ ] Set up required pre-existing state if needed (e.g., navigate to create a chat), BEFORE starting recording
  - [ ] `agent-browser record start [feature]-[flow].webm` ← start only after warm-up
  - [ ] `agent-browser snapshot -i` → inspect interactive elements (also paces recording for reviewers)
  - [ ] Interact with changed UI; screenshot before/after state change; confirm success condition: [specific visual criteria]
  - [ ] `agent-browser snapshot -i` after interaction (re-snapshot required — DOM refs change; also provides pacing)
  - [ ] `agent-browser record stop` → save .webm directly to `$STATE_DIR/evidence/` (no conversion needed)
  - [ ] `agent-browser close`
- [ ] Commit

### Phase 2: [Phase Name] [PARALLEL]

Parallel phases split independent sub-tasks that can be implemented concurrently. Each `[PARALLEL]` block is assigned to a separate agent — they must not modify the same files.

- [ ] [PARALLEL] Implement [sub-feature A]
  - [ ] [Specific detail]
- [ ] [PARALLEL] Implement [sub-feature B]
  - [ ] [Specific detail]
- [ ] **[A] Browser verify during development** — same `agent-browser` sequence as Phase 1
- [ ] Commit

### Phase N-1: Testing (after all implementation phases)

- [ ] Write unit tests → save output to `$STATE_DIR/[feature]-unit.txt`
  - [ ] [Test scenario 1]
  - [ ] [Test scenario 2]
  - [ ] Run: `cd <app-dir> && npx vitest run tests/unit/[feature]/ 2>&1 | tee $STATE_DIR/[feature]-unit.txt`
- [ ] Write E2E specs — **Behavior Inventory → Persona Brainstorm → Unified List**
  - [ ] **Step 1: Behavior Inventory** — enumerate every behavioral change from all implementation phases
    - [ ] List all new UI elements and their render conditions
    - [ ] List all new user interactions and expected outcomes
    - [ ] List all regression surfaces (existing behaviors that must not break)
    - [ ] List all boundary conditions (exact threshold values, empty states, error states)
    - [ ] Deduplicate across phases — keep each unique behavior once
  - [ ] **Step 2: Persona Brainstorm** — apply each mindset to the inventory to generate test ideas
    - [ ] Meticulous pass: "Is this exact element rendered? Are its dimensions correct? Does it persist after reload?" → assertion-level ideas
    - [ ] Average pass: "What is the most natural sequence of actions?" → flow-level ideas
    - [ ] Loose pass: "What exact boundary value breaks this? What if I act out of order?" → boundary/stress ideas
    - [ ] Merge all ideas → remove duplicates → classify each as: Assertion / Flow / Boundary
  - [ ] **Step 3: Write spec files based on dev test-plan scenarios (one file per scenario)**
    - [ ] Read `$STATE_DIR/<task-name>-dev.md` — use scenario list as the authoritative spec structure
    - [ ] `tests/e2e/[feature]/[feature]-s1-<slug>.spec.ts` — all test cases for Scenario 1
      - [ ] [Test cases derived from S1 success conditions — assertion/flow/boundary cases organized within]
    - [ ] `tests/e2e/[feature]/[feature]-s2-<slug>.spec.ts` — all test cases for Scenario 2
      - [ ] [Test cases derived from S2 success conditions]
    - [ ] (repeat for each scenario in the test plan)
- [ ] Commit

```

## Plan Completeness Check

Before publishing, verify ALL of the following items. If any item is missing, go back and add it.

- [ ] Technical Approach includes at least one alternative considered and rejected with reason
- [ ] Code example showing primary API usage (section 7)
- [ ] Success criteria with measurable targets (section 5)
- [ ] Open questions recorded (headless) or resolved (interactive) (section 8)
- [ ] **Visual Reference present (section 1a) — REQUIRED for UI work**: if any phase modifies `.tsx/.jsx/.css/.svg` files or adds/changes a user-observable surface, section 1a MUST contain at least one ASCII/ANSI mockup or Mermaid diagram per user-observable state (primary success, empty, alternate modes, error/confirm). Each mockup in a fenced code block with a `Notes:` line. Pure non-UI changes may set the section body to `Not applicable — non-UI change.` but the heading MUST remain.
- [ ] **User Experience present (section 1b) — REQUIRED always**: every user-facing access mode (CLI / SDK embed / MCP host / HTTP / config) created or changed has a fenced-block transcript showing what the user types AND what they see (incl. ≥1 error-path), plus a Before vs. After block (≤ 6 lines per side) and a v1 carve-outs list. No prose paraphrase substitutes for transcripts.
- [ ] **Every phase that modifies `.tsx`, `.jsx`, `.css`, `.svg` files OR affects a user-facing flow (bug fixes, API route changes) has a browser verify step** — per Phase Rules and `rules/testing.md` Browser Test Completion Criteria. If a phase only changes non-UI files with no user flow impact, explicitly note "non-UI: skip browser verify".
- [ ] **Every UI phase has step [A]: Browser verify during development** — `agent-browser` CLI (primary) with `record start/stop` (webm saved directly, no conversion needed); Chrome for Claude (`mcp__claude-in-chrome__*`) is the fallback. "Any tool acceptable" is NOT sufficient; a concrete tool must be specified. This is an interactive manual check, not a test runner.
  - **Verification failure rule**: If the feature does not work correctly in the browser, the phase is NOT complete — return to Implement, fix, and re-verify. Do NOT advance to the next phase until verification passes.
- [ ] **Final testing phase has step [B]: E2E test run with automated evidence capture** — `RECORD_VIDEO=true`, `.webm` files uploaded via `Skill(skill: "upload-evidence")` (NOT raw `gh release upload`). One spec file and one webm per scenario — scenario count must match dev test-plan. [B] runs ONCE in the final Testing phase after all implementation phases are committed — NOT repeated in each phase.
- [ ] **Scenario-First Anchoring completed** — Step 2a-pre scenarios are written as Given/When/Then, and every time-sensitive behavior (⏱) has a Mock/Fixture specified in State Setup. No time-sensitive behavior uses `waitForTimeout` as its setup method. No test case uses `if (condition) { assert } else { test.skip() }`.
- [ ] **Testing strategy in Implementation Notes follows the Scenario-First → Behavior Inventory → Persona Brainstorm → Unified List protocol.** A behavior inventory table (one row per implemented behavior, with State Setup and test-case reference) must be present. Spec files must be organized by dev test-plan scenario (one file per scenario: `<feature>-s<N>-<slug>.spec.ts`), not by test type. Total test count must be ≥ total behavior count across all implementation phases. An evidence artifacts table listing all [A] and [B] webm videos plus the unit test log file MUST be included.
- [ ] **`## E2E Scenarios` section written to plan file** — `$STATE_DIR/${TASK_ID}-plan.md` contains a `## E2E Scenarios` section with step-by-step verification procedures before any test code is written. This is the Scenario-First artifact gate. The orchestrator posts the plan file as a GitHub issue comment with the `<!-- gate:dev-plan:${TASK_ID} -->` marker; the GitHub issue body is NOT modified. The local `$STATE_DIR/<name>-dev.md` is derived from the plan file during dev-plan.
- [ ] **Plan metadata written to `$STATE_DIR/plan.md`** — Work dir computed from git context (REPO_ROOT, ISSUE, branch slug). The plan document contains the `video-required:` and (if true) `video-flows:` fields using the type-prefix convention (`browser-verify-*` for [A], `e2e-*` for [B]). The plan is posted to GitHub as a PR/issue comment with the `<!-- gate:dev-plan:${TASK_ID} -->` marker — NOT written into the issue body.

## Step 3.3: Epic Size Detection (MANDATORY — runs after Step 3, before Self-Validation)

After generating the plan, evaluate whether the scope exceeds what can be safely implemented in a single session.

### Trigger Criteria

Apply the **Large Project Protocol** if ANY of the following are true:

- Estimated total LOC across all implementation phases > **2,000**
- Number of implementation phases (excluding the Final Testing Phase) > **2**

To estimate LOC: for each implementation phase, sum the estimated lines added/modified across all listed files. When in doubt, err on the side of declaring Epic — it is always safer to decompose than to timeout mid-session.

### When NOT triggered (normal flow)

If both criteria are below threshold: continue to Step 3.5 (Self-Validation) as normal.

---

### When triggered: Epic Decomposition

**Do NOT write a detailed multi-phase implementation plan to the parent issue.** Instead:

#### 3.3.1 — Create dev branch and declare the parent issue as an Epic

**Create the Epic dev branch** so all sub-issue PRs target it instead of main:

```bash
# Derive dev branch name from issue number and scope
# Format: dev/<number>-<scope-slug> (max 40 chars)
DEV_BRANCH="dev/<number>-<scope-slug>"

_BASE=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' | grep . || echo "main")
git fetch origin "$_BASE" && git branch -f "$_BASE" "origin/$_BASE"
git checkout -b "$DEV_BRANCH" "$_BASE"
git push -u origin "$DEV_BRANCH"
```

> **Why a dev branch?** Epic sub-issues are sequential — Layer 1 depends on Layer 0's changes. Without a dev branch, each sub-issue PR would target main, and Layer 1 couldn't see Layer 0's code until it's merged to main. The dev branch collects all sub-issue PRs so later layers can branch from it and see prior work. The final merge to main happens once all sub-issues are complete.

**Do NOT modify the parent issue body or labels.** The Epic identity is conveyed via a posted comment carrying the `<!-- gate:epic-decomposition:<number> -->` marker. The user's original issue body remains untouched.

The Epic comment is posted in step 3.3.3 (after sub-issues are created so they can be linked from the same comment).

#### 3.3.2 — Decompose into Epic slices

Split the work into sub-issues following this order:

1. **Infrastructure** — DB schema, API routes, shared types, auth changes
2. **Core Logic** — Non-UI business logic, data transforms, server actions
3. **UI / Presentation** — React components, layouts, styling
4. **Verification** — E2E tests, integration tests, migration validation

Rules:
- Each sub-issue MUST be ≤ 2,000 LOC and ≤ 2 implementation phases
- Each sub-issue must be independently mergeable without breaking others
- Sub-issues that depend on another sub-issue's output MUST be in a later layer

For each sub-issue, create it with a scoped plan:

```bash
gh issue create \
  --title "<imperative description> [Epic #<parent>]" \
  --body "<scoped 8-section plan for this slice only>"
```

The sub-issue body MUST be a complete, self-contained plan (all 8 sections). Builder agents will read it without the parent issue for context. Title prefix conventions (e.g., `feat(scope):`) and labels are user-local — do NOT apply them in this skill. The `[Epic #<parent>]` suffix is the cross-link signal that this is part of the parent epic.

#### 3.3.3 — Post Epic decomposition comment with sub-issue links

After creating all sub-issues, post a single comment to the parent issue. The comment **explicitly identifies the issue as an Epic** and **links every sub-issue** so the relationship is discoverable from the parent without modifying the body:

```bash
gh issue comment <parent-number> --body "$(cat <<'EOF'
## 🗂 This issue is an Epic

This issue tracks an Epic decomposed into sequential sub-issues. The Epic dev branch
collects all sub-issue PRs; the final PR merges the dev branch back to the default branch.

### Dev branch
`dev/<number>-<scope-slug>` — all sub-issue PRs target this branch.
Final merge: `dev/<number>-<scope-slug>` → default branch.

### Sub-issues (linked)

- [ ] #<N1> — Infrastructure: <title>
- [ ] #<N2> — Core Logic: <title>  (depends on #<N1>)
- [ ] #<N3> — UI: <title>  (depends on #<N2>)
- [ ] #<N4> — Verification: <title>  (depends on #<N3>)

### Why this is an Epic
- Estimated LOC: ~N (threshold: 2,000)
- Phases: N (threshold: 2)

### Execution order
Infrastructure → Core Logic → UI → Verification.
Each sub-issue PR merges into the dev branch. After all sub-issues complete, the
final PR (dev branch → default branch) is opened.

<!-- gate:epic-decomposition:<parent-number> -->
EOF
)"
```

**Why this comment carries the Epic identity:**
- The opening line ("This issue is an Epic") states it explicitly — readers don't need to infer from a label.
- The "Sub-issues (linked)" list uses `#N` references — GitHub renders these as live links and adds backlinks on each sub-issue, so the parent ↔ sub-issue relationship is bidirectional and discoverable from either side.
- The `gate:epic-decomposition` marker lets `/epic` and other tooling locate the canonical Epic comment without scanning the body.
- Re-running the skill posts a new comment; the latest one carrying the marker supersedes prior ones.

#### 3.3.4 — Output layer structure

Print the layer structure for use with `/epic`:

```
Epic decomposition complete.

Epic branch: epic/<number>-<scope-slug>

Layer 0 (no dependencies):
  - #<N1> Infrastructure

Layer 1 (depends on Layer 0):
  - #<N2> Core Logic

Layer 2 (depends on Layer 1):
  - #<N3> UI

Layer 3 (depends on Layer 2):
  - #<N4> Verification

All sub-issue PRs target epic/<number>-<scope-slug>.
After all layers complete: create final PR epic/<number>-<scope-slug> → main.

Next step: run /epic to dispatch sub-issues
```

#### 3.3.5 — Stop

After Epic decomposition, **do NOT proceed to Step 3.5 or Step 4 for the parent issue**. The parent issue now contains only the Epic overview. Each sub-issue is a complete plan ready for execution.

Report to the user:

```
Issue #<N> has been declared an Epic.
Created <K> sub-issues: #<N1>, #<N2>, #<N3>, #<N4>
Epic branch: epic/<number>-<scope-slug> (pushed to origin)

The parent issue is now a tracking Epic. Each sub-issue contains a
complete implementation plan. Sub-issue PRs target the epic branch.

To execute:
  1. Run /epic to dispatch all sub-issues (layer by layer, with QA)
  2. /epic handles merge monitoring, QA, and final PR automatically
```

---

## Step 3.5: Self-Validation (MANDATORY — runs between Step 3 and Step 4)

The Plan Completeness Check above is a passive checklist. Without active enforcement, it is skipped due to instruction dilution (primary task of writing the plan dominates attention).

**This step enforces the checklist programmatically before publishing.**

### Procedure

After generating the plan in Step 3 and BEFORE publishing in Step 4, the skill MUST:

1. **Scan the generated plan text** against each Completeness Check item:

| # | Check | How to verify |
|---|-------|---------------|
| 1 | Alternative considered | Plan contains "Alternative" or "Rejected" in Section 2 |
| 2 | Code example | Section 7 contains a code block |
| 3 | Measurable success criteria | Section 5 contains numeric targets or specific criteria |
| 4 | Open questions | Section 8 exists and is non-empty (headless) or resolved (interactive) |
| 5 | [A] Browser verify in UI phases | Every phase changing `.tsx/.jsx/.css/.svg` has `agent-browser` steps |
| 6 | [B] E2E evidence capture | Final Testing Phase contains `RECORD_VIDEO=true`, webm save, and `Skill(skill: "upload-evidence")` call (NOT raw `gh release upload`) |
| 7 | E2E coverage matrix | Section 6 contains a behavior inventory table; total test count ≥ total behavior count; spec files organized by dev test-plan scenario (`<feature>-s<N>-<slug>.spec.ts`) with evidence artifacts table |
| 8 | Manual Tests section | `$STATE_DIR/<name>-dev.md` contains `## Manual Tests` table with scenario/steps/expected columns |
| 9 | Plan metadata in $STATE_DIR | Work dir computed from git context (REPO_ROOT, ISSUE, branch slug). `$STATE_DIR/plan.md` contains `video-required:` and (if true) `video-flows:` using `browser-verify-*`/`e2e-*` prefixes. Posted to GitHub as a comment with `<!-- gate:dev-plan:${TASK_ID} -->` — NOT written into the issue body. |
| 10 | Visual Reference (section 1a) | If any phase modifies `.tsx/.jsx/.css/.svg` files or adds/changes a user-observable surface: section 1a contains ≥1 fenced-code-block ASCII mockup OR Mermaid diagram per user-observable state (primary, empty, alternate modes, confirm). Each mockup has a `Notes:` line. Pure non-UI plans: section body is `Not applicable — non-UI change.` (heading still present). |
| 11 | User Experience (section 1b) | Section 1b contains, for every user-facing access mode created/changed, fenced-block transcript(s) showing what the user types AND sees, ≥1 error-path example, a Before-vs-After block, and a v1 carve-outs list. Pure UI PR may set the body to `See §1a` (heading still present). |

2. **If ANY check fails:**
   - DO NOT proceed to Step 4
   - Add the missing item to the plan
   - Re-run the scan
   - Only proceed when all 11 checks pass

3. **Log the result** at the end of the plan (visible to the orchestrator):

```markdown
<!-- Plan Completeness: 11/11 passed -->
```

If a check is intentionally skipped (e.g., no E2E possible because the feature has no testable UI flow and no API endpoint to test), the skill MUST:
- Replace the check with an explicit exemption note in the plan
- State the reason (e.g., "pure type refactor with no runtime behavior change")
- The exemption is visible to the orchestrator for gate review

### Why this step exists

Passive checklists in long prompts suffer from instruction dilution — the primary task (write the plan) dominates attention, and verification steps get skipped. A concrete example: a past run produced a plan with unit tests only, omitting E2E evidence capture entirely, because the completeness checklist existed but was never actively executed. Active self-validation with a scan-fix-rescan loop prevents this class of omission.

## Step 4: Publish to GitHub

**The plan comment (posted with `<!-- gate:dev-plan:${TASK_ID} -->` by the orchestrator's POST stage) is the canonical plan document.** All 8 sections of the Required Report Structure MUST appear in the plan file at `$STATE_DIR/${TASK_ID}-plan.md`; the orchestrator posts that file verbatim as the plan comment. **The GitHub issue body is NOT modified by this skill** — it remains as the user authored it. The triage seed in the existing body (Goals, Constraints, Related Files) should be read as input and incorporated into / preserved within the plan, but the body itself is left untouched.

### Verify Commands (written to plan file — NOT the issue body)

After writing the 8-section plan, append the gate metadata to the same plan file. This is machine-readable pipeline configuration — it must NOT appear in the GitHub issue body, which is public-facing and human-readable.

Determine the task name from the issue (kebab-case branch suffix, e.g., `my-feature`), then write the plan metadata to `$STATE_DIR/plan.md`:

```bash
# Compute TASK_ID / STATE_DIR / REPO inline (dev-plan may run standalone).
# Issue number: events.jsonl init event is the source of truth.
REPO_ROOT=$(git rev-parse --show-toplevel)
. "$HOME/.claude/scripts/events.sh" || { echo "ERROR: scripts/events.sh missing"; exit 1; }
STATE_DIR=$(events_state_dir) || { echo "ERROR: cannot resolve state dir (not in a git worktree?)"; exit 1; }
mkdir -p "$STATE_DIR"
ISSUE=""
if [ -f "$STATE_DIR/events.jsonl" ]; then
  ISSUE=$(events_latest "$STATE_DIR" init 2>/dev/null | jq -r '.issue_num // empty' 2>/dev/null || echo "")
fi
SLUG=$(git branch --show-current | sed 's|.*/||' | tr '/' '-')
TASK_ID="${ISSUE}-${SLUG}"
REPO=$(git remote get-url origin | sed -e 's#^.*github\.com[:/]##' -e 's#\.git$##')

# Append Verify Commands metadata to the plan document
cat >> "$STATE_DIR/plan.md" <<EOF

## Verify Commands
video-required: true
video-flows: browser-verify-<phase1>, browser-verify-<phase2>, s1-<slug>, s2-<slug>
EOF
```

> **Why `$STATE_DIR` instead of a task file:** The plan (and every other stage log) lives under the plugin-scoped state dir resolved via `events_state_dir` (per-branch, computed from git + repo slug). Each stage posts its summary to GitHub with a `<!-- gate:<stage>:${TASK_ID} -->` marker — there is no intermediate task file.

Rules for Verify Commands content:
- `video-required: true` if ANY implementation phase has `[A] browser verify` steps OR the feature changes `.tsx`/`.jsx`/`.css`/`.svg` files
- `video-required: false <reason>` if the feature is purely non-UI (e.g., API-only, type refactor)
- `video-flows:` lists every distinct video that will be captured using the type-prefix convention:
  - **`browser-verify-<flow>`** — `[A]` interactive browser verify recordings from implementation phases (tool: `agent-browser`)
  - **`s<N>-<slug>`** — `[B]` automated E2E spec recordings from the final testing phase (one per dev test-plan scenario; slug matches the scenario slug in the dev test plan). Matches `rules/testing.md` → File Naming Authority.
- Flow names must be kebab-case and match what will be saved as `<task>-<flow>.webm`

### Target selection

Always write the plan to the local plan file. The orchestrator's POST stage (`/plan-dev` or `/dev` PLAN stage) reads this file and posts it as a GitHub issue comment with the `<!-- gate:dev-plan:${TASK_ID} -->` marker. **Do NOT call `gh issue edit --body` for the plan content** — the GitHub issue body is left as the user authored it.

```bash
# Write the 8-section plan to the file the orchestrator reads.
cat > "$STATE_DIR/${TASK_ID}-plan.md" <<'EOF'
<8-section plan>
EOF
```

### Plan writing rules

- All 8 sections MUST be present: Overview, Technical Approach, Implementation Plan, Dependencies, Success Criteria, Implementation Notes, Code Examples, Open Questions
- If the issue had a triage seed (Goals, Constraints, Related Files), incorporate those into the Overview/Dependencies sections — do not discard them
- This skill does NOT modify the GitHub issue title or labels. Title/label conventions are user-local and out of scope. The user can apply them manually or through `/triage` if their repo has the convention.

## Output Guidelines

- **Use checkboxes (`- [ ]`)** for EVERY actionable step — GitHub progress tracking is mandatory
- Break down each phase into granular sub-tasks (not just "implement X" — specify what exactly)
- Mark parallelizable tasks with `[PARALLEL]` so implementers know what can run concurrently
- Include specific file paths where changes will be made
- Reference existing code patterns and components by name
- Focus on the 'why' behind decisions, not just the 'what'
- Include code examples for complex or non-obvious implementations
- Always analyze actual code before documenting — never make assumptions
- Each bullet point should be self-contained with enough context to be developed in isolation

## Working Principles

- **Think First, Code Later**: Invest significant time in planning to minimize implementation issues
- **Clarity Over Brevity**: Write detailed explanations that leave no room for ambiguity
- **Parallel When Possible**: Identify opportunities for parallel development to accelerate delivery
- **User-Centric**: Always align with the user's goals while suggesting improvements
- **Iterative Refinement**: Be prepared to revise plans based on feedback
- **Self-Contained Issues**: Each bullet point should be executable without needing to reference other items
- **Progressive Enhancement**: Structure plans so that partial implementations still provide value

When creating plans, remember that another agent (the builder) will read the plan comment (posted to the GitHub issue with the `<!-- gate:dev-plan:${TASK_ID} -->` marker) to implement the feature. The plan must be comprehensive enough that implementation can proceed without additional clarification. The GitHub issue body is left untouched — read it for context, but write the plan to the plan file.

## Output

- `$STATE_DIR/${TASK_ID}-plan.md` — the 8-section plan with `## E2E Scenarios` and `## Verify Commands` sections. The orchestrator posts this verbatim as a GitHub issue comment.
- `$STATE_DIR/<task-name>-dev.md` — local dev test plan derived from the plan file's E2E Scenarios section
- The GitHub issue body is **not** modified by this skill.

Task registration and session tracking are handled by the orchestrator, not by this skill.

---

# QA Planning (`--mode qa`)

# QA Plan Skill

Write mode only — creates a qa-plan document that the QA stage (`/qa` Phase 3) executes.
Called internally by `/qa` Phase 1. Direct invocation generates a standalone QA plan without executing it.

---

## Mode 1: Write — QA agent creates a qa-plan

### When

After the implementation is complete. The qa-plan should be ready before the QA stage begins so scenarios can be executed independently.

---

### Step 0: Handoff Collection

Before writing the qa-plan, collect the artifacts produced by the previous stages (dev-plan, builder).

```bash
TASK_NAME=$(basename "$TASK_FILE" .md)
TESTS=$(dirname "$TASK_FILE")/tests
```

1. **Infer issue type** (informational only — does not affect gates):
   ```bash
   # Prefer branch name → PR title prefix → recent commit prefix.
   # Labels are NOT consulted (user-local convention).
   ISSUE_TYPE=$(git branch --show-current | grep -oE '^(feat|fix|refactor|chore|docs|test|perf)' || echo "")
   if [ -z "$ISSUE_TYPE" ]; then
     ISSUE_TYPE=$(git log --format=%s -1 2>/dev/null | grep -oE '^(feat|fix|refactor|chore|docs|test|perf)' || echo "chore")
   fi
   ```
   The inferred type is informational; it does not change gate behavior.

2. **Read the dev test plan** (written by builder):
   ```bash
   cat "$STATE_DIR/${TASK_NAME}-dev.md" 2>/dev/null || echo "MISSING"
   ```
   If present: use the already-validated scenarios as the baseline for Gap Analysis.
   If missing: switch to Cold Start Mode (see below).

3. **Confirm E2E scenarios** (dev-plan output):
   ```bash
   # Read the ## E2E Scenarios section from task.md
   awk '/^## E2E Scenarios$/,/^## [^E]/' "$TASK_FILE" 2>/dev/null
   # Or check the issue body
   gh issue view "$ISSUE_NUMBER" --json body -q '.body' | awk '/^## E2E Scenarios$/,/^## [^E]/'
   ```
   If present: use those scenarios as the coverage baseline. Expand any gaps as new scenarios.
   If missing: derive scenarios from scratch.

4. **Confirm the implementation diff**:
   ```bash
   git diff "$BASE_BRANCH"...HEAD --stat
   git diff "$BASE_BRANCH"...HEAD -- '*.ts' '*.tsx' | head -200
   ```

5. **Read TIA results** (written by builder Verify mode — /dev VERIFY stage):
   ```bash
   cat "$STATE_DIR/${TASK_NAME}-tia.md" 2>/dev/null || echo "MISSING"
   ```
   - **If present**: record the spec list TIA covered into `TIA_COVERED_SPECS`; flag any failed specs separately.
   - **If missing**:
     a. Search the issue comments for TIA traces: `gh issue view "$ISSUE_NUMBER" --json comments -q '.comments[].body' | grep -i 'tia\|test impact'`
     b. Check the `## Build Results` / `## TIA Results` sections of task.md: `awk '/^## (Build|TIA) Results$/,/^## [^BT]/' "$TASK_FILE"`
     c. Identify affected specs directly from the diff: extract changed files via `git diff "$BASE_BRANCH"...HEAD --name-only`, then enumerate existing `*.test.*`/`*.spec.*` files that reference those modules
     d. Record specs that have no execution evidence as the **TIA gap** entry under `Scope Boundary`
   - `TIA_EXISTS`: yes | no — included in the handoff summary

**Handoff result summary** (internal note, not included in the document):
- `ISSUE_TYPE`: feat | fix | refactor | chore
- `DEV_PLAN_EXISTS`: yes | no
- `E2E_SCENARIOS_EXISTS`: yes | no
- `TIA_EXISTS`: yes | no
- `TIA_COVERED_SPECS`: [list of spec paths] | empty
- `MODE`: Gap Analysis (handoff present) | Cold Start (handoff missing)

---

### Step 1: Capability Inventory (Requirements Traceability)

Before writing scenarios, enumerate every **user-visible capability** introduced by the diff.
Classify by user-facing capability, not by code module.

**Lens by issue type (apply the `ISSUE_TYPE` confirmed in Step 0):**

| Type | Focus | Boundary |
|------|-------|----------|
| `feat` | The full user journey of the new feature. Happy path + error path + boundary values | Regression of existing features is included only when explicitly affected |
| `refactor` | **Behavior preservation** — does it produce the same result as before? No user-visible difference allowed | No new-feature verification; only verify that user-visible outcomes are identical |
| `fix` | Prevent recurrence of the fixed bug + detect related regressions | Do NOT verify new features or unrelated regressions |
| `chore` | None — QA not required (infrastructure/build changes) | — |

1. Read `git diff $BASE_BRANCH...HEAD` and the issue description, and extract user-visible capabilities
2. Score risk per capability: `risk = impact × likelihood`
3. Build the capability inventory table

| Impact | Likelihood | Priority | Test Depth |
|--------|-----------|----------|------------|
| HIGH | HIGH | P1 | Full scenario + error path + boundary values |
| HIGH | LOW | P2 | Full scenario + key error paths |
| LOW | HIGH | P3 | Happy-path scenario |
| LOW | LOW | P4 | May be deferred with rationale |

**Coverage rules:**
- CRITICAL/HIGH capabilities: at least 1 scenario MUST exist
- MEDIUM capabilities: coverage recommended
- LOW capabilities: may be deferred with stated rationale

### Step 2: SFDPOT Dimension Expansion (HTSM-based)

For each capability, examine which SFDPOT dimensions need testing and expand scenarios accordingly:

| Dimension | Question |
|-----------|----------|
| **S**tructure | Are the UI elements correctly present? |
| **F**unction | Does the core behavior work? |
| **D**ata | Are valid/invalid/boundary inputs handled? |
| **I**nterfaces | Does it work at integration touchpoints? |
| **P**latform | Does it work on the target environment? |
| **O**perations | Does it work under realistic conditions? |
| **T**ime | Are timing/ordering important? |

**Dimension rules:**
- Each scenario MUST cover at least Function
- P1 scenarios: Function + at least 2 additional dimensions (typically Data + Interfaces)
- Not every dimension applies to every capability — pick only the relevant ones

### Step 2.5: Environment Constraint Mapping

Before writing scenarios, confirm whether each capability can actually be exercised.
**Environment constraints are not a reason to skip scenarios** — they determine the testing approach.

| Constraint Type | Decision Criteria | Response |
|-----------------|------------------|----------|
| External service unavailable | Is the service absent in the dev environment? | Check whether mocking is possible. If not, mark as BLOCKED |
| SSRF / firewall restriction | Is access to localhost or private IPs blocked? | Look for a workaround (mocked fixture, test flag). If none exists, BLOCKED |
| Authentication required | Is a user with specific permissions required? | Use Playwright auth state or seed data |
| Filesystem / OS dependency | Does macOS need a Linux-only binary? | Mark the capability as BLOCKED |

**Rules:**
- Document the execution environment (dev URL, required services) for every scenario
- BLOCKED scenarios MUST still be included in the qa-plan — annotated with a reason
- "Cannot do it because the environment is missing" is not acceptable. Change the testing approach instead.

### Step 3: Identify QA scenarios (Scenario-First)

Based on the capability inventory and SFDPOT dimensions, write user-journey scenarios.
Each scenario MUST be a **complete user journey** — not a code path.

**Scenario derivation process:**
1. Cover P1/P2 capabilities first from the inventory
2. Group related changes into a coherent user journey (1 scenario = 1 user goal)
3. Actor-Based naming: `[user] can [action] under [condition]`
4. Success conditions are observable outcomes — what the user sees, not how the code behaves
5. Include at least one end-to-end journey that spans multiple capabilities

**Minimum coverage formula:**
```
minimum scenarios = count(HIGH/CRITICAL capabilities) + 1 end-to-end journey
recommended scenarios = above + count(MEDIUM capabilities needing the Function dimension)
```

**Inclusion criteria:**
- Verify the full user journey end-to-end
- Success depends on real data or real API behavior
- Optimal for verification by someone unaware of the implementation
- Cases where mocking would create false confidence (UI flow, user-visible state transitions)

**Exclusion criteria (apply strictly):**
- Verifying a specific code behavior or regression — except for integration boundaries (where two modules actually connect), which DO require E2E
- When mocking provides reliable, deterministic coverage — but if mocking bypasses the real integration path, do not exclude
- Concerns that are about code correctness, not user experience
- **When unit tests are sufficient**: pure calculation/transformation logic, functions without external I/O, fully isolated utilities
- **When unit tests are insufficient (E2E required)**: flows crossing two or more layers, real network/DB/filesystem dependencies, user-visible state transitions

> **Core principle**: judge by **integration boundaries**, not by code paths.
> Even when something can be unit-tested, the integration path itself must be verified by E2E.

---

### Cold Start Mode (when handoff is absent)

If Step 0 yields `DEV_PLAN_EXISTS=no` and `E2E_SCENARIOS_EXISTS=no`, run in Cold Start Mode.

**What Cold Start Mode is**: when there is no handoff from dev-plan or builder, the QA agent analyzes the source directly to identify capabilities.

**Additional steps to perform:**
1. **Read the full issue body**: `gh issue view "$ISSUE_NUMBER" --json body,title`
2. **Read the full PR diff**: `git diff "$BASE_BRANCH"...HEAD -- '*.ts' '*.tsx' '*.js'`
3. **Identify the changed files and their roles**:
   ```bash
   git diff "$BASE_BRANCH"...HEAD --name-only | while read f; do echo "=== $f ==="; done
   ```
4. **Extract user-visible capabilities directly from each changed file** — analyze function names, exports, API routes, UI components
5. **Check existing test files**:
   ```bash
   find apps/*/tests apps/*/src -name '*.test.*' -o -name '*.spec.*' 2>/dev/null | head -30
   ```
   Compare paths covered by existing tests against the new capability paths

**Cold Start completion criterion**: every changed module's user-visible capability MUST appear at least once in the Capability Inventory.

> **Note**: Cold Start is a fallback, not a preferred mode. If the dev-plan stage failed to produce handoff data, document that as a gap.

---

### Step 4: Rewrite as pure user language

For each QA scenario, rewrite from scratch in user language:

| Remove | Replace with |
|--------|-------------|
| Component names (`ChatInput`, `MessageBranch`) | Descriptive UI terms ("the message input field", "the version selector") |
| API routes (`/api/chat`, `POST /messages`) | Observable outcomes ("a response appears") |
| Technical state ("store updates", "re-renders") | What the user sees ("the page updates", "the list refreshes") |
| Code terms ("optimistic update", "SSE stream") | User-visible behavior ("the message appears immediately") |

**Validity check**: read the finished qa-plan aloud. If someone who has never seen the codebase could execute every step, it's valid.

### Step 5: Write and publish the plan

**Output location**: `$STATE_DIR/<task-name>-qa.md`

**Publishing**: this skill writes the qa-plan to `$STATE_DIR/<task-name>-qa.md`. The orchestrator's POST stage (`/plan-qa` or `/qa` PLAN stage) reads this file and posts it as a GitHub issue comment with the `<!-- gate:qa-plan:${TASK_ID} -->` marker. **Do NOT call `gh issue edit --body`** — the GitHub issue body is left as the user authored it.

**Fallback**: Post as a new PR comment if the issue doesn't exist.

### qa-plan Document Format

```markdown
# QA Plan: <feature-name>

## System Access
- URL: <dev server URL — resolve using the mechanism declared in the project's CLAUDE.md>
- Credentials: <from project CLAUDE.md>
- Required state: <what must exist in the system before testing begins, in plain terms>

## Feature Brief
<2-3 sentences describing what this feature does, from a user's perspective.
No code, no component names, no technical details.>

## Personas
- **Who**: <role and goal — e.g., "a developer who wants to review a previous conversation">
- **Environment**: Chrome, 1280×720
- **Assumption**: user is already logged in

## Capability Inventory

| # | Capability | Impact | Likelihood | Priority | SFDPOT Dimensions |
|---|-----------|--------|-----------|----------|-------------------|
| C1 | <user-visible capability> | HIGH/MEDIUM/LOW | HIGH/MEDIUM/LOW | P1/P2/P3/P4 | F, D, I |
| C2 | ... | ... | ... | ... | ... |

**Coverage summary:**
- CRITICAL/HIGH capabilities: N → all mapped to scenarios
- MEDIUM capabilities: N → N covered, N deferred (reason: ...)
- LOW capabilities: N → deferred (reason: ...)

## Scenarios

### S1: <scenario name — a user goal, not a test type>
**Capabilities**: C1, C3 (capability numbers covered)
**Dimensions**: Function, Data, Interfaces
**User action**: <one sentence — what the user is trying to accomplish>

**Steps**:
1. <concrete browser action — e.g., "Click the chat history button in the sidebar">
2. <concrete browser action>
3. ...

**Success conditions**:
- <observable outcome — what the user sees, e.g., "The previous messages are visible">
- <observable outcome>

**Out of scope**: <what NOT to verify in this scenario>

**Expected evidence** (video mode — default):
- `$STATE_DIR/evidence/s<N>-<slug>.webm` (one recording per scenario — orchestrator rewrites to `s<N>-<slug>.<hash8>.webm` via `store_evidence_migrate`)

**Expected evidence** (screenshot mode — requires rationale):
- `$STATE_DIR/evidence/s<N>-step<NN>-<desc>.png` (one per user action)
- `screenshot-rationale: <reason>` line in gate:verify comment body

> This is a **contract**, not a suggestion. The tester agent MUST produce files with exactly these basenames under `$STATE_DIR/evidence/` (both video and screenshot modes), and the orchestrator MUST upload exactly those files to the GitHub Release. The /qa FINALIZE step verifies `count(scenarios) == count(uploaded evidence files)`; mismatches block the gate.

### S2: ...

## Coverage Adequacy Check

**C-number traceability table** (verify every Capability is mapped to at least one scenario):

| Capability | Priority | Mapped Scenarios | Status |
|-----------|----------|-----------------|--------|
| C1 | P1 | S1, S3 | ✅ Covered |
| C2 | P1 | S2 | ✅ Covered |
| C3 | P2 | — | ⚠️ Not covered (reason: ...) |
| C4 | P4 | — | ⏭️ Deferred (LOW risk, reason: ...) |

**Checklist:**
- [ ] Every CRITICAL capability has ≥1 scenario (no unmapped C-number)
- [ ] Every HIGH capability has ≥1 scenario (no unmapped C-number)
- [ ] Each P1 scenario covers Function + ≥2 SFDPOT dimensions
- [ ] At least 1 end-to-end journey spans multiple capabilities
- [ ] Error paths of capabilities with external dependencies are tested
- [ ] BLOCKED scenarios state the reason and an alternative
- [ ] Deferred capabilities are LOW risk only (rationale stated)
- [ ] Minimum coverage formula satisfied: scenario count ≥ HIGH/CRITICAL count + 1
- [ ] **If Cold Start**: every capability derived from issue body + diff is in the Inventory

## Scope Boundary
**In scope**: <features to test>
**Out of scope**: <features to ignore>
**Known limitations**: <expected constraints — do not flag these as bugs>
**TIA covered**: <spec paths already verified by /dev test TIA — qa should NOT re-run these>
**TIA gap**: <spec paths affected by the diff but NOT covered by TIA — qa MUST run these in Phase 2 (Regression). Use `none` if TIA was fully complete.>
```

### Rules for tester agent

- **NEVER** include code, component names, or API routes
- **MUST** add `Required state` for any scenario needing pre-existing data
- **MUST** include an `Expected evidence` filename per scenario — the basename written here is the contract enforced by /qa FINALIZE
- **MUST** include `Capability Inventory` section with risk scoring
- **MUST** include `Coverage Adequacy Check` section with all items checked
- **MUST** map every scenario to capability numbers (`Capabilities: C1, C3`)
- **MUST** specify SFDPOT dimensions per scenario (`Dimensions: Function, Data`)
- **MUST** satisfy minimum coverage formula: `scenario count ≥ HIGH/CRITICAL count + 1`
- One scenario = one coherent user goal (not a list of unrelated checks)
- P1 scenarios MUST cover Function + at least 2 additional dimensions
