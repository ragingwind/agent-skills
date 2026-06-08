#!/usr/bin/env bash
# Pre-commit comment audit — blocks `git commit` when the staged diff adds
# source-code comments matching the forbidden patterns set (time-rotting
# words, rule-path citations, what-narration, etc.).
#
# Operates on the staged diff (--cached, --unified=0). For each added comment
# line in a source file, runs the forbidden-pattern set. Any match → deny
# with the offending file:line and the matched class.
#
# Bypass: CLAUDE_COMMENT_AUDIT_SKIP=1 (logged to events.jsonl when available).
#
# Trigger: PreToolUse:Bash (command contains "git commit")
set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$COMMAND" ] && exit 0

# Only match git commit commands
echo "$COMMAND" | grep -qE 'git[[:space:]]+commit' || exit 0

# Skip merge commits and amend-only-message
echo "$COMMAND" | grep -qE -- '--allow-empty|--amend([[:space:]]|$).*--no-edit' && exit 0

# Emergency skip (logged)
if [ "${CLAUDE_COMMENT_AUDIT_SKIP:-0}" = "1" ]; then
  if . "${CLAUDE_PLUGIN_ROOT}/scripts/events.sh" 2>/dev/null \
     && _sd=$(events_state_dir 2>/dev/null) && [ -d "$_sd" ] && [ -f "$_sd/events.jsonl" ]; then
    _tid=$( { events_latest "$_sd" init 2>/dev/null || true; } | jq -r '.task_id // "unknown"' 2>/dev/null || echo "unknown")
    events_emit_gate_skipped "$_sd" "${_tid:-unknown}" "pre-bash-comment-audit" "CLAUDE_COMMENT_AUDIT_SKIP" \
      "$(printf '%s' "$COMMAND" | head -c 200)" 2>/dev/null || true
  fi
  echo "pre-bash-comment-audit: CLAUDE_COMMENT_AUDIT_SKIP=1 — skipping comment audit (logged to events.jsonl if available)" >&2
  exit 0
fi

git rev-parse --show-toplevel >/dev/null 2>&1 || exit 0
REPO_ROOT=$(git rev-parse --show-toplevel)

DIFF=$(cd "$REPO_ROOT" && git diff --cached --no-color --unified=0 -- \
  '*.ts' '*.tsx' '*.js' '*.jsx' '*.mjs' '*.cjs' \
  '*.py' '*.go' '*.rs' '*.java' '*.rb' '*.php' \
  '*.swift' '*.kt' '*.c' '*.cc' '*.cpp' '*.h' '*.hpp' '*.cs' \
  '*.sh' '*.bash' '*.zsh' 2>/dev/null || true)
[ -z "$DIFF" ] && exit 0

VIOLATIONS=$(printf '%s\n' "$DIFF" | awk '
function is_shell_file(f) {
  return (f ~ /\.(sh|bash|zsh|py|rb)$/)
}
function is_comment_line(line, file,    t) {
  t = line
  sub(/^[ \t]+/, "", t)
  if (t ~ /^\/\//) return 1
  if (t ~ /^\/\*/) return 1
  if (t ~ /^\*[^\/]/) return 1
  if (t ~ /^\*\/$/) return 1
  if (is_shell_file(file) && t ~ /^#/) return 1
  if (file ~ /\.py$/ && (t ~ /^"""/ || t ~ /^\x27\x27\x27/)) return 1
  return 0
}
function classify(line,   t, lower) {
  t = line; sub(/^[ \t]+/, "", t)
  lower = tolower(t)
  if (t ~ /Phase[ \t]+[0-9]+/) return "Phase N"
  if (lower ~ /iteration[ \t]+[0-9]+/) return "iteration N"
  if (t ~ /Plan[ \t]+v[0-9]+/) return "Plan vN"
  if (lower ~ /review[ \t]+[hcmq]+-?[0-9]+/) return "review HN/CN"
  if (t ~ /(QC|QH)-[0-9]+/) return "QC-N/QH-N"
  if (t ~ /(^|[^A-Za-z0-9_])[HC]-[0-9]+([^A-Za-z0-9_]|$)/) return "H-N/C-N"
  if (t ~ /PR[ \t]*#[0-9]+/) return "PR #N"
  if (lower ~ /issue[ \t]*#[0-9]+/) return "issue #N"
  if (lower ~ /post-?fix/) return "post-fix"
  if (lower ~ /carryover/) return "carryover"
  if (lower ~ /follow-up/) return "follow-up"
  if (t ~ /(rules|commands|agents|skills)\/([A-Za-z0-9_.-]+\/)*[A-Za-z0-9_.-]+\.md/) return "rule-path citation"
  if (t ~ /VERIFY BEFORE ABSTRACT/) return "rule phrase: VERIFY BEFORE ABSTRACT"
  if (t ~ /Planner[^A-Za-z]+Reviewer/) return "rule phrase: Planner != Reviewer"
  if (t ~ /Real-environment principle/) return "rule phrase: Real-environment principle"
  if (t ~ /Three-Group Taxonomy/) return "rule phrase: Three-Group Taxonomy"
  return ""
}
/^diff --git/ {
  if (match($0, /[ \t]b\/[^ \t]+/)) {
    current_file = substr($0, RSTART+3, RLENGTH-3)
  }
  current_line = 0
  next
}
/^\+\+\+ / { next }
/^--- / { next }
/^@@ / {
  if (match($0, /\+[0-9]+/)) {
    current_line = substr($0, RSTART+1, RLENGTH-1) + 0
  }
  next
}
/^\+/ {
  added = substr($0, 2)
  if (current_file != "" && is_comment_line(added, current_file)) {
    bad = classify(added)
    if (bad != "") {
      gsub(/^[ \t]+/, "", added)
      printf("  %s:%d  [%s]  %s\n", current_file, current_line, bad, added)
    }
  }
  current_line += 1
  next
}
/^-/ { next }
{ next }
')

if [ -n "$VIOLATIONS" ]; then
  MSG=$'BLOCKED: rules/code-comments.md violations in staged comments.\n\n'
  MSG+="$VIOLATIONS"$'\n\n'
  MSG+=$'Move the rationale to the commit message or PR description.\nBypass (logged): CLAUDE_COMMENT_AUDIT_SKIP=1 git commit ...'
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":%s}}\n' \
    "$(printf '%s' "$MSG" | jq -Rs .)"
  exit 0
fi

exit 0
