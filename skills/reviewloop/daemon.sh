#!/usr/bin/env bash
# Review Loop Daemon — background PR polling for automatic review.
# Usage: daemon.sh start|stop|status <state-file-path>
#
# Polls the PR HEAD sha every 30s. When a new commit is detected,
# invokes engine.py to run a review round. Auto-stops on approval
# or max_rounds.
set -euo pipefail

ACTION="${1:-}"
STATE_FILE="${2:-}"

if [ -z "$ACTION" ] || [ -z "$STATE_FILE" ]; then
  echo "Usage: daemon.sh start|stop|status <state-file-path>"
  exit 1
fi

# Derive PID file from PR number
PR_NUMBER=$(grep '^pr_number:' "$STATE_FILE" 2>/dev/null | awk '{print $2}')
PID_FILE="/tmp/.claude-reviewloop-${PR_NUMBER:-unknown}.pid"

# Plugin root (for engine.py location)
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")" && pwd)}"

case "$ACTION" in
  start)
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "Daemon already running (PID: $(cat "$PID_FILE"))"
      exit 0
    fi

    # Read state fields
    REPO=$(grep '^repo:' "$STATE_FILE" 2>/dev/null | awk '{print $2}')
    # State is at ~/.claude/plugins/reviewloop/<project>/<branch>/review-loop.local.md
    # CWD is stored in the state file frontmatter
    CWD=$(grep '^cwd:' "$STATE_FILE" 2>/dev/null | sed 's/^cwd: *//')

    if [ -z "$PR_NUMBER" ] || [ -z "$REPO" ]; then
      echo "Error: cannot read pr_number/repo from state file"
      exit 1
    fi

    # Get current HEAD sha as baseline
    LAST_SHA=$(gh api "repos/$REPO/pulls/$PR_NUMBER" --jq .head.sha 2>/dev/null || echo "")
    if [ -z "$LAST_SHA" ]; then
      echo "Error: cannot fetch PR HEAD sha"
      exit 1
    fi

    # Update state with daemon tracking fields
    # (uses python for reliable YAML update)
    python3 -c "
import sys, re, yaml
state_path = sys.argv[1]
with open(state_path) as f:
    content = f.read()
m = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
if m:
    state = yaml.safe_load(m.group(1))
    state['last_reviewed_sha'] = sys.argv[2]
    state['daemon_pid'] = int(sys.argv[3])
    fm = yaml.dump(state, default_flow_style=False, allow_unicode=True)
    with open(state_path, 'w') as f:
        f.write(f'---\n{fm}---\n')
" "$STATE_FILE" "$LAST_SHA" "$$"

    RLDIR=$(dirname "$STATE_FILE")  # ~/.claude/plugins/reviewloop/<project>/<branch>
    LOG_FILE="$RLDIR/reviewloop-daemon.log"

    # Background polling loop
    (
      echo "[$(date -Iseconds)] Daemon started for PR #$PR_NUMBER ($REPO)" >> "$LOG_FILE"
      echo "[$(date -Iseconds)] Baseline SHA: $LAST_SHA" >> "$LOG_FILE"

      while true; do
        sleep 30

        # Check if state file still exists and is active
        if [ ! -f "$STATE_FILE" ] || ! grep -q '^active: true' "$STATE_FILE" 2>/dev/null; then
          echo "[$(date -Iseconds)] State file inactive or missing, stopping daemon" >> "$LOG_FILE"
          break
        fi

        # Check if already approved/max_rounds/error
        PHASE=$(grep '^phase:' "$STATE_FILE" 2>/dev/null | awk '{print $2}')
        if [ "$PHASE" = "approved" ] || [ "$PHASE" = "max_rounds" ] || [ "$PHASE" = "disagreement" ]; then
          echo "[$(date -Iseconds)] Phase is '$PHASE', stopping daemon" >> "$LOG_FILE"
          break
        fi

        # Poll for new commits
        NEW_SHA=$(gh api "repos/$REPO/pulls/$PR_NUMBER" --jq .head.sha 2>/dev/null || echo "")
        if [ -z "$NEW_SHA" ]; then
          echo "[$(date -Iseconds)] Warning: failed to fetch PR HEAD sha" >> "$LOG_FILE"
          continue
        fi

        if [ "$NEW_SHA" = "$LAST_SHA" ]; then
          continue  # No new commits
        fi

        echo "[$(date -Iseconds)] New commit detected: $NEW_SHA (was: $LAST_SHA)" >> "$LOG_FILE"
        LAST_SHA="$NEW_SHA"

        # Update last_reviewed_sha in state
        python3 -c "
import sys, re, yaml
state_path = sys.argv[1]
with open(state_path) as f:
    content = f.read()
m = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
if m:
    state = yaml.safe_load(m.group(1))
    state['last_reviewed_sha'] = sys.argv[2]
    fm = yaml.dump(state, default_flow_style=False, allow_unicode=True)
    with open(state_path, 'w') as f:
        f.write(f'---\n{fm}---\n')
" "$STATE_FILE" "$NEW_SHA"

        # Invoke engine via stdin (hook mode — daemon uses the standard path)
        echo "{\"cwd\":\"$CWD\"}" | python3 "$PLUGIN_ROOT/engine.py" >> "$LOG_FILE" 2>&1 || true

        echo "[$(date -Iseconds)] Review round complete" >> "$LOG_FILE"
      done

      echo "[$(date -Iseconds)] Daemon stopped" >> "$LOG_FILE"
      rm -f "$PID_FILE"
    ) &

    DAEMON_PID=$!
    echo "$DAEMON_PID" > "$PID_FILE"

    # Update PID in state file
    python3 -c "
import sys, re, yaml
state_path = sys.argv[1]
with open(state_path) as f:
    content = f.read()
m = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
if m:
    state = yaml.safe_load(m.group(1))
    state['daemon_pid'] = int(sys.argv[2])
    fm = yaml.dump(state, default_flow_style=False, allow_unicode=True)
    with open(state_path, 'w') as f:
        f.write(f'---\n{fm}---\n')
" "$STATE_FILE" "$DAEMON_PID"

    echo "Daemon started (PID: $DAEMON_PID)"
    echo "Log: $LOG_FILE"
    ;;

  stop)
    if [ -f "$PID_FILE" ]; then
      PID=$(cat "$PID_FILE")
      if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null
        echo "Daemon stopped (PID: $PID)"
      else
        echo "Daemon not running (stale PID file)"
      fi
      rm -f "$PID_FILE"
    else
      echo "No daemon PID file found"
    fi
    ;;

  status)
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "Running (PID: $(cat "$PID_FILE"))"
    else
      echo "Not running"
    fi
    ;;

  *)
    echo "Unknown action: $ACTION"
    echo "Usage: daemon.sh start|stop|status <state-file-path>"
    exit 1
    ;;
esac
