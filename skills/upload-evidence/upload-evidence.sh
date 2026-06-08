#!/usr/bin/env bash
# upload-evidence.sh — Upload evidence (screenshots or video) to GitHub Release and post PR comment.
#
# Usage:
#   bash ~/.claude/skills/upload-evidence/upload-evidence.sh [--pr NUMBER] [--name TASK_NAME] [--mode screenshot|video]
#     [--section "Section header"] [--description "Blockquote context"]
#
# Examples:
#   bash ~/.claude/skills/upload-evidence/upload-evidence.sh                    # auto-detect mode
#   bash ~/.claude/skills/upload-evidence/upload-evidence.sh --pr 7
#   bash ~/.claude/skills/upload-evidence/upload-evidence.sh --mode screenshot \
#     --section "[A] Browser Verify — Phase 1" --description "Purpose: verify settings page rendering"
#   bash ~/.claude/skills/upload-evidence/upload-evidence.sh --pipeline qa --mode video \
#     --section "S1: Chat flow" --description "Verify new-conversation creation and message send"
#
# What it does:
#   1. Collects .png (screenshot mode, default) or .webm (video mode) files from known locations
#   2. Renames to PR-scoped filename: pr{N}-{pipeline}-{basename}.{png|webm}
#   3. Uploads to test-evidence GitHub Release
#   4. Verifies each upload via API
#   5. Posts PR comment with links (--section/--description provide context inline)
#
# Hard rules enforced by this script (not documentation):
#   - Filename: pr{N}-{pipeline}-{basename}.{png|webm} — pipeline prefix (dev|qa)
#     prevents /dev and /qa from clobbering each other on the shared release.
#   - Comment posting: --input <json-file> — never --field body="..."
#   - Release tag: test-evidence — hardcoded, never configurable
set -euo pipefail

# ── Parse arguments ──────────────────────────────────────────────

PR_NUMBER=""
TASK_NAME=""
EVIDENCE_MODE=""  # auto-detect if not specified
PIPELINE_TYPE="dev"  # dev (default) | qa
SECTION_HEADER=""    # PR comment section title (replaces .desc line 1)
DESCRIPTION=""       # PR comment blockquote context (replaces .desc > lines)
SKIP_HEAD_CHECK="auto"  # auto | yes | no — auto skips for private repos (HEAD always 404)
STAGE_NAME=""        # build | verify — required for emitting evidence.uploaded event
STAGE_ITER="1"       # event matching iteration (default 1)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr) PR_NUMBER="$2"; shift 2 ;;
    --name) TASK_NAME="$2"; shift 2 ;;
    --mode) EVIDENCE_MODE="$2"; shift 2 ;;
    --pipeline) PIPELINE_TYPE="$2"; shift 2 ;;
    --section) SECTION_HEADER="$2"; shift 2 ;;
    --description) DESCRIPTION="$2"; shift 2 ;;
    --stage) STAGE_NAME="$2"; shift 2 ;;
    --iter) STAGE_ITER="$2"; shift 2 ;;
    --skip-head-check) SKIP_HEAD_CHECK="yes"; shift ;;
    --require-head-check) SKIP_HEAD_CHECK="no"; shift ;;
    --*) echo "Unknown flag: $1" >&2; exit 1 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# Validate --pipeline and --mode against documented contract
case "$PIPELINE_TYPE" in
  dev|qa) ;;
  *) echo "ERROR: --pipeline must be 'dev' or 'qa', got '$PIPELINE_TYPE'" >&2; exit 1 ;;
esac

case "$EVIDENCE_MODE" in
  screenshot|video|"") ;;
  *) echo "ERROR: --mode must be 'screenshot' or 'video', got '$EVIDENCE_MODE'" >&2; exit 1 ;;
esac

# ── Resolve context ──────────────────────────────────────────────

REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')
if [ -z "$REPO" ]; then
  echo "ERROR: Cannot resolve repo — ensure gh is authenticated" >&2
  exit 1
fi

if [ -z "$PR_NUMBER" ]; then
  PR_NUMBER=$(gh pr view --json number -q '.number' 2>/dev/null || echo "")
  if [ -z "$PR_NUMBER" ]; then
    echo "ERROR: No PR found for current branch — use --pr NUMBER" >&2
    exit 1
  fi
