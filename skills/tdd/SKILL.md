---
name: tdd
description: TDD workflow with strict test-first gates, Red-Green-Refactor cycle, and verification rules. Use for test-first development methodology. For web-specific E2E testing, use `/playwright` or `/e2e`.
---

# TDD Skill

Test-Driven Development methodology with strict test-first enforcement.

For web-specific testing (Playwright, browser E2E), use `/playwright` or `/e2e`.

## Rules

- **NEVER** implement before tests exist
- **NEVER** complete with failing tests
- **NEVER** skip test verification — always show test output as proof
- **HARD RULE**: ALL tests (E2E + unit) MUST pass at the end of each phase

---

## HARD GATE: TEST-FIRST ENFORCEMENT

**THIS IS A BLOCKING REQUIREMENT. YOU CANNOT PROCEED WITHOUT COMPLETING EACH GATE.**

### Gate Checklist (MUST complete in order)

Before ANY implementation code:

1. [ ] **E2E test file created** — Show the file path
2. [ ] **E2E test cases written** — Show the test code
3. [ ] **E2E tests executed** — Show the FAILING output
4. [ ] **Unit test file created** — Show the file path
5. [ ] **Unit test cases written** — Show the test code
6. [ ] **Unit tests executed** — Show the FAILING output
7. [ ] **Integration test file created** — Show the file path (or declare "N/A: pure logic, no layer crossing" with justification)
8. [ ] **Integration test cases written** — Show the test code (or N/A with justification)
9. [ ] **Integration tests executed** — Show the FAILING output (or N/A with justification)

### Enforcement Rule

```
IF implementation_file_edited AND NOT all_gates_completed:
    STOP IMMEDIATELY
    DELETE the implementation changes
    GO BACK to writing tests
```

### What counts as "implementation code"

- ANY edit to source code files (`.ts`, `.tsx`, `.js`, `.jsx`, `.py`, `.rs`, `.go`, etc.)
- ANY edit that is NOT a test file
- Creating new non-test files

### What does NOT count

- Test files (`*.test.*`, `*.spec.*`, `*_test.*`)
- Plan/documentation files (`.claude/`, `*.md`)
- Configuration files (`*.json`, `*.yaml`, `*.toml`)
- Reading files for understanding

**If you find yourself about to edit an implementation file without showing failing test output first, STOP. You are violating the workflow.**

---

## Phase 1: Write Tests First

### Step 0: Derive test candidates (Three-Group Taxonomy)

Before writing any test code, derive the must-have test list:

1. **List all candidates** — brainstorm every test you *could* write (no filtering yet)
2. **Classify each candidate**:
   - **A** — Everyone agrees this must be tested (if broken, feature is clearly broken)
   - **B** — Most agree, some might skip (useful but debatable)
   - **C** — Debated (nice to have)
3. **Extract must-haves** — All A candidates. Add B candidates that cover an uncovered behavior zone (happy path / edge / error).
4. **Verify coverage** — Confirm at least one test covers each zone. If a zone is missing, add the cheapest candidate from that zone.

This step prevents under-testing (writing only the "obvious" tests) and over-testing (writing every conceivable candidate).

### Step 1: Write the tests

- Write tests BEFORE any implementation
- **Unit tests**: for logic and functions (follow project test conventions)
- **Integration tests**: MANDATORY when the change crosses ≥2 layers, depends on real DB/network/filesystem, or validates a wiring contract between modules. Integration tests are an equal first-class deliverable to unit tests — not optional, not a substitute.
  - Write as separate test files (e.g., `*.integration.test.*`) exercising real integration points (no mocking across the boundary being validated)
  - Skip only when the change is pure logic/transformation with no layer crossing and no external I/O
- **E2E tests**: for user-facing behavior (write as spec files from the start)
- Tests must include:
  - Inputs that accurately describe the operation sequence
  - Clear expected outputs for verification
  - All use cases and edge cases derived in Step 0
- Make sure tests are comprehensive and cover all acceptance criteria

**Gate Check:**

```
## Phase 1 Gate Check

### E2E Tests Created
- File: {path to E2E test file}
- Test cases:
  - {test case 1 description}
  - {test case 2 description}

### Unit Tests Created
- File: {path to unit test file}
- Test cases:
  - {test case 1 description}
  - {test case 2 description}

Gate Status: TESTS WRITTEN - Ready for Phase 2
```

