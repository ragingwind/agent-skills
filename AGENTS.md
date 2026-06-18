# ragingwind/agent-skills — execution contract

Multi-agent orchestration skills for AI coding agents — autonomous pipelines,
parallel execution, and self-healing loops.

This file is the **self-contained contract for agents without a native harness**
(Codex, Cursor, Copilot, Windsurf, Amp, Devin, Gemini CLI). It inlines what a
harness would otherwise surface automatically: the intent→skill mapping, how to
invoke each asset, the pipeline lifecycle, and the skill-authoring guide. Agents
**with** a native harness should read `CLAUDE.md` instead — it is intentionally a
thin pointer because the harness already provides what follows.

> Shared facts (layout, conventions, boundaries) are kept in sync with `CLAUDE.md`.
> If you change one, change both.

## How to use this repo without a harness

Nothing here is auto-loaded for you. To act on an asset, open its file and follow it:

- **Skill** — read `skills/<name>/SKILL.md` and follow its instructions. The
  frontmatter `description` is the trigger; the body is the procedure.
- **Slash command** (`/dev`, `/qa`, …) — read `commands/<name>.md` and execute the
  pipeline it describes, in order. Commands orchestrate skills and agents.
- **Agent / persona** — read `agents/<name>.md` and adopt that role's posture and
  constraints for the delegated sub-task.
- **Rule** — `rules/*.md` are shared constraints referenced by the above. Honor any
  rule a command/skill/agent cites.

Plugin-internal asset paths are written as `${CLAUDE_PLUGIN_ROOT}/...`; resolve that
to this repo's root. Genuine runtime state lives under
`$HOME/.local/state/agent-skills/...`.

## Intent → skill mapping

When the user's intent matches a row, read that `SKILL.md` and follow it.

### Orchestration & quality
| Intent | Skill |
|--------|-------|
| Plan an implementation roadmap or QA scenario plan | `planning-features` (`--mode dev` / `--mode qa`) |
| Run work in parallel / pipeline / team / swarm | `parallel` |
| Review code with severity-rated findings | `review` |
| Deep code analysis / codebase exploration | `analyze` |
| Test-first development (Red-Green-Refactor) | `tdd` |
| Evaluate or label issues, sync labels | `triage` |
| Clean up stale worktrees / orphan state dirs | `cleanup` |
| Version bump, changelog, tag, GitHub release | `release` |
| Upload browser-test evidence and post as a PR comment | `upload-evidence` |
| Generate ARCHITECTURE.md from project structure | `architecture` |

### Browser & E2E verification
| Intent | Skill |
|--------|-------|
| Headless, scriptable browser UI verification | `agent-browser` |
| Playwright E2E (API, auth, assertions) | `playwright` |
| Author E2E tests (design → implement → verify) | `e2e` |
| Live debugging / authed testing / recording in Chrome | `chrome-for-claude` |
| Render a web page inside the Ghostty terminal | `browse-terminal` |

### Web & frontend
| Intent | Skill |
|--------|-------|
| Review web code (React/Next.js, TS, CSS, a11y) | `web-development` |
| Audit UI against the Web Interface Guidelines | `web-design-guidelines` |
| Build distinctive, production-grade frontend UI | `web-frontend-design` |
| React/Next.js performance optimization | `vercel-react-best-practices` |

### Language & framework experts
| Intent | Skill |
|--------|-------|
| Idiomatic Python (decorators, generators, async/await) | `python` |
| Idiomatic Rust (ownership, lifetimes, traits) | `rustlang` |
| ProseMirror rich-text editor work | `prosemirror` |
| Monaco / VS Code-style editor work | `monaco-editor` |

### Utilities
| Intent | Skill |
|--------|-------|
| Open VS Code at the working directory | `vscode` |
| GeekNews-style Korean tech summary of a project | `geeknews` |

## Slash commands & pipeline lifecycle

