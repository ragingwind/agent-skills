# ragingwind/agent-skills

A library of reusable skills for AI coding agents.

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

## Skills

| Skill | Description |
|-------|-------------|
| [anatomy-project](skills/anatomy-project/) | Analyzes the current project and produces an onboarding guide (architecture, key modules, structure, features, trade-offs) in the user's language. Invoke as `/anatomy-project [path]`. |
| reviewloop | Moved to a standalone repo: [ragingwind/reviewloop](https://github.com/ragingwind/reviewloop) |

## Usage

After installation, skills are automatically available in your Claude Code session. Use slash commands or reference skills directly in your prompts.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on adding new skills.

## License

[MIT](LICENSE)
