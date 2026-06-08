#!/usr/bin/env bash
# Claude Code statusLine — single line, left-aligned
# Format: feat/auth · (#42) · PR #325 · 12k/200k · Sonnet 4.6 (43%)

input=$(cat)

# Colors
R=$'\033[0m'
D=$'\033[2m'
CY=$'\033[36m'
GR=$'\033[32m'
YL=$'\033[33m'
RD=$'\033[31m'
MG=$'\033[35m'

SEP="${D}·${R}"

# ── Parse input ─────────────────────────────────────────────────
model=$(echo "$input" | jq -r '.model.display_name // "?"' | sed 's/^Claude //')
used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
cwd=$(echo "$input" | jq -r '.cwd // ""')
transcript_path=$(echo "$input" | jq -r '.transcript_path // ""')

# ── Absolute token count ─────────────────────────────────────────
tok_display=""
input_tokens=$(echo "$input" | jq -r '.context_window.current_usage.input_tokens // 0')
cache_create=$(echo "$input" | jq -r '.context_window.current_usage.cache_creation_input_tokens // 0')
cache_read=$(echo "$input" | jq -r '.context_window.current_usage.cache_read_input_tokens // 0')
ctx_size=$(echo "$input" | jq -r '.context_window.context_window_size // 0')
total_tokens=$(( input_tokens + cache_create + cache_read ))

fmt_k() {
  local n=$1
  if [ "$n" -ge 1000 ]; then
    printf "%dk" $(( n / 1000 ))
  else
    printf "%d" "$n"
  fi
}

if [ "$ctx_size" -gt 0 ]; then
  tok_display="$(fmt_k "$total_tokens")/$(fmt_k "$ctx_size")"
fi

# ── Git info ────────────────────────────────────────────────────
branch=""
worktree_name=""
staged=0
modified=0

if [ -n "$cwd" ] && git -C "$cwd" rev-parse --git-dir > /dev/null 2>&1; then
  branch=$(git -C "$cwd" symbolic-ref --short HEAD 2>/dev/null \
        || git -C "$cwd" rev-parse --short HEAD 2>/dev/null)
  branch_display=$(echo "$branch" | sed 's|^worktree-||')

  abs_git_dir=$(git -C "$cwd" rev-parse --absolute-git-dir 2>/dev/null)
  if echo "$abs_git_dir" | grep -q '/worktrees/'; then
    worktree_name=$(echo "$abs_git_dir" | sed 's|.*/worktrees/||; s|^worktree-||')
    [ "$worktree_name" = "$branch_display" ] && worktree_name=""
  fi

  st=$(git -C "$cwd" --no-optional-locks status --porcelain 2>/dev/null)
  staged=$(echo "$st"   | grep -c '^[MADRC]' 2>/dev/null); staged=${staged:-0}
  modified=$(echo "$st" | grep -c '^.[MD]'   2>/dev/null); modified=${modified:-0}
fi

# ── Shared computed vars ─────────────────────────────────────────
branch_safe=""
project_root=""
project_key=""

if [ -n "$branch" ]; then
  branch_safe=$(echo "$branch" | tr '/' '_' | tr -cd '[:alnum:]_-')

  # Resolve project root: worktrees return absolute git-common-dir; main repo returns relative ".git"
  git_common_dir=$(git -C "$cwd" rev-parse --git-common-dir 2>/dev/null)
  case "$git_common_dir" in
    /*)
      project_root=$(echo "$git_common_dir" | sed 's|/\.git$||; s|/\.git/.*||')
      ;;
    *)
      project_root="$cwd"
      ;;
  esac
  project_key=$(echo "$project_root" | tr '/' '-' | tr '.' '-')
fi

# ── PR detection with URL and linked issues (cached, 5 min TTL) ──
pr_num=""
pr_url=""
pr_issues=""
if [ -n "$branch_safe" ] && command -v gh > /dev/null 2>&1; then
  # Include project_key to prevent cross-project cache collision on same branch name
  cache_file="/tmp/.claude-pr-${project_key}-${branch_safe}"

  use_cache=0
  if [ -f "$cache_file" ]; then
    mtime=$(stat -f %m "$cache_file" 2>/dev/null || stat -c %Y "$cache_file" 2>/dev/null)
    if [ -n "$mtime" ]; then
      age=$(( $(date +%s) - mtime ))
      [ "$age" -lt 300 ] && use_cache=1
    fi
  fi

  if [ "$use_cache" -eq 1 ]; then
    cached=$(cat "$cache_file" 2>/dev/null)
  else
    cached=$(gh pr view --json number,url,closingIssuesReferences \
      -q '[.number, .url, ([.closingIssuesReferences[].number] | map(tostring) | join(","))] | join("|")' \
      2>/dev/null || echo "")
    echo "$cached" > "$cache_file"
  fi

  pr_num=$(echo "$cached" | cut -d'|' -f1)
  pr_url=$(echo "$cached" | cut -d'|' -f2)
  pr_issues=$(echo "$cached" | cut -d'|' -f3)
  # Guard: if pr_url doesn't look like a URL (legacy cache), discard it
  case "$pr_url" in https://*) ;; *) pr_url="" ;; esac
fi

# ── Issue detection (3-tier fallback) ────────────────────────────
issue_num=""

# Tier 1: PR linked issues
if [ -z "$issue_num" ] && [ -n "$pr_issues" ]; then
  issue_num=$(echo "$pr_issues" | cut -d',' -f1)
fi

# Tier 2: Branch name pattern (e.g., fix/42-desc or issue/42)
if [ -z "$issue_num" ] && [ -n "$branch" ]; then
  issue_num=$(echo "$branch" | sed -n 's|^[a-z][a-z]*/\([0-9][0-9]*\)[-/].*|\1|p')
  [ -z "$issue_num" ] && issue_num=$(echo "$branch" | sed -n 's|^[a-z][a-z]*/\([0-9][0-9]*\)$|\1|p')
