---
name: parallel
description: Parallel, pipeline, team, and swarm execution modes for multi-agent coordination.
---

# Parallel Execution Skill

Multi-agent execution patterns for concurrent and coordinated work.

## Execution Modes

### Parallel Tasks
Run independent tasks concurrently via Task tool.

```
Task A ──┐
Task B ──┼── Aggregate ── Result
Task C ──┘
```

### Pipeline
Sequential agent chain with verification gates between steps.

```
Agent₁ ── gate ── Agent₂ ── gate ── Agent₃ ── Result
```

### Team
Multiple agents share context on a single task.

```
           ┌── Agent A ──┐
Shared ────┤             ├── Merge ── Result
Context    └── Agent B ──┘
```

### Swarm
Parallel execution with model routing — see `skills/swarm/SKILL.md` for the full swarm engine including model routing (haiku/sonnet/opus), agent selection, and splitting rules.

```
orchestrator → classify → route(agent+model) → [N parallel tasks] → aggregate → result
```

## Task Splitting Rules

### CAN Parallelize When:
- Tasks are **independent** (no shared state)
- Tasks are **idempotent** (same input → same output)
- Tasks are **isolated** (different files/modules)

### CANNOT Parallelize When:
- Tasks have sequential dependencies
- Tasks modify the same files
- Execution order matters for correctness

## Result Aggregation

| Strategy | When to Use |
|----------|------------|
| Concatenate | Independent search results |
| Deduplicate | Overlapping findings |
| Priority merge | Conflicting recommendations (higher severity wins) |
| Summary | Synthesize multiple agent outputs |

## Conflict Resolution

When agents produce conflicting results:
1. Flag the conflict explicitly
2. Present both results with context
3. Let the user decide

## Usage

- `/swarm [tasks]` — Parallel execution with model routing
- Orchestrator selects mode based on task analysis

## Rules

- MUST verify task independence before parallelizing
- MUST aggregate results before dependent tasks begin
- MUST NOT parallelize tasks that modify the same files
- Conflicts MUST be flagged and presented to user
