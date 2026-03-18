#!/usr/bin/env bash
# Review Loop Stop Hook — intercepts Stop events to run review engine.
# If no review loop is active, passes through (approve).
set -euo pipefail

INPUT=$(cat)

# Prevent infinite recursion: if stop_hook_active, approve immediately
ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)
[ "$ACTIVE" = "true" ] && printf '{"decision":"approve"}\n' && exit 0

# Determine working directory
CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
[ -z "$CWD" ] && CWD=$(pwd)

# Per-project, per-branch state file under ~/.claude/plugins/reviewloop/
BRANCH=$(git -C "$CWD" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "default")
BRANCH_SLUG=$(echo "$BRANCH" | sed 's/[^a-zA-Z0-9._-]/-/g')
PROJECT_SLUG=$(echo "$CWD" | sed 's|^/||; s|[^a-zA-Z0-9._-]|-|g')
STATE="$HOME/.claude/plugins/reviewloop/$PROJECT_SLUG/$BRANCH_SLUG/review-loop.local.md"
[ ! -f "$STATE" ] && printf '{"decision":"approve"}\n' && exit 0

# Check if loop is active (quick grep of frontmatter)
if ! grep -q '^active: true' "$STATE" 2>/dev/null; then
  printf '{"decision":"approve"}\n'
  exit 0
fi

# Inline mode: engine is called directly within the session, stop hook is no-op
MODE=$(grep '^mode:' "$STATE" 2>/dev/null | awk '{print $2}')
[ "$MODE" = "inline" ] && printf '{"decision":"approve"}\n' && exit 0

# Resolve plugin root (works with both plugin install and direct path)
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")" && pwd)}"

# Delegate to the engine
exec python3 "$PLUGIN_ROOT/engine.py" <<< "$INPUT"
