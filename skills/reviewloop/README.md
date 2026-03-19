# reviewloop

Bidirectional implement/review exchange via GitHub PR comments. An implementer works on code while external reviewer agents provide feedback through PR comments — automatically looping until approval.

## Features

- **3 modes**: inline (default), daemon (background polling), hook (legacy stop-hook)
- **Multi-reviewer**: run multiple agents in parallel or sequentially
- **Auto-termination**: stops on approval, max rounds, or unresolvable disagreement
- **Reviewer skip**: already-approved reviewers are skipped in subsequent rounds
- **Review report**: structured report generated on every loop termination

## Installation

```bash
npx skills add ragingwind/agent-skills --skill reviewloop
```

### Development (local symlink)

Install from a local clone via symlink for live editing:

```bash
git clone https://github.com/ragingwind/agent-skills.git
cd agent-skills
npx skills add ./ --skill reviewloop
```

By default `skills add` symlinks into the agent directory, so edits to the clone are reflected immediately. Use `--copy` to copy files instead.

## Prerequisites

- `gh` CLI authenticated and working
- At least one reviewer agent CLI installed (claude, opencode, gemini, codex)

## Usage

```bash
# Start a review loop on PR #42
/reviewloop 42

# Use daemon mode with specific reviewers
/reviewloop 42 --mode=daemon --reviewer=claude,opencode

# Dry run to verify config
/reviewloop 42 --dry-run

# Cancel active loop
/reviewloop cancel
```

## Scenarios

### Scenario 1: Basic Inline Review (Single Reviewer)

PR #42 on branch `feat/add-validation`, default inline mode with the `claude` reviewer.

```
$ /reviewloop 42
```

**Round 1 — engine output (stdout):**

```json
{"decision": "block", "reason": "## Review Feedback (Round 1) — Posted to PR #42\n\n### claude\nThe `validate_email` function does not handle empty strings...\n\nAddress the findings above. Commit and push your changes — the next review round will run automatically."}
```

**PR comment posted (Round 1 — reviewer):**

```
<!-- reviewloop:round-1 -->
## 🔄 Review (Round 1) — Claude Code

The `validate_email` function does not handle empty strings, which will raise
`AttributeError` at runtime. Please add a guard:

    if not email:
        return False

VERDICT: CHANGES_REQUIRED
```

Implementer fixes the issue, commits, and pushes. The engine runs again automatically.

**Round 2 — engine output (stdout):**

```json
{"decision": "approve"}
```

**PR comment posted (Round 2 — reviewer):**

```
<!-- reviewloop:round-2 -->
## 🔄 Review (Round 2) — Claude Code

Empty-string guard is in place. No further issues found.

VERDICT: APPROVED
```

**Final PR comment:**

```
✅ Review loop complete: APPROVED (claude=APPROVED)
```

---

### Scenario 2: Multi-Reviewer with Partial Approval

Two reviewers run in parallel. `claude` approves immediately; `opencode` requests changes.

```
$ /reviewloop 42 --reviewer=claude,opencode
```

**Round 1 — parallel execution:**

```
[14:02:01] Review Loop: Round 1: 2 reviewer(s) (claude, opencode) — parallel
[14:02:01] Review Loop: Round 1: reviewer (claude) started
[14:02:01] Review Loop: Round 1: reviewer (opencode) started
[14:03:15] Review Loop: Round 1: claude → APPROVED
[14:04:30] Review Loop: Round 1: opencode → CHANGES_REQUIRED
[14:04:30] Review Loop: Round 1: all reviewers completed → CHANGES_REQUIRED
```

Aggregated verdict is `CHANGES_REQUIRED` (strictest wins). `claude` is recorded as already approved and will be skipped in Round 2.

**Round 2 — reviewer skip optimization:**

```
[14:07:10] Review Loop: Round 2: skipping already-approved reviewers: claude
[14:07:10] Review Loop: Round 2: 1 reviewer(s) (opencode) — parallel
[14:07:10] Review Loop: Round 2: reviewer (opencode) started
[14:08:45] Review Loop: Round 2: opencode → APPROVED
[14:08:45] Review Loop: Round 2: all reviewers completed → APPROVED
```

**Final PR comment:**

```
✅ Review loop complete: APPROVED (opencode=APPROVED)
```

`claude` is counted as previously approved, so the final aggregate is `APPROVED`.

---

### Scenario 3: Daemon Mode (Async Workflow)

Start a background daemon that polls the PR every 30 seconds. The implementer can work across multiple sessions.

```
$ /reviewloop 42 --mode=daemon --reviewer=claude
```

**Daemon start output:**

```
Daemon started (PID: 18432)
Log: ~/.claude/plugins/reviewloop/Users-alice-myapp/feat-add-validation/reviewloop-daemon.log
```

**Daemon log (`reviewloop-daemon.log`):**

```
[2026-03-19T14:00:01+09:00] Daemon started for PR #42 (alice/myapp)
[2026-03-19T14:00:01+09:00] Baseline SHA: a1b2c3d4
[2026-03-19T14:00:31+09:00] (no new commits — polling)
[2026-03-19T14:01:01+09:00] (no new commits — polling)
[2026-03-19T14:05:47+09:00] New commit detected: e5f6a7b8 (was: a1b2c3d4)
[2026-03-19T14:05:47+09:00] Review round complete
[2026-03-19T14:09:22+09:00] New commit detected: c9d0e1f2 (was: e5f6a7b8)
[2026-03-19T14:09:22+09:00] Review round complete
[2026-03-19T14:09:22+09:00] Phase is 'approved', stopping daemon
[2026-03-19T14:09:22+09:00] Daemon stopped
```

The daemon continues running after the current session ends. To cancel it manually:

```
$ /reviewloop cancel
```

---

## Configuration

Edit [`config.yaml`](config.yaml) to customize the review loop behavior.

### Agent Registry

Register reviewer agents under the `agents` key. Each agent defines a CLI command, prompt delivery mode, and availability check:

```yaml
agents:
  claude:
    enabled: true
    command: "claude -p --output-format=text --permission-mode=plan"
    prompt_mode: stdin      # stdin | arg | file
    timeout: 600
    check: "which claude"
    description: "Claude Code"
```

### Defaults

```yaml
defaults:
  mode: inline              # inline | daemon | hook
  reviewer: all             # "all" or comma-separated: "claude,opencode"
  max_rounds: 5
  review_strategy: parallel # parallel | sequential
  same_issue_threshold: 2   # same findings N times → force stop
```

### Prompt Templates

Customize review prompts via the `prompts` key: `preamble`, `diff_review`, `holistic_review`, `verdict_instructions`. Templates support variables like `{pr_number}`, `{round}`, `{pr_diff}`, `{custom_context}`.

## Documentation

See [SKILL.md](SKILL.md) for the full protocol specification, state file format, termination conditions, and integration details.