fi

# Tier 3: events.jsonl init event
if [ -z "$issue_num" ] && [ -f "$HOME/.claude/scripts/events.sh" ]; then
  if ( . "$HOME/.claude/scripts/events.sh" 2>/dev/null ); then
    _sd=$(cd "${cwd:-.}" && . "$HOME/.claude/scripts/events.sh" 2>/dev/null && events_state_dir 2>/dev/null || echo "")
    if [ -n "$_sd" ] && [ -f "$_sd/events.jsonl" ]; then
      issue_num=$(cd "${cwd:-.}" && . "$HOME/.claude/scripts/events.sh" 2>/dev/null \
        && events_latest "$_sd" init 2>/dev/null \
        | jq -r '.issue_num // empty' 2>/dev/null || echo "")
    fi
  fi
fi

repo_url=""
if [ -n "$pr_url" ]; then
  repo_url="${pr_url%/pull/*}"
elif [ -n "$cwd" ]; then
  remote_url=$(git -C "$cwd" remote get-url origin 2>/dev/null)
  case "$remote_url" in
    git@*) repo_url="https://$(echo "$remote_url" | sed 's|git@||; s|:|/|; s|\.git$||')" ;;
    https://*) repo_url="${remote_url%.git}" ;;
  esac
fi

issue_display=""
if [ -n "$issue_num" ]; then
  if [ -n "$repo_url" ]; then
    issue_url="${repo_url}/issues/${issue_num}"
    issue_link=$'\033]8;;'"${issue_url}"$'\033\\'"#${issue_num}"$'\033]8;;\033\\'
    issue_display="${D}(${R}${YL}${issue_link}${R}${D})${R}"
  else
    issue_display="${D}(${R}${YL}#${issue_num}${R}${D})${R}"
  fi
fi

# -- Dev server statusline extension ──────────────────────────
ext_display=""
ext_script="$HOME/.claude/scripts/statusline-ext.sh"
if [ -n "$project_root" ] && [ -f "$ext_script" ]; then
  ext_display=$(bash "$ext_script" "$project_root" "$project_key" "$cwd" 2>/dev/null)
fi


# ── Context % color ──────────────────────────────────────────────
pct_color="$GR"
pct_int=""
if [ -n "$used_pct" ]; then
  pct_int=$(printf "%.0f" "$used_pct")
  [ "$pct_int" -gt 80 ] && pct_color="$RD"
  [ "$pct_int" -gt 60 ] && [ "$pct_int" -le 80 ] && pct_color="$YL"
fi

# ── Assemble single left-aligned line ────────────────────────────
out=""

if [ -n "$branch" ]; then
  # Primary identifier: PR if exists, otherwise branch name
  if [ -n "$pr_num" ]; then
    if [ -n "$pr_url" ]; then
      # OSC 8 hyperlink — clickable in iTerm2, Kitty, WezTerm, Windows Terminal, etc.
      pr_link=$'\033]8;;'"${pr_url}"$'\033\\'"PR #${pr_num}"$'\033]8;;\033\\'
    else
      pr_link="PR #${pr_num}"
    fi
    out="${CY}${pr_link}${R}"
  else
    out="${CY}${branch_display}${R}"
  fi
  [ -n "$issue_display" ] && out="${out} ${issue_display}"
fi

[ -n "$ext_display"  ] && { [ -n "$out" ] && out="${out} ${SEP} "; out="${out}${ext_display}"; }
[ -n "$tok_display"  ] && { [ -n "$out" ] && out="${out} ${SEP} "; out="${out}${D}${tok_display}${R}"; }

[ -n "$out" ] && out="${out} ${SEP} "
out="${out}${MG}${model}${R}"
[ -n "$pct_int" ] && out="${out} ${D}(${R}${pct_color}${pct_int}%${R}${D})${R}"

printf '%s\n' "$out"
