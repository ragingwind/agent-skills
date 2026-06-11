---
description: Retry loop primitive — execute/verify/fix/repeat with capped termination. Callers inject executor, verifier, fixer, terminator.
argument-hint: [task description]
---

# /ralph

Ralph is a **domain-agnostic retry loop primitive**. Callers inject what to run and when to stop; Ralph handles the loop control flow.

## Algorithm

```
loop:
  iteration += 1
  result = executor(iteration)
  (status, diagnosis) = verifier(result)
  if status == PASS: return SUCCESS
  fixer(diagnosis, iteration)
  if terminator(iteration, failure_history): return HARD_STOP
```

## Parameters (caller MUST inject all four)

| Parameter | Purpose | Provided by caller |
|-----------|---------|-------------------|
| `executor` | The agent or task to run each iteration | Required |
| `verifier` | Success check; on failure produces diagnosis for fixer | Required |
| `fixer` | Consumes diagnosis and modifies state so next iteration can differ | Required |
| `terminator` | Decides when to HARD STOP | Optional (defaults provided) |

## Default Termination Policy

If caller does not specify `terminator`, Ralph applies:
- max 5 iterations
- same-failure 3 times = HARD STOP (detects "no progress")

Callers may override with stricter or looser policies as appropriate.

## Invariants

1. Ralph MUST NOT know which agent the executor/fixer is.
2. Ralph MUST NOT know what domain the verifier checks.
3. Ralph MUST guarantee bounded iteration (terminator is mandatory, default or custom).
4. `iteration` count is passed to executor/fixer as generic context; their interpretation is their concern.

## Standalone invocation

```
/ralph <task description>
```

Orchestrator interprets the task description to derive (executor, verifier, fixer, terminator) and invokes the loop. For pipeline-embedded Ralph usage, see each pipeline command's stage documentation.

## What Ralph is NOT

- Not a specialized agent (no domain-specific worker lives inside Ralph — the executor/fixer are always caller-injected)
- Not a pipeline (see `/swarm` for parallel execution; pipelines are built by composing stages in `/dev`, `/qa`, etc.)
- Not tied to any gate/marker system (gate posting is caller responsibility)
