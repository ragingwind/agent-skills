#!/usr/bin/env bash
# Session start hook — loads the meta-skill if available

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-.}"
META_SKILL="$PLUGIN_ROOT/skills/using-agent-skills/SKILL.md"

if [ -f "$META_SKILL" ]; then
  cat "$META_SKILL"
else
  echo "[INFO] Meta-skill not found at $META_SKILL. Add skills/using-agent-skills/SKILL.md to enable session-start guidance."
fi