Slash commands orchestrate skills + agents into multi-stage pipelines. Read the
command file for the authoritative steps; the table is the map.

| Command | Pipeline |
|---------|----------|
| `/dev` | plan → build → review → verify → evidence → finalize |
| `/qa` | plan → ENV-AUDIT → full QA → finalize |
| `/epic` | sub-issue dispatch → QA → final PR |
| `/fix` | issue intake (or creation) → fix branch → events.jsonl init → draft PR |
| `/plan-dev` | standalone dev plan, posted as an issue comment (break-point) |
| `/plan-qa` | standalone qa-plan, posted as an issue comment (break-point) |
| `/ralph` | retry-loop primitive: execute → verify → fix → repeat, capped termination |
| `/swarm` | split a task and run the parts concurrently with model routing |

### Lifecycle invariants (from `rules/orchestration.md`)

These are MANDATORY and enforced by gate hooks — not optional conventions:

1. **Writer ≠ approver.** The agent that authors an artifact (dev-plan, qa-plan,
   code, tests) never approves it for the next stage — an independent `reviewer`
   agent does. There is no `--skip-review`. A review loop exits only on `APPROVED`,
   Ralph termination (max 3 cycles → HARD STOP), or user abort.
2. **`events.jsonl` is authoritative.** Each pipeline appends stage events
   (`stage.passed`, `stage.failed`, `plan.posted`, `mirror.posted`) to a state-dir
   `events.jsonl`. Gate hooks (commit / PR / stop) read it to allow or block the
   action. Gates self-skip outside a pipeline branch; emergency bypass is
   `CLAUDE_EVENTS_HOOK_SKIP=1`.
3. **Verify production, not mocks.** Plans, execution, and evidence must reflect the
   real production path. Each scenario emits an evidence file (`.webm`/`.png`) plus a
   `.metadata.json` audit record. A cutover phase (`cutover-phase: true` in plan.md)
   requires ≥1 real-path, non-mock evidence file; `pre-bash-pr-gate.sh` enforces this
   automatically.

## Agents (personas)

Dispatched by the pipelines; read the file before adopting the role.

| Agent | Role |
|-------|------|
| `builder` | Implements features/fixes/tasks from plans. Use PROACTIVELY for implementation. |
| `reviewer` | Final auditor — quality, architecture, performance, security. Analysis only; never modifies code. |
| `tester` | Full QA pipeline — qa-plan, regression, scenarios, evidence, report. Never implements features. |
| `debugger` | Forensic bug investigator — reproduce, diagnose, fix, verify. For bugs that resist simple fixes. |

## Rules (`rules/*.md`)

Shared constraints cited by commands/skills/agents:

- `core.md` — hard rules every agent obeys.
- `orchestration.md` — pipeline invariants (writer≠approver, evidence, cutover).
- `anti-rationalization.md` — guards against rationalizing past the hard rules.
- `code-comments.md` — comment policy.
- `testing.md`, `testing-patterns.md` — testing expectations and patterns.
- `labels.md` — user-local GitHub label catalog (NOT required for pipelines to run).

## Authoring a skill

### SKILL.md format
Each skill is `skills/<kebab-name>/SKILL.md` with:
- **Frontmatter** — `name` and `description`. The `description` is the trigger an
  agent matches against, so make it specific (include the verbs and nouns a user
  would actually say).
- **Body** — freeform markdown describing how the skill works. Common sections:
  Usage, Rules, Process, Input, Output. There is no fixed section set.

### Creating a new skill
1. Create `skills/<skill-name>/` (kebab-case).
2. Add `SKILL.md` with the frontmatter + body above.
3. Optionally add supporting scripts or references in the same directory.

### Script requirements
- POSIX-compatible, or explicitly require bash (`#!/usr/bin/env bash`).
- Executable (`chmod +x`).
- Use `${CLAUDE_PLUGIN_ROOT}` for in-plugin path references; never hardcode
  `~/.claude` or absolute home paths.
