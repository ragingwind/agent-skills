# Agents Guide

## Repository Overview

This repository contains reusable skills, agent personas, and slash commands for AI coding agents. It is designed as a shared skill library installable via Claude Code marketplace.

## Creating a New Skill

1. Create a directory under `skills/<skill-name>/`
2. Add a `SKILL.md` file following the standard format
3. Optionally add supporting scripts or references

## SKILL.md Format

Each skill must have a `SKILL.md` with:
- Frontmatter (name, description, version)
- Purpose section
- Instructions section
- Examples section (optional)

See `docs/skill-anatomy.md` for the full specification.

## Script Requirements

- All shell scripts must be POSIX-compatible or explicitly require bash
- Scripts must be executable (`chmod +x`)
- Use `${CLAUDE_PLUGIN_ROOT}` for path references within the plugin
