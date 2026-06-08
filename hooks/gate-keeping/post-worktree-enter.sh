#!/usr/bin/env bash
# PostToolUse:EnterWorktree hook — .env.local symlink setup
# Runs after Claude Code creates/enters a worktree
set -euo pipefail

input=$(cat || true)
tool_name=$(echo "$input" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_name',''))" 2>/dev/null || true)

# Only run for EnterWorktree
if [ "$tool_name" != "EnterWorktree" ]; then
  exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0

# Resolve main repo root for .env.local symlink
_GIT_COMMON=$(git rev-parse --git-common-dir 2>/dev/null)
if [[ "$_GIT_COMMON" == /* ]]; then
  MAIN_ROOT=$(dirname "$_GIT_COMMON")
else
  MAIN_ROOT="$REPO_ROOT"
fi

# Create .env.local symlink if it exists in the main root but not in worktree
if [ "$REPO_ROOT" != "$MAIN_ROOT" ] && [ -f "$MAIN_ROOT/.env.local" ] && [ ! -f "$REPO_ROOT/.env.local" ]; then
  ln -sf "$MAIN_ROOT/.env.local" "$REPO_ROOT/.env.local" 2>/dev/null || true
fi
