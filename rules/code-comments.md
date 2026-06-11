---
paths:
  - "**/*.{ts,tsx,js,jsx,mjs,cjs,py,go,rs,java,rb,php,swift,kt,c,cc,cpp,h,hpp,cs,sh,bash,zsh}"
---

# Code Comment Rules

Operationalizes the `core.md` directive "NEVER add meaningless comments" with testable triggers. The vague form is exactly what lets agents rationalize meaningful-looking but rotten comments past their own filter.

## The Self-Check (apply BEFORE writing any comment longer than one line)

Refuse to write the comment if **any** of these triggers fires:

1. **Channel collision** — `git blame` + the commit message + the PR description would tell a future reader the same thing. Comments duplicate; commit messages are immutable; PR descriptions are searchable. Do not pay the comment-rot tax for information that is already persisted elsewhere.

2. **Time-rotting words** — the comment contains any of: `Phase \d+`, `iteration \d+`, `Plan v\d+`, `review H\d+`, `QC-\d+`, `QH-\d+`, `H-\d+`, `C-\d+`, `PR #\d+`, `issue #\d+`, `post-fix`, `carryover`, `[Ff]ollow-up`, `Plan v\d+ Phase \d+`. These reference ephemeral pipeline state and become misleading the moment the next iteration ships.

3. **Rule citation** — the comment names a path under `rules/`, `commands/`, `agents/`, or `skills/`, OR cites a rule by phrase ("VERIFY BEFORE ABSTRACT", "Planner ≠ Reviewer", "Real-environment principle", etc.). Citing a rule inside source is an admission that the rule was not actually followed — real compliance is the behavior, not the citation. The reader can search the rules directory if they need policy context.

4. **What-narration** — the comment describes WHAT the code does. Well-named identifiers + a typed signature already do that. If the names are insufficient, fix the names.

If none of the four triggers fires, the comment may be written.

## The Allowed Set (the only legitimate reasons to write a comment)

Writing is allowed when the comment serves one of these specific purposes:

- **Justification mandated by `core.md`** — `eslint-disable`, `as any`, or `@ts-ignore`/`@ts-expect-error` MUST carry a one-line reason (existing rule, not waived by this file).
- **Hidden constraint or invariant** — a precondition, ordering requirement, or shared-state assumption that a reader cannot infer from the local code. Example: `// Caller must hold the row lock; this function does not re-check.`
- **Workaround for a specific upstream bug** — must include the bug tracker URL or upstream issue number. The link decays if the upstream changes; the comment then becomes removable in the same PR.
- **Surprising behavior despite good naming** — a security decision, a concurrency subtlety, a deliberate non-obvious branch. The bar is "a competent reader, after reading the code carefully, would still be wrong about what happens."

If the comment does not fit one of these, it does not belong in the source file. Move it to the commit message, the PR description, or the issue.

## Length Limits

- One-line `//` or `#` comment is the default form. Use it sparingly.
- Multi-line block comments (3+ lines) are reserved for the **Hidden constraint** and **Surprising behavior** cases above. They MUST NOT recap diff intent, plan stage, reviewer feedback, or motivation that belongs in the commit message.
- Never write multi-paragraph docstrings. A function's contract is its name + signature + types. If you need a paragraph to explain it, the function is too large or named wrong — fix the code, not the doc.

## Examples

**Bad — ships rotting work-state into source:**

```ts
// Plan v2 Phase 1: split structuredContent (UI-only) from content
// (model-visible). The LLM only sees `modelResult`. ASSUMPTION GAP
// (Phase 2 carryover, review H2): per `rules/core.md` → VERIFY BEFORE
// ABSTRACT, this contract is not yet proven by an integration test.
const { modelResult, structuredContent } = splitStructuredContent(rawResult);
```

Why bad: cites `rules/core.md`, names "Phase 1 / Phase 2 / review H2", narrates *what* `splitStructuredContent` returns (the function name already says it), and substitutes a comment for the integration test the rule actually demands.

**Good — no comment; commit message holds the rationale:**

```ts
const { modelResult, structuredContent } = splitStructuredContent(rawResult);
```

Commit message: `fix(chat): strip structuredContent from model-visible content` with the assumption-gap caveat in the PR description, and the integration test in the same diff.

---

**Bad — narrates intent that the diff already shows:**

```ts
// Phase 6 — single stable React tree across all display modes.
// Only the wrapper class names change based on `displayMode`; the
// iframe element and its parent slot stay at the same position in
// the React tree.
const wrapperClass = displayMode === 'fullscreen' ? '...' : '...';
```

Why bad: "Phase 6" rots; the rest is what-narration that a reader can see by reading the next 8 lines.

**Good — delete the comment; let the names carry meaning:**

```ts
const wrapperClass = displayMode === 'fullscreen' ? '...' : '...';
```

---

**Good — hidden constraint a reader cannot infer:**

```ts
// MCP App widgets dispatch size-changed in a ResizeObserver loop.
// Honoring width here causes content to re-wrap narrower, retriggering
// the observer until iframe collapses to MIN_IFRAME_SIZE_PX.
const honorWidth = displayMode !== 'inline';
```

This is the **Surprising behavior** case: the feedback loop is invisible from the local code. A reader who deletes the `honorWidth` guard will reintroduce the bug. Note: no `Phase`, no `rules/` citation, no `// fix for issue #...`. Just the invariant.

## Enforcement

Two layers (see `commands/dev.md` REVIEW stage and `hooks/gate-keeping/pre-bash-comment-audit.sh`):

1. **Mechanical pre-commit gate** — blocks `git commit` when the staged diff adds a comment line matching the time-rotting-words or rule-citation regex set. Bypass: `CLAUDE_COMMENT_AUDIT_SKIP=1` (logged to `events.jsonl`). Use only for the rare case where the comment is genuinely the "Hidden constraint" kind AND the regex false-fires (very rare in practice).
2. **Reviewer agent** — flags violations of triggers 1, 2, 3, 4 as **MEDIUM** findings during `/dev` REVIEW. MEDIUM does not block APPROVED, but the finding goes into the audit report and the builder is expected to clean it up.

These are taste/noise rules, not safety rules — they belong at MEDIUM, not CRITICAL/HIGH. The point is to make the right behavior the easy default, not to grind the pipeline to a halt over a stray comment.
