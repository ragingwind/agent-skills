#!/usr/bin/env bash
# PostToolUse:ExitWorktree hook — clean up work-directory artifacts
# Runs after Claude Code exits/removes a worktree
set -euo pipefail

input=$(cat || true)
tool_name=$(echo "$input" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_name',''))" 2>/dev/null || true)

# Only run for ExitWorktree
if [ "$tool_name" != "ExitWorktree" ]; then
  exit 0
fi

worktree_path=$(echo "$input" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('path',''))" 2>/dev/null || true)

if [ -z "$worktree_path" ] || [ ! -d "$worktree_path" ]; then
  exit 0
fi

# Clean up work directory artifacts
BRANCH_NAME=$(git -C "$worktree_path" branch --show-current 2>/dev/null || true)
if [ -n "$BRANCH_NAME" ]; then
  source ~/.claude/scripts/project-paths.sh "$worktree_path" 2>/dev/null || true
  rm -rf "${TESTS:-}" "${GATES_DIR:-}" 2>/dev/null || true
fi
