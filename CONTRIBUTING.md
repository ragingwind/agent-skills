# Contributing

Thanks for helping grow this skill library. This guide covers how to add or
change a skill.

## Adding a skill

1. Create a directory under `skills/<skill-name>/` — names are kebab-case.
2. Add a `SKILL.md`, the single entry point for the skill.
3. Optionally add supporting scripts or reference files alongside it.

## SKILL.md format

Every `SKILL.md` starts with YAML frontmatter followed by the instructions the
agent should follow:

```yaml
---
name: my-skill            # required — kebab-case, matches the directory
description: One line ...  # required — when to use the skill and what it does
user-invocable: true      # optional — exposes it as /my-skill
argument-hint: "[path]"   # optional — shown next to the slash command
---
```

After the frontmatter, write:

- a short purpose line,
- the instructions (inputs, steps, and the expected output),
- examples (optional).

Keep `SKILL.md` itself in English. If a skill produces user-facing output,
state its output-language policy explicitly in the instructions.

## Scripts

- Shell scripts must be POSIX-compatible or explicitly require bash.
- Make them executable (`chmod +x`).
- Use `${CLAUDE_PLUGIN_ROOT}` for paths inside the plugin.

## Before opening a PR

- Run `bash scripts/validate-skills.sh` and make sure it passes.
- Update the skill tables in `README.md` and `CLAUDE.md` if you added or
  renamed a skill.
- Use Conventional Commit messages (`feat:`, `fix:`, `docs:`, …).
