#!/usr/bin/env bash
# Watch review loop logs with automatic new-round detection.
# Usage: bash reviewloop-watch.sh [cwd]
#
# Automatically switches to the newest log file when a new round starts.
# Press Ctrl+C to stop.

CWD="${1:-.}"
BRANCH=$(git -C "$CWD" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "default")
BRANCH_SLUG=$(echo "$BRANCH" | sed 's/[^a-zA-Z0-9._-]/-/g')
GLOB="$CWD/.claude/reviewloops/$BRANCH_SLUG/reviewloop-round-*.log"
CURRENT=""

while true; do
  LATEST=$(ls -t $GLOB 2>/dev/null | head -1)

  if [ -z "$LATEST" ]; then
    echo "Waiting for review loop to start..."
    sleep 2
    continue
  fi

  if [ "$LATEST" != "$CURRENT" ]; then
    # Kill previous tail if running
    [ -n "$TAIL_PID" ] && kill "$TAIL_PID" 2>/dev/null
    CURRENT="$LATEST"
    echo ""
    echo "=== Watching: $CURRENT ==="
    tail -f "$CURRENT" &
    TAIL_PID=$!
  fi

  sleep 2
done
