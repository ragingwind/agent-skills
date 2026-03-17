# ragingwind/agent-skills

Multi-agent orchestration skills for AI coding agents — autonomous pipelines, parallel execution, and self-healing loops.

## Installation

### Quick Install via [skills.sh](https://skills.sh)

```bash
npx skills add ragingwind/agent-skills
```

### Claude Code Plugin

```bash
/plugin marketplace add ragingwind/agent-skills
/plugin install ragingwind-agent-skills@ragingwind-agent-skills
```

### Other Editors

See [docs/getting-started.md](docs/getting-started.md) for Cursor, Windsurf, Copilot, and more.

## Directory Structure

```
skills/           — Reusable skill definitions (each with SKILL.md)
agents/           — Agent persona definitions
.claude/commands/ — Slash commands for Claude Code
references/       — Shared checklists and reference materials
hooks/            — Session lifecycle hooks
docs/             — Documentation and guides
.claude-plugin/   — Claude Code marketplace plugin manifests
```

## Skills

| Skill | Description |
|-------|-------------|
| [reviewloop](skills/reviewloop/) | Bidirectional implement/review loop via GitHub PR comments |

## Usage

After installation, skills are automatically available in your Claude Code session. Use slash commands or reference skills directly in your prompts.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on adding new skills.

## License

[MIT](LICENSE)
