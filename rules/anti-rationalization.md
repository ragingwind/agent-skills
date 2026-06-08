# Anti-Rationalization Rules

Common excuses agents use to skip critical steps — with pre-emptive rebuttals.
Apply **before** taking a shortcut, not after it causes a failure.

> These complement `core.md` hard rules. Items already enforced by gates or hard rules there are not repeated here.

---

## BUILD stage (builder — Build mode)

### Tests

| Rationalization | Reality |
|---|---|
| "I tested it manually" | Manual testing doesn't persist. Tomorrow's change breaks it silently. Run the suite, show the output. |
| "It's just a prototype" | Prototypes become production. Test debt compounds into a crisis on first refactor. |
| "All tests pass" (without running them) | "All tests pass" without running is fiction. Output is the evidence; assertion is not. |
| "This is already covered by the existing suite" | Verify with TIA — don't assume. Assumed coverage is the leading cause of undetected regression. |

### Scope

| Rationalization | Reality |
|---|---|
| "This refactor is small enough to include with the feature" | Refactors mixed with features make both harder to bisect and impossible to revert cleanly. |
| "It's faster to do it all at once" | It feels faster until something breaks and you can't identify which of 500 lines caused it. |
| "I'll test it all at the end" | Bugs in Slice 1 make Slices 2–5 wrong. Test each slice before building on it. |

---

## REVIEW stage (reviewer)

| Rationalization | Reality |
|---|---|
| "AI-generated code is probably fine" | AI code needs **more** scrutiny, not less. It is confident and plausible even when wrong. |
| "The tests pass, so it's good" | Tests are necessary but not sufficient. They don't catch architecture problems, security issues, or readability failures. |
| "LGTM — the author knows the codebase" | Rubber-stamping is a failure mode, not a favor. Every Critical and Important finding must have a specific fix recommendation. |
| "We'll clean it up later" | "Later" is not a sprint. The review is the quality gate — require cleanup before merge, not after. |
| "I wrote this plan AND I'll approve it" | Planner ≠ Reviewer (`rules/orchestration.md`). Self-approval misses what the writer never thought of. Dispatch a separate reviewer agent. If you are the reviewer and you also wrote the artifact, REFUSE the review. |
| "This finding is MEDIUM, deferrable" (when reviewer initially flagged HIGH) | Downgrade requires explicit orchestrator-driven user override. The reviewer agent itself MUST NOT downgrade CRITICAL or HIGH findings on grounds of "deferrable". |

---

## qa-plan REVIEW stage (reviewer in qa-plan-review mode)

| Rationalization | Reality |
|---|---|
| "I mocked it with page.route() so production is validated" | Mock is a spec test, not validation. The qa-plan must define `Required state` in real-service terms. Mocked production routes for a P1 scenario = CRITICAL (QC-1). |
| "vendored fixture is enough" | "vendored" means a snapshot copy of upstream source. **Hand-written HTML that mimics the upstream API is "synthesized", not "vendored"**. Different word, different status. Synthesized fixtures count as mock-only environment (QC-1). |
| "Already deferred to Phase N, so we can pass" | Without a `gap.opened` event with a `close_by` field, "deferred" is "forgotten". Every gap MUST have a deadline and a closing condition. |
| "Dev env constraints, no way around it" | Constraints are resolved by environment provisioning. ENV-AUDIT refuses pipeline entry if the production environment is unreachable. The fix is `git clone <upstream> && pnpm dev`, not `page.route()`. |
| "It's just MEDIUM, deferrable" | QC-1 through QC-7 in `agents/reviewer.md` → QAPlanReviewMode are CRITICAL by design. Reviewer cannot downgrade. Only orchestrator + user can override per-finding via `AskUserQuestion`, with the override recorded in events.jsonl. |
| "tester agent will catch it later" | tester executes the qa-plan. If qa-plan says "use mock", tester uses mock. The reviewer is the only checkpoint that audits qa-plan substance. |
| "scenario count = evidence count, parity OK" | Parity check is necessary but not sufficient. The new check is `count(production_path_exercised: true) ≥ count(P1 capabilities)`. 8 mocked webms still fails the new check. |
| "URL 404 is just CDN propagation lag" | If the repo is private/internal, the public download URL requires auth. That is the ARCHITECTURE, not a delay. `upload-evidence.sh`'s reachability check is correct to refuse. Bypassing it = posting broken links to the gate trail. |

---

## QA / VERIFY stage (tester / builder Verify mode)

| Rationalization | Reality |
|---|---|
| "Dev tests pass, QA is redundant" | Dev TIA covers only affected specs. QA covers the TIA gap — different scope, not duplication. |
| "No UI changed, browser verification is optional" | API route changes cause UI behavior changes. Decide from the diff type, not from assumption. |
| "Screenshots are close enough for QA" | `/qa` default is `.webm`. A screenshot override requires a written rationale in the QA report. |

---

## Security (any stage)

| Rationalization | Reality |
|---|---|
| "This is an internal tool, security doesn't matter" | Internal tools get compromised. Attackers target the weakest link. |
| "We'll add security later" | Security retrofitting is 10× harder than building it in. Boundary validation belongs in the first commit. |
| "The framework handles security" | Frameworks provide tools, not guarantees. You still have to use them correctly. |
| "No one would exploit this" | Automated scanners will find it before a human attacker needs to. |

---

## Orchestration (orchestrator)

### Worktree routing

| Rationalization | Reality |
|---|---|
| "The worktree only has README.md, so I'll point the builder at the main repo root instead" | A stale worktree is a SETUP failure. Fix it with `git rebase origin/$BASE` in Step 1c — do NOT route around it. Routing to the main repo root commits directly to the base branch with no PR. |
| "The worktree doesn't have node_modules so I'll just use the project root" | Rebase the worktree. The builder must always work inside `$REPO_ROOT` (the worktree). No exceptions. |

### Gate bypass

| Rationalization | Reality |
|---|---|
| "The plan-hash mismatch is a false positive because we just wrote the plan — I'll proceed anyway" | Use `--skip-plan` explicitly and visibly. Silent bypass is the same as no gate. If you can't name the flag, you're rationalizing. |
| "The hash just changed because the skill updated the issue body, so it's fine" | That's a known design issue, not a reason to proceed silently. Either use `--skip-plan` or fix the hash computation. |
| "HARD STOP means I should stop unless I have a good reason" | HARD STOP means stop. "Good reason" is not an escape hatch — it is the rationalization that always appears before a bad decision. |

---

## Planning / Investigation

| Rationalization | Reality |
|---|---|
| "The requirements are obvious — I'll just start building" | State assumptions explicitly. Unspoken assumptions are the most common source of rework and Ralph loops. |
| "I'll figure it out as I go" | That's how you reach a 3-failure STOP with a tangled implementation and no clean rollback. |
| "I can hold the whole plan in my head" | Context windows compress. Written plans survive session boundaries and compression; mental plans don't. |
