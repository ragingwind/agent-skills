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

### Development (local testing)

Load the plugin directly from a local clone without installing:

```bash
git clone https://github.com/ragingwind/agent-skills.git
claude --plugin-dir ./agent-skills
```

After making changes, run `/reload-plugins` inside the session to pick them up without restarting.

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

Edit `config.yaml` to register reviewer agents and customize prompt templates.

## Documentation

See [SKILL.md](SKILL.md) for the full protocol specification, state file format, termination conditions, and integration details.
