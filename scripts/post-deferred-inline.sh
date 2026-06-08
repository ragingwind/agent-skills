#!/usr/bin/env bash
# Post deferred inline comments from a /dev review report to a PR.
#
# Reads `## Deferred Inline Comments` table from the review report and posts
# each row as a line comment on the given PR + commit. Idempotent within a
# single run (does NOT dedupe against existing comments — re-runs will
# duplicate; gate the call site to once-per-review-cycle).
#
# Usage: post-deferred-inline.sh <review-report.md> <pr-num> <repo> <commit-sha>
#
# Expected table shape:
#   ## Deferred Inline Comments
#   | # | File | Line | Severity | Comment |
#   |---|------|------|----------|---------|
#   | 1 | `path/to/file.ts` | 42 | 🔴 CRITICAL | **Why:** ... |
#
# Silent no-op when:
#   - Report file missing
#   - Section header not found
#   - Section has no data rows (only header + separator)
set -euo pipefail

REPORT="${1:?review report path}"
PR="${2:?pr number}"
REPO="${3:?owner/repo}"
COMMIT="${4:?commit sha}"

[ -f "$REPORT" ] || { echo "post-deferred-inline: $REPORT not found, skipping" >&2; exit 0; }

# Extract the section between '## Deferred Inline Comments' and the next '## ' header
SECTION=$(awk '
  /^## Deferred Inline Comments/ { capture=1; next }
  capture && /^## / { exit }
  capture { print }
' "$REPORT")

if [ -z "$SECTION" ]; then
  echo "post-deferred-inline: no Deferred Inline Comments section, skipping" >&2
  exit 0
fi

# Parse data rows: "| N | `file` | line | severity | body |"
# Skip header row (matches "File") and separator (matches "---")
POSTED=0
while IFS= read -r ROW; do
  [[ "$ROW" =~ ^\|[[:space:]]*[0-9]+[[:space:]]*\| ]] || continue

  FILE=$(echo "$ROW" | awk -F'|' '{print $3}' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/^`//;s/`$//')
  LINE=$(echo "$ROW" | awk -F'|' '{print $4}' | sed 's/[^0-9]//g')
  SEVERITY=$(echo "$ROW" | awk -F'|' '{print $5}' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  BODY=$(echo "$ROW" | awk -F'|' '{
    out=""
    for (i=6; i<=NF-1; i++) { out = out (i==6 ? "" : "|") $i }
    print out
  }' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

  [ -z "$FILE" ] || [ -z "$LINE" ] || [ -z "$BODY" ] && continue

  FULL_BODY="**${SEVERITY}** ${BODY}"
  if gh api -X POST "repos/$REPO/pulls/$PR/comments" \
       -f body="$FULL_BODY" \
       -f commit_id="$COMMIT" \
       -f path="$FILE" \
       -F line="$LINE" \
       -f side="RIGHT" \
       --jq '.html_url' >/dev/null 2>&1; then
    POSTED=$((POSTED + 1))
  else
    echo "post-deferred-inline: failed to post comment for $FILE:$LINE" >&2
  fi
done <<< "$SECTION"

echo "post-deferred-inline: posted $POSTED inline comment(s) for PR #$PR"
