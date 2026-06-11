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

## Pipelines

Slash commands that orchestrate the multi-agent pipeline (`.claude/commands/`):

| Command | Description |
|---------|-------------|
| [dev](.claude/commands/dev.md) | Development pipeline — plan, build, review, verify, evidence, finalize |
| [qa](.claude/commands/qa.md) | QA pipeline — plan, full QA, finalize |
| [epic](.claude/commands/epic.md) | Epic pipeline — sub-issue dispatch + QA + final PR |
| [fix](.claude/commands/fix.md) | Lightweight fix track — issue intake, fix branch, draft PR |
| [plan-dev](.claude/commands/plan-dev.md) | Standalone dev plan posted as an issue comment (break-point) |
| [plan-qa](.claude/commands/plan-qa.md) | Standalone QA plan posted as an issue comment (break-point) |
| [ralph](.claude/commands/ralph.md) | Retry loop primitive — execute/verify/fix/repeat with capped termination |
| [swarm](.claude/commands/swarm.md) | Parallel execution with model routing |

## Agents

Personas dispatched by the pipelines (`agents/`):

| Agent | Role |
|-------|------|
| [builder](agents/builder.md) | Implementation + dev testing (Build mode) + TIA (Verify mode) |
| [reviewer](agents/reviewer.md) | Code review, security audit, qa-plan review |
| [tester](agents/tester.md) | Full QA — scenarios, evidence, release gate |
| [debugger](agents/debugger.md) | Forensic bug investigation |

## Skills

Each skill lives in `skills/<skill-name>/SKILL.md`.

**Orchestration & quality**

| Skill | Description |
|-------|-------------|
| [planning-features](skills/planning-features/) | Dev implementation roadmaps (`--mode dev`) and QA scenario plans (`--mode qa`) |
| [parallel](skills/parallel/) | Parallel, pipeline, team, and swarm execution modes |
| [review](skills/review/) | Code review with severity-rated findings |
| [analyze](skills/analyze/) | Deep code analysis and codebase exploration |
| [tdd](skills/tdd/) | Test-first workflow with Red-Green-Refactor gates |
| [triage](skills/triage/) | Issue evaluation, label management, and label sync |
| [cleanup](skills/cleanup/) | Clean up stale worktrees and orphan state dirs |
| [release](skills/release/) | Version bump, changelog, git tag, GitHub release |
| [upload-evidence](skills/upload-evidence/) | Upload browser test evidence and post as a PR comment |

**Browser & E2E verification**

| Skill | Description |
|-------|-------------|
| [agent-browser](skills/agent-browser/) | Playwright-based headless browser automation CLI |
| [playwright](skills/playwright/) | Playwright E2E testing — API, auth, assertions, commands |
| [e2e](skills/e2e/) | E2E test authoring — design, structure, implement, verify |
| [chrome-for-claude](skills/chrome-for-claude/) | Chrome integration — live debugging, authed testing, recording |

**Web & frontend**

| Skill | Description |
|-------|-------------|
| [web-development](skills/web-development/) | Web review guidelines — React/Next.js, TS, CSS, a11y |
| [web-design-guidelines](skills/web-design-guidelines/) | Review UI code for Web Interface Guidelines compliance |
| [web-frontend-design](skills/web-frontend-design/) | Create distinctive, production-grade frontend interfaces |
| [vercel-react-best-practices](skills/vercel-react-best-practices/) | React/Next.js performance guidelines from Vercel |
| [architecture](skills/architecture/) | Generate ARCHITECTURE.md by analyzing project structure |

**Language & framework experts**

| Skill | Description |
|-------|-------------|
| [python](skills/python/) | Idiomatic Python — decorators, generators, async/await |
| [rustlang](skills/rustlang/) | Idiomatic Rust — ownership, lifetimes, trait impls |
| [prosemirror](skills/prosemirror/) | ProseMirror rich text editor expert |
| [monaco-editor](skills/monaco-editor/) | Monaco Editor development expert |

**Utilities**

| Skill | Description |
|-------|-------------|
| [vscode](skills/vscode/) | Open VS Code at the current working directory |
| [ghostty-split](skills/ghostty-split/) | Ghostty terminal split helper |
| [browse-terminal](skills/browse-terminal/) | Open web pages inside the Ghostty terminal |
| [geeknews](skills/geeknews/) | Generate GeekNews-style Korean tech summaries |

## Usage

After installation, skills are automatically available in your Claude Code session. Use slash commands or reference skills directly in your prompts.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on adding new skills.

## License

[MIT](LICENSE)
