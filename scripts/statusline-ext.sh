#!/usr/bin/env bash
# Dev server status segment for Claude Code statusline
# Args: $1=project_root, $2=project_key, $3=cwd (actual Claude working directory, e.g. worktree path)
#
# Discovers running portless dev servers for the current branch via `portless list`.
# No project-specific configuration needed.
PROJECT_ROOT="$1"
PROJECT_KEY="$2"
CWD="${3:-$PROJECT_ROOT}"

# Derive branch slug from cwd
BRANCH=$(git -C "$CWD" branch --show-current 2>/dev/null | sed 's|/|-|g; s|\.|_|g' | cut -c1-40)
[ -z "$BRANCH" ] && exit 0

# ANSI colors
R=$'\033[0m'
D=$'\033[2m'
GR=$'\033[32m'

# 5s TTL cache (per worktree, not project-wide)
CACHE="/tmp/.claude-dev-statusline-${PROJECT_KEY}-${BRANCH}"
if [ -f "$CACHE" ]; then
  mtime=$(stat -f %m "$CACHE" 2>/dev/null || stat -c %Y "$CACHE" 2>/dev/null)
  if [ -n "$mtime" ]; then
    age=$(( $(date +%s) - mtime ))
    [ "$age" -lt 5 ] && { cat "$CACHE"; exit 0; }
  fi
fi

# Discover portless route whose app name starts with the branch slug
URL=$(portless list 2>/dev/null | grep -oE "http://${BRANCH}[^[:space:]]+" | head -1)
if [ -z "$URL" ]; then
  printf '' > "$CACHE"
  exit 0
fi

# Quick liveness check (2s timeout)
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "$URL" 2>/dev/null || echo 000)
case "$code" in
  000|502|503)
    printf '' > "$CACHE"
    exit 0 ;;
esac

# Display name: strip protocol and .localhost suffix (e.g. "feat-chat-ui.dol")
DISPLAY=$(printf '%s' "$URL" | sed 's|http://||; s|\.localhost.*||')

# OSC 8 hyperlink — display: app name, link: portless URL
link=$'\033]8;;'"${URL}"$'\033\\'"${DISPLAY}"$'\033]8;;\033\\'
out="⚡${D}Dev:${R}${GR}${link}${R}"
printf '%s' "$out" > "$CACHE"
printf '%s' "$out"
