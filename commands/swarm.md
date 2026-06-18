---
description: Parallel execution with model routing — splits tasks and runs them concurrently
argument-hint: [task description]
---

# /swarm

Parallel execution engine with model routing. Splits tasks into independent subtasks, routes each to the optimal agent+model combination, and runs them concurrently.

## Model Routing

| Complexity | Model | When |
|------------|-------|------|
| Simple | `haiku` | Single-file edits, boilerplate, formatting, typo fixes |
| Standard | `sonnet` | Multi-file implementation, test writing, refactoring |
| Complex | `opus` | Architecture decisions, complex logic, security-critical code |

## Agent Selection

| Task Type | Agent | Model |
|-----------|-------|-------|
| Simple code change | `builder` | haiku |
| Standard implementation | `builder` | sonnet |
| Complex implementation | `builder` | opus |
| Test writing | `qa` | sonnet |
| Security-sensitive | `reviewer` | opus |

## Execution Steps

```
1. CLASSIFY  → Analyze task, split into independent subtasks
2. ROUTE     → Assign agent + model per subtask (routing table above)
3. LAUNCH    → Fire all independent subtasks in parallel via Task tool
4. MONITOR   → Track background tasks, collect results
5. VERIFY    → Check each result, aggregate into final output
```

## Splitting Rules

A task can be split when subtasks are:
- **Independent**: No data dependencies between them
- **Idempotent**: Safe to retry without side effects
- **Isolated**: Each operates on different files/resources

Do NOT split when:
- Tasks have sequential dependencies
- Tasks modify the same files
- Order of execution matters for correctness

## Result Aggregation

| Strategy | When |
|----------|------|
| Concatenate | Independent outputs (review + test results) |
| Deduplicate | Multiple searches for same info |
| Priority merge | Conflicting results (use highest severity) |
| Summary | Large outputs needing compression |

## Conflict Resolution

When parallel agents produce conflicting results:
1. Flag the conflict to orchestrator
2. Present both findings to user
3. User decides (or higher-authority agent resolves)

## Examples

### Good — Independent file changes
```
/swarm Add input validation to UserForm, PaymentForm, and ProfileForm
→ 3 parallel builder(haiku) tasks, one per form
```

### Good — Mixed complexity
```
/swarm Implement auth middleware + write tests + update docs
→ builder(sonnet) for middleware, qa(sonnet) for tests, builder(haiku) for docs
```

### Bad — Sequential dependency
```
/swarm Create database schema then seed it with test data
→ REJECT: seeding depends on schema — sequential execution required
```
