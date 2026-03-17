# Contributing

## Adding a New Skill

1. Create `skills/<skill-name>/SKILL.md`
2. Follow the SKILL.md format spec in `docs/skill-anatomy.md`
3. Add a brief entry in `CLAUDE.md` under the appropriate category
4. Submit a pull request

## Skill Quality Bar

- Skill must have a clear, single purpose
- Instructions must be actionable and unambiguous
- Must not duplicate existing skills

## Structure

```
skills/<skill-name>/
├── SKILL.md          # Required — skill definition
├── scripts/          # Optional — supporting scripts
└── references/       # Optional — skill-specific references
```

## What Not to Do

- Do not add skills that require external API keys without documenting it
- Do not add overly broad or vague skills
- Do not modify other skills in the same PR
- Do not add dependencies on specific frameworks unless the skill is framework-specific
