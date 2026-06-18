---
paths:
  - ".github/**"
  - "**/commands/**"
---

# Labels

> **Status: user-local convention.** Labels are NOT required for the `/dev`, `/qa`, `/plan-dev`, `/plan-qa`, `/epic` pipelines to function. Pipelines, gate hooks, and skills do not read labels for any decision; all gate-keeping is local (`events.jsonl`).
>
> This catalog documents the label set the user maintains in their own repos. The only place labels are *applied* automatically is the `/triage` skill, which the user invokes explicitly. Other skills and commands do not write labels — they assume label conventions are user-local and may not exist in other contributors' repos.

Standard GitHub label definitions for users who choose to maintain a label catalog in their repo.

## Label Length Policy

- **Label name: max 20 characters** (industry best practice — fits GitHub issue badge without overflow)
- **Label description: max 50 characters** (scannable tooltip at a glance)
- Format: `prefix:value` — prefix counts toward the 20-char limit
- Use standard abbreviations: `perf`, `deps`, `depr`, `wip`

## Label Catalog (29 labels)

### Status (7)

| Label | Color | Description |
|-------|-------|-------------|
| `status:ready` | `#0075CA` | Triaged and ready for work |
| `status:wip` | `#0E8A16` | Work in progress |
| `status:review` | `#D93F0B` | PR created, awaiting review |
| `status:done` | `#6E7781` | PR merged, issue closed |
| `status:backlog` | `#C5DEF5` | Not yet prioritized |
| `status:blocked` | `#B60205` | Blocked by dependency |
| `status:wontfix` | `#FFFFFF` | Declined or out of scope |

### Type (10)

| Label | Color | Description |
|-------|-------|-------------|
| `type:enhancement` | `#A2EEEF` | New feature or improvement |
| `type:bug` | `#D73A4A` | Something isn't working |
| `type:refactor` | `#D4C5F9` | Code restructuring, no behavior change |
| `type:chore` | `#FEF2C0` | Maintenance, tooling, infrastructure |
| `type:docs` | `#0075CA` | Documentation only |
| `type:test` | `#BFD4F2` | Test additions or updates |
| `type:perf` | `#F9D0C4` | Performance improvement |
| `type:security` | `#B60205` | Security fix or improvement |
| `type:deps` | `#EDEDED` | Dependency update |
| `type:question` | `#D876E3` | Needs clarification |

### Priority (5)

| Label | Color | Description |
|-------|-------|-------------|
| `priority:critical` | `#B60205` | Must fix now — production down |
| `priority:high` | `#D93F0B` | Must fix this sprint |
| `priority:medium` | `#FBCA04` | Should fix soon |
| `priority:low` | `#0E8A16` | Nice to have |
| `priority:backlog` | `#C5DEF5` | Someday / maybe |

### Impact (2)

| Label | Color | Description |
|-------|-------|-------------|
| `impact:breaking` | `#B60205` | Breaking change — major version bump |
| `impact:depr` | `#D93F0B` | Deprecates existing API or behavior |

### QA (1)

| Label | Color | Description |
|-------|-------|-------------|
| `qa:e2e-required` | `#D93F0B` | E2E tests mandatory before PR |

**Enforcement note:** Earlier versions of this rule claimed `pre-bash-pr-gate.sh` reads this label to enforce E2E evidence. That is no longer the case — gate enforcement is local-only via `events.jsonl stage.passed(verify)`, with no GitHub label read. The `qa:e2e-required` label remains as a human-visible signal in repos that maintain the convention; it has no effect on the gate.

### Conditional (4+)

| Label | Color | Description |
|-------|-------|-------------|
| `area:*` | `#EDEDED` | Feature area (e.g., `area:auth`, `area:api`) |
| `platform:*` | `#BFD4F2` | Platform (e.g., `platform:ios`, `platform:web`) |

Area and platform labels are project-specific. Create as needed with the colors above.
`area:*` and `platform:*` values MUST also stay within the 20-char total limit.

## Commit Prefix → Label Mapping

| Commit Prefix | Label |
|---------------|-------|
| `feat` | `type:enhancement` |
| `fix` | `type:bug` |
| `docs` | `type:docs` |
| `style` | `type:chore` |
| `refactor` | `type:refactor` |
| `perf` | `type:perf` |
| `test` | `type:test` |
| `chore` | `type:chore` |
| `security` | `type:security` |
| `deps` | `type:deps` |

## Status Transitions

```
backlog → ready → wip → review → done
                    ↓
                 blocked → wip (when unblocked)

Any status → wontfix (declined)
```

| From | To | Trigger |
|------|----|---------|
| `status:backlog` | `status:ready` | Issue triaged and prioritized |
| `status:ready` | `status:wip` | Work begins |
| `status:wip` | `status:review` | PR created |
| `status:wip` | `status:blocked` | External dependency |
| `status:blocked` | `status:wip` | Blocker resolved |
| `status:review` | `status:done` | PR merged |
| any | `status:wontfix` | Issue declined |

## Label Policy

### Check Before Apply

```bash
gh label list --json name -q '.[].name'
```

Verify the label exists before applying. If missing, report to user — NEVER auto-create.

### Recommended Labels (when the repo maintains the catalog)

Every issue SHOULD have at least 3 labels — applied via `/triage` or manually by the user. None of the pipelines depend on labels being present.

1. **status:** — one of the 7 status labels
2. **type:** — one of the 10 type labels
3. **priority:** — one of the 5 priority labels

### Verify After Apply

```bash
gh issue view <number> --json labels --jq '.labels[].name'
```

Always verify labels were applied correctly.

## Rules (apply only when the user explicitly invokes a label-applying workflow such as `/triage`)

- MUST check label existence before applying
- NEVER auto-create labels — report missing labels to user
- SHOULD apply at least status + type + priority to every issue when the convention is in use
- MUST verify labels after applying
- MUST follow status transition rules
- MUST keep label names under 20 characters
- Only one `status:*` label per issue at a time
- Only one `priority:*` label per issue at a time
- Multiple `type:*` labels are allowed (e.g., `type:bug` + `type:security`)
- Pipelines (`/dev`, `/qa`, `/plan-dev`, `/plan-qa`, `/epic`) MUST NOT read or write labels — labels are out of scope for those flows