---

## Phase 2: RED — Verify Tests Fail

- Run tests and confirm they FAIL (for web test commands, see `/playwright`)
- If tests pass, they are invalid — rewrite them

**Gate Check:**

```
## Phase 2 Gate Check

### Unit Test Output (MUST BE FAILING)
{paste actual test output showing failures}

### E2E Test Output (MUST BE FAILING)
{paste actual test output showing failures}

Gate Status: TESTS FAILING - Ready for Phase 3
```

**If tests are not failing, DO NOT PROCEED. Rewrite the tests.**

---

## Phase 3: GREEN — Incremental Implementation

**Implement ONE sub-task at a time. Verify before moving to the next.**

```
FOR EACH sub-task in sub-task list:

  STEP 1: FOCUS
    - State which sub-task you are working on
    - Identify the specific tests that should pass after this sub-task

  STEP 2: IMPLEMENT (INNER LOOP)
    REPEAT:
      a. Write minimum code for THIS sub-task only
      b. Run relevant tests (unit)
      c. If tests fail: analyze failure → fix → go to (a)
    UNTIL: Target unit tests for this sub-task pass

  STEP 2.5: INTEGRATION VERIFICATION
    - If this sub-task crosses ≥2 layers, touches real DB/network/filesystem, or validates a wiring contract: run the integration test(s) for this boundary
    - If integration test fails: fix the wiring (not the mock) → rerun → repeat
    - If no integration test applies (pure logic): declare "integration: N/A" with one-line justification
    - Integration MUST pass before advancing to STEP 3

  STEP 3: VERIFY & CHECKPOINT
    - Confirm target unit tests pass
    - Confirm target integration tests pass (or N/A declared)
    - Confirm previously passing tests still pass (no regressions)
    - Output sub-task completion status

  STEP 4: ADVANCE
    - Mark sub-task as complete
    - Move to next sub-task

END FOR
```

### Sub-Task Completion Report (output after EACH sub-task)

```
## Sub-Task {N}/{Total}: {Name}
- Status: COMPLETE
- Tests now passing: {list of newly passing tests}
- Regression check: No regressions
- Cumulative progress: {M}/{Total_Tests} tests passing
```

### Rules for Incremental Implementation

- **ONE sub-task at a time** — never implement multiple sub-tasks simultaneously
- **NO forward-looking code** — do not write code for future sub-tasks
- **Run tests after EACH change** — never batch multiple changes before testing
- **NO workarounds, NO skipping tests**
- **If a sub-task takes more than 3 attempts, STOP** — add logging, re-analyze, or split into smaller sub-tasks

---

## Test Plan Integration

When a test plan artifact exists at `$STATE_DIR/<task-name>-dev.md`, TDD integrates with it automatically.

### Step 0: Load Plan

At the start of TDD workflow, check for a test plan:

```
IF $STATE_DIR/<task-name>-dev.md exists:
    Load the plan
    Use plan's test IDs, descriptions, and target files to guide Gate Checklist
    Report: "Test plan loaded: N unit tests, M E2E tests planned"
ELSE:
    Proceed with standard TDD workflow (no plan = no change in behavior)
```

### Plan-Driven Gate Checklist

When a plan is loaded, the Gate Checklist items are derived from the plan:

- **E2E test file created** → Create spec files listed in plan's E2E section
- **E2E test cases written** → Write test cases matching plan's E2E IDs and descriptions
- **Unit test file created** → Create test files for targets in plan's Unit section
- **Unit test cases written** → Write test cases matching plan's Unit IDs and descriptions

### Status Updates

The TDD workflow updates the plan file's Status column as it progresses:

| TDD Phase | Status Transition |
|-----------|-------------------|
| Phase 1 (Write) | No change — tests being written, still `planned` |
| Phase 2 (RED) | `planned` → `red` — test confirmed failing |
| Phase 3 (GREEN) | `red` → `green` — test now passing |

Update the plan file in-place after each phase completes. Use the Edit tool to update Status values in the markdown table rows.

### Completeness Check

At the end of Phase 3, verify:
- All plan items with `planned` status → flag as incomplete
- All plan items should be `green`
- Report any gaps to the orchestrator
