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

## Configuration

Edit [`config.yaml`](config.yaml) to customize the review loop behavior. The file is located in the skill installation directory (e.g., `~/.claude/skills/reviewloop/config.yaml`).

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
