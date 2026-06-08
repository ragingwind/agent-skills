---
paths:
  - "**/*.test.*"
  - "**/*.spec.*"
  - "**/tests/**"
  - "**/*.e2e.*"
---

# Testing Patterns — Methodology (Language/Framework Agnostic)

Distilled from the artifact stream E2E test suite (PR #343, 2026-02-27).
These patterns apply to **any** feature, language, or test framework.

For Playwright + Next.js specific patterns (SSE mocking, video recording, SPA routing),
see the project-level `memory/testing-patterns.md`.

---

## Pattern 1: Three-Group Taxonomy — Test Case Derivation

Three-Group Taxonomy is a **derivation methodology** for extracting must-have tests from a candidate list. It is NOT a way to classify or organize tests after the fact.

### How to use it

**Step 1: List all test candidates** — brainstorm every test you *could* write for this feature. Do not filter yet.

**Step 2: Classify each candidate**

```
┌─────────────────────────────────────────────────────┐
│  A — Everyone agrees this must be tested            │
│  "If this test fails, the feature is clearly broken"│
├─────────────────────────────────────────────────────┤
│  B — Most people agree, some might skip             │
│  "Useful but debatable given time/effort"           │
├─────────────────────────────────────────────────────┤
│  C — Debated — some say yes, some say no            │
│  "Nice to have, not essential"                      │
└─────────────────────────────────────────────────────┘
```

**Step 3: Extract must-haves** — Group A candidates are always written. Add Group B candidates if they cover an untested behavior zone (happy path, edge case, or error path). Group C is optional.

**Step 4: Verify coverage** — After extracting must-haves, check that at least one test covers each of the three behavior zones:
- Happy path (what must work for the feature to be useful)
- Edge/boundary (weird-but-valid inputs)
- Error/failure (what happens when things go wrong)

If a zone has zero coverage, add the cheapest Group B or C candidate from that zone.

### Why this works

Most test suites under-test because developers skip the candidate-listing step and jump straight to writing "obvious" tests. Three-Group forces you to surface hidden candidates before committing to a subset.

The derivation order matters: list first, classify second, extract third. Never classify while listing — it anchors you to your first instinct.

---

## Pattern 2: Behavioral Discovery via Failing Tests

Sometimes a test failure reveals actual app behavior that contradicts the test's assumption.
This is **useful information**, not just a failure.

### Example

- **Assumption in test**: Two consecutive `ARTIFACT_ERROR` events → first wins (second ignored).
- **Actual behavior**: Last wins (second overwrites first).
- **Action**: Rename test + update assertion to document real behavior.

### Decision tree when a negative-case test fails unexpectedly

```
Test fails with "element not found" or "wrong value"
         │
         ├─ Is the test assumption about app BEHAVIOR correct?
         │     NO → Update test to document actual behavior
         │     YES → It's a real bug → report to team
         │
         └─ Is the test flaky (fails sometimes, passes sometimes)?
               YES → Root cause is timing/race → fix the guard
               NO  → Deterministic failure → wrong assumption
```

### Why documenting actual behavior matters

Even "wrong" behavior (e.g., last-wins instead of first-wins) is important to document:
- It prevents future developers from accidentally "fixing" it and breaking dependent behavior.
- It creates a baseline: if behavior changes, the test fails and triggers a conversation.

---

## Pattern 3: Test Naming Convention (P1/N1/D1)

An independent naming convention — not tied to Three-Group derivation order.

```
describe('A: Positive — Happy Path Scenarios')
  test('P1: [thing] — [specific condition]')
  test('P2: [thing] — [specific condition]')

describe('B: Neutral — Edge Case Scenarios')
  test('N1: [thing] — [specific condition]')

describe('C: Negative — Pessimistic Scenarios')
  test('D1: [thing] — [specific condition]')   // D for "doomsday"
```

Benefits:
- Alphabetical ordering (A→B→C) matches dependency order: positive must pass before testing edge/error.
- Numbered IDs (P1, N1, D1) make cross-referencing in PR comments and bug reports precise.
- The suffix after `—` is the assertion-in-English: someone reading only test names understands what's verified.

---

## Pattern 4: Actor-Based Test Naming

Name tests from the user's perspective, not the implementation's.

```
// Good — describes what the user can do
"User can send a message and see a response"
"User cannot send an empty message"
"User can edit a sent message and see the updated version"

// Bad — describes what the code does
"sendMessage dispatches action"
"input validation returns false for empty string"
"MessageComponent re-renders after edit"
```

Format: `[Actor] can [action] [condition]` or `[Actor] cannot [action] when [condition]`

Benefits:
- Tests read like acceptance criteria
- Failing test names explain what broke in user terms
- Forces you to think about user intent before implementation details

---

## Pattern 5: Journey-Based Test Organization

Organize spec files by **user journey**, not by test type (assertions/flows/boundaries).

```
// Good — organized by journey
tests/e2e/chat/
  chat-send-message.spec.ts      // journey: user sends a message
  chat-edit-message.spec.ts      // journey: user edits a sent message
  chat-branch-navigation.spec.ts // journey: user navigates message branches

// Bad — organized by test type
tests/e2e/
  chat-assertions.spec.ts
  chat-flows.spec.ts
  chat-boundaries.spec.ts
```

Benefits:
- Each file has a single, clear responsibility
- Adding a new journey = adding a new file (no existing files touched)
- Failing test names immediately point to the broken journey
- Onboarding: new developer reads file names, understands what the feature does