fi

if [ -z "$TASK_NAME" ]; then
  BRANCH=$(git branch --show-current 2>/dev/null)
  TASK_NAME="${BRANCH##*/}"  # feat/mobile-nav-overlap → mobile-nav-overlap
fi

RELEASE_TAG="test-evidence"
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
# Compute TASK_ID / STATE_DIR inline.
# Issue number: events.jsonl init event is the source of truth.
STATE_DIR=""
if . "$HOME/.claude/scripts/events.sh" 2>/dev/null; then
  STATE_DIR=$(events_state_dir 2>/dev/null) || STATE_DIR=""
fi
ISSUE=""
if [ -n "$STATE_DIR" ] && [ -f "$STATE_DIR/events.jsonl" ]; then
  ISSUE=$(events_latest "$STATE_DIR" init 2>/dev/null | jq -r '.issue_num // empty' 2>/dev/null || echo "")
fi
SLUG=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | sed 's|.*/||' | tr '/' '-' || echo "")
TASK_ID="${ISSUE:+${ISSUE}-}${SLUG}"
RESULTS_DIR="${STATE_DIR:-/tmp/claude-evidence}"

echo "▶ Upload Evidence: repo=$REPO pr=#$PR_NUMBER task=$TASK_NAME"
echo ""

# ── Step 1: Auto-detect or use specified evidence mode ───────────

if [ -z "$EVIDENCE_MODE" ]; then
  # Auto-detect: check for screenshots first (default), then webm.
  # Both live under $STATE_DIR/evidence/ after Phase 6 (content-addressed storage).
  PNG_COUNT=$(ls "$RESULTS_DIR"/evidence/*.png 2>/dev/null | wc -l | tr -d ' ')
  WEBM_COUNT=$(ls "$RESULTS_DIR"/evidence/*.webm 2>/dev/null | wc -l | tr -d ' ')
  if [ "$PNG_COUNT" -gt 0 ]; then
    EVIDENCE_MODE="screenshot"
  elif [ "$WEBM_COUNT" -gt 0 ]; then
    EVIDENCE_MODE="video"
  else
    echo "ERROR: No evidence found (no .png or .webm under $RESULTS_DIR/evidence/)" >&2
    exit 1
  fi
fi
echo "  Evidence mode: $EVIDENCE_MODE"
echo ""

# ── Step 1b: Collect evidence files ──────────────────────────────

declare -a EVIDENCE_SRCS

if [ "$EVIDENCE_MODE" = "screenshot" ]; then
  # Collect .png from $STATE_DIR/evidence/
  while IFS= read -r f; do
    EVIDENCE_SRCS+=("$f")
  done < <(ls -t "$RESULTS_DIR"/evidence/*.png 2>/dev/null || true)

  if [ ${#EVIDENCE_SRCS[@]} -eq 0 ]; then
    echo "ERROR: No screenshot evidence found in:" >&2
    echo "  - $RESULTS_DIR/evidence/*.png" >&2
    exit 1
  fi

  # Viewport guard: reject full-screen captures that leak desktop contents.
  # Browser viewport widths are <= 1920 in nearly all evidence flows; Playwright
  # full-page captures can be tall but never wider than the viewport. macOS
  # Retina OS-level captures are 2880px or 5120px wide — clearly disqualifying.
  # We check WIDTH only so Playwright `fullPage: true` (tall) evidence still passes.
  # Bypass: UPLOAD_EVIDENCE_ALLOW_OVERSIZE=1 (warning logged in PR comment).
  if [ "${UPLOAD_EVIDENCE_ALLOW_OVERSIZE:-0}" != "1" ] && command -v sips >/dev/null 2>&1; then
    OVERSIZE_FAIL=0
    for f in "${EVIDENCE_SRCS[@]}"; do
      W=$(sips -g pixelWidth "$f" 2>/dev/null | awk '/pixelWidth/ {print $2}')
      H=$(sips -g pixelHeight "$f" 2>/dev/null | awk '/pixelHeight/ {print $2}')
      [ -z "$W" ] && continue
      if [ "$W" -gt 1920 ]; then
        echo "  [REJECT] $(basename "$f") — ${W}x${H:-?} exceeds 1920px viewport width limit" >&2
        OVERSIZE_FAIL=$((OVERSIZE_FAIL + 1))
      fi
    done
    if [ $OVERSIZE_FAIL -gt 0 ]; then
      cat >&2 <<EOF
ERROR: $OVERSIZE_FAIL screenshot(s) exceed the 1920px viewport-width limit.
       Full-screen captures from \`mcp__claude-in-chrome__computer(action:"screenshot")\`
       leak the user's desktop and are forbidden as evidence.

       Re-capture with: agent-browser screenshot --path <file>
       (Playwright viewport-only, ~1280x720, ~100-180KB.)

       See ~/.claude/skills/chrome-for-claude/SKILL.md → "Screenshot evidence".

       Emergency bypass (will warn in PR comment): UPLOAD_EVIDENCE_ALLOW_OVERSIZE=1
EOF
      exit 1
    fi
  fi
else
  # Video mode: collect .webm from $STATE_DIR/evidence/ (Phase 6 content-addressed storage)
  while IFS= read -r f; do
    EVIDENCE_SRCS+=("$f")
  done < <(ls -t "$RESULTS_DIR"/evidence/*.webm 2>/dev/null || true)

  # Fallback locations (pre-migrate / local-only recordings that haven't been moved yet)
  if [ ${#EVIDENCE_SRCS[@]} -eq 0 ]; then
    while IFS= read -r f; do
      EVIDENCE_SRCS+=("$f")
    done < <(ls -t /tmp/*.webm ~/Downloads/*.webm 2>/dev/null || true)
  fi
  if [ ${#EVIDENCE_SRCS[@]} -eq 0 ]; then
    while IFS= read -r f; do
      EVIDENCE_SRCS+=("$f")
    done < <(find "$REPO_ROOT" -path "*/test-results/*.webm" -mmin -30 2>/dev/null || true)
  fi

  if [ ${#EVIDENCE_SRCS[@]} -eq 0 ]; then
    echo "ERROR: No video evidence found in:" >&2
    echo "  - $RESULTS_DIR/evidence/*.webm" >&2
    echo "  - /tmp/*.webm" >&2
    echo "  - ~/Downloads/*.webm" >&2
    echo "  - */test-results/*.webm" >&2
    exit 1
  fi
fi

echo "  Found ${#EVIDENCE_SRCS[@]} evidence file(s):"
for f in "${EVIDENCE_SRCS[@]}"; do
  echo "    $(basename "$f") ($(du -h "$f" | cut -f1))"
done
echo ""

# ── Step 2: Create release (idempotent) ─────────────────────────

gh release create "$RELEASE_TAG" \
  --title "Test Evidence" \
  --notes "Browser test recordings" \
  --prerelease 2>/dev/null || true

# ── Step 3: Upload with PR-scoped filename ───────────────────────
# Hard rule: filename = pr{N}-{pipeline}-{basename}.{ext}
# Pipeline prefix (dev|qa) prevents /dev and /qa from clobbering each other
# when they upload same-named files (e.g. both produce tia-foo-step01.png).

declare -a ASSET_URLS
declare -a ASSET_NAMES

for i in "${!EVIDENCE_SRCS[@]}"; do
  SRC="${EVIDENCE_SRCS[$i]}"
  SRC_BASENAME=$(basename "$SRC")
  EXT="${SRC_BASENAME##*.}"
  NAME_NO_EXT="${SRC_BASENAME%.*}"
  ASSET_NAME="pr${PR_NUMBER}-${PIPELINE_TYPE}-${NAME_NO_EXT}.${EXT}"
  ASSET_NAMES+=("$ASSET_NAME")

  cp "$SRC" "/tmp/${ASSET_NAME}"
  gh release upload "$RELEASE_TAG" "/tmp/${ASSET_NAME}" --clobber
  echo "  Uploaded: $ASSET_NAME"
  ASSET_URLS+=("https://github.com/${REPO}/releases/download/${RELEASE_TAG}/${ASSET_NAME}")
done
echo ""

# ── Step 4: Verify uploads via API ───────────────────────────────

echo "▶ Verifying uploads..."
VERIFY_FAILED=0

for ASSET_NAME in "${ASSET_NAMES[@]}"; do
  RESULT=$(gh api "repos/${REPO}/releases/tags/${RELEASE_TAG}" \
    --jq ".assets[] | select(.name == \"${ASSET_NAME}\") | {name: .name, state: .state, size: .size}" 2>/dev/null || echo "")

  if [ -z "$RESULT" ]; then
    echo "  [FAIL] $ASSET_NAME — not found in release assets"
    VERIFY_FAILED=$((VERIFY_FAILED + 1))
  else
    STATE=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])" 2>/dev/null || echo "unknown")
    SIZE=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['size'])" 2>/dev/null || echo "0")
    if [ "$STATE" = "uploaded" ] && [ "$SIZE" != "0" ]; then
      echo "  [OK] $ASSET_NAME (state=$STATE, size=$SIZE)"
    else
      echo "  [FAIL] $ASSET_NAME (state=$STATE, size=$SIZE)"
      VERIFY_FAILED=$((VERIFY_FAILED + 1))
    fi
  fi
done

if [ $VERIFY_FAILED -gt 0 ]; then
  echo "ERROR: $VERIFY_FAILED upload(s) failed verification" >&2
  exit 1
fi
echo ""

# ── Emit evidence.uploaded event NOW (after API-verified upload, before HEAD check)
# Rationale: assets are confirmed uploaded by the GitHub API. The HEAD check below
# is a UX guard for anonymous link reachability (public repos) — its failure does
# not invalidate the upload. We emit the event here so events_emit_stage_passed
# can find it even if the HEAD check or PR-comment posting fails downstream.
if [ -n "$STAGE_NAME" ] && [ -n "$STATE_DIR" ] && command -v events_emit_evidence_uploaded >/dev/null 2>&1; then
  EV_URLS_JSON=$(printf '%s\n' "${ASSET_URLS[@]}" | jq -R . | jq -sc .)
  events_emit_evidence_uploaded "$STATE_DIR" "$TASK_ID" "$STAGE_NAME" "$STAGE_ITER" \
    "${#ASSET_URLS[@]}" "$EV_URLS_JSON" "$RELEASE_TAG" \
    2>/dev/null && echo "▶ events.jsonl: evidence.uploaded recorded (stage=$STAGE_NAME, iter=$STAGE_ITER, count=${#ASSET_URLS[@]})"
fi

# ── Auto-detect repo visibility for HEAD check policy ────────────
# Private repos serve the public release URL behind auth, so anonymous HEAD
# always returns 404. Refusing to post in that case strands the evidence trail
# for legitimate reviewers (who do have auth). Default policy is "auto": skip
# HEAD when the repo is private. Override with --require-head-check or --skip-head-check.

REPO_VISIBILITY=$(gh repo view --json visibility -q '.visibility' 2>/dev/null || echo "UNKNOWN")
case "$SKIP_HEAD_CHECK" in
  auto)
    case "$REPO_VISIBILITY" in
      PRIVATE|INTERNAL)
        SKIP_HEAD_CHECK="yes"
        echo "▶ Repo visibility=$REPO_VISIBILITY — skipping anonymous HEAD check (assets are gated behind auth)."
        ;;
      *)
        SKIP_HEAD_CHECK="no"
        ;;
    esac
    ;;
esac

# ── Step 4.5: Verify public download URLs are reachable ──────────
# API state=uploaded does not guarantee the public URL resolves immediately
# (CDN propagation, asset rename, release-state edge cases). HEAD-check each
# URL with one retry before posting it to the PR — a 404 link in the gate
# comment defeats the entire evidence trail. Skipped for private/internal repos
# where the public URL requires auth (HEAD will always fail anonymously).

if [ "$SKIP_HEAD_CHECK" = "yes" ]; then
  echo "▶ Skipping public URL reachability check (--skip-head-check or auto-detected private/internal repo)."
  echo ""
else
  echo "▶ Verifying public URL reachability..."
  URL_FAILED=0

  for URL in "${ASSET_URLS[@]}"; do
    if curl -fIsSL --max-time 10 "$URL" >/dev/null 2>&1; then
      echo "  [OK] $URL"
    else
      sleep 2
      if curl -fIsSL --max-time 10 "$URL" >/dev/null 2>&1; then
        echo "  [OK after retry] $URL"
      else
        echo "  [FAIL] $URL — public download URL unreachable"
        URL_FAILED=$((URL_FAILED + 1))
      fi
    fi
  done

  if [ $URL_FAILED -gt 0 ]; then
    echo "ERROR: $URL_FAILED evidence URL(s) unreachable — refusing to post broken links to PR" >&2
    echo "       If this is a private/internal repo, anonymous HEAD always fails — re-run with --skip-head-check." >&2
    exit 1
  fi
  echo ""
fi

# ── Step 5: Post PR comment with evidence table ──────────────────
# Hard rule: Use Python to generate JSON → --input <file>
# NEVER use --field body="..." (zsh ! → \! breaks link syntax)

PR_TITLE=$(gh pr view "$PR_NUMBER" --json title -q '.title' 2>/dev/null || echo "")
PR_BODY=$(gh pr view "$PR_NUMBER" --json body -q '.body' 2>/dev/null || echo "")

python3 - "$PR_NUMBER" "$PR_TITLE" "$EVIDENCE_MODE" "$PIPELINE_TYPE" "$SECTION_HEADER" "$DESCRIPTION" "${ASSET_URLS[@]}" <<'PYEOF' > "$REPO_ROOT/.claude/evidence-comment.json"
import json, sys, re

pr_num = sys.argv[1]
pr_title = sys.argv[2]
evidence_mode = sys.argv[3]
pipeline_type = sys.argv[4]
section_header = sys.argv[5]   # --section value (empty string if not provided)
description = sys.argv[6]      # --description value (empty string if not provided)
asset_urls = sys.argv[7:]

# Title reflects pipeline type: /dev produces "Dev Test Evidence", /qa produces "QA Evidence"
title_label = "Dev Test Evidence" if pipeline_type == "dev" else "QA Evidence"
header = f"## {title_label}\n\n**{pr_title}**"

if evidence_mode == "screenshot":
    # Use provided section header, or fall back to generic label
    heading = section_header if section_header else "Screenshots"

    section = f"### {heading}\n"
    if description:
        section += f"\n> {description}\n"

    # Sort screenshots ascending by step number
    def step_num(url):
        m = re.search(r'step(\d+)', url.split("/")[-1])
        return int(m.group(1)) if m else 999

    urls_sorted = sorted(asset_urls, key=step_num)

    section += "\n| Verification Item | Screenshot |\n|-------------------|------------|\n"
    prefix = f"pr{pr_num}-{pipeline_type}-"
    for i, url in enumerate(urls_sorted):
        base = url.split("/")[-1].replace(prefix, "").replace(".png", "")
        label = base.replace("-", " ").title()
        section += f"| {label} | ![step{i+1}]({url}) |\n"

    body = header + "\n\n---\n\n" + section
else:
    # Video mode
    rows = []
    prefix = f"pr{pr_num}-{pipeline_type}-"
    for url in asset_urls:
        name = url.split("/")[-1].replace(".webm", "")
        flow = section_header if section_header else name.replace(prefix, "").replace("-", " ").title()
        desc = description if description else ""
        rows.append(f"| {flow} | [📥 Download]({url}) | {desc} |")

    table = (
        "| Flow | Recording | What it verifies |\n"
        "|------|-----------|------------------|\n"
        + "\n".join(rows)
    )
    body = header + "\n\n---\n\n" + table

print(json.dumps({"body": body}))
PYEOF

gh api --method POST "repos/${REPO}/issues/${PR_NUMBER}/comments" --input "$REPO_ROOT/.claude/evidence-comment.json"
rm -f "$REPO_ROOT/.claude/evidence-comment.json"

echo "▶ Evidence comment posted to PR #${PR_NUMBER}"
echo ""
echo "  PR: https://github.com/${REPO}/pull/${PR_NUMBER}"
echo "  Assets: ${#ASSET_NAMES[@]} file(s) uploaded to release/$RELEASE_TAG (mode: $EVIDENCE_MODE)"
