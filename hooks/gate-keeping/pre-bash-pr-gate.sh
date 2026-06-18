#!/usr/bin/env bash
# Pre-PR gate — blocks PR creation until events.jsonl has build + verify + review passes.
#
# Events-authoritative (Phase 5):
#   - Valid log with stage.passed(build), stage.passed(verify) with writer,
#     and stage.passed(review) summary containing APPROVED → allow.
#   - Valid log missing any of the above → deny with actionable message.
#   - Invalid log                         → deny (fail-closed on ambiguity).
#   - events.jsonl absent                 → deny (run /dev <issue> to initialize).
#
# Draft PR lighter gate (--draft flag detected):
#   - Resolves state dir from CWD first, then from --head <branch> worktree lookup.
#   - Only requires a valid events.jsonl with an init event — no build/review/verify.
#   - Rationale: draft PRs are explicitly not-ready-to-merge placeholders; enforcing
#     the full gate prevents creating fix tracks before any code exists.
#
# Emergency escape hatch: CLAUDE_EVENTS_HOOK_SKIP=1 (logged to stderr).
#
# Trigger: PreToolUse:Bash (gh pr create / gh api pulls POST)
set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$COMMAND" ] && exit 0

# Match gh pr create OR gh api pulls POST
IS_PR=false
echo "$COMMAND" | grep -qE 'gh\s+pr\s+create' && IS_PR=true
echo "$COMMAND" | grep -qE 'gh\s+api.*pulls.*(POST|-X\s*POST|--method\s+POST)' && IS_PR=true

# Match gh pr comment commands that post gate:build or gate:verify markers.
# Gate comments require evidence.uploaded before they can land — this closes the gap
# where EVENTS_ALLOW_UNUPLOADED_EVIDENCE=1 is used for stage.passed but the follow-up
# upload step is skipped, leaving evidence only on disk and never on GitHub.
IS_GATE_COMMENT=false
_GATE_COMMENT_STAGE=""
if echo "$COMMAND" | grep -qE 'gh\s+pr\s+comment'; then
  if echo "$COMMAND" | grep -qE '<!--[[:space:]]*gate:build:'; then
    IS_GATE_COMMENT=true
    _GATE_COMMENT_STAGE="build"
  elif echo "$COMMAND" | grep -qE '<!--[[:space:]]*gate:verify:'; then
    IS_GATE_COMMENT=true
    _GATE_COMMENT_STAGE="verify"
  fi
fi

[ "$IS_PR" = false ] && [ "$IS_GATE_COMMENT" = false ] && exit 0

# Detect draft PR — lighter gate applies
IS_DRAFT=false
echo "$COMMAND" | grep -qE -- '--draft\b' && IS_DRAFT=true

# Emergency skip (logged + recorded to events.jsonl if available)
if [ "${CLAUDE_EVENTS_HOOK_SKIP:-0}" = "1" ]; then
  if . "${CLAUDE_PLUGIN_ROOT}/scripts/events.sh" 2>/dev/null \
     && _sd=$(events_state_dir 2>/dev/null) && [ -d "$_sd" ] && [ -f "$_sd/events.jsonl" ]; then
    # Corrupt events.jsonl would make `events_latest | jq` fail under pipefail.
    _tid=$( { events_latest "$_sd" init 2>/dev/null || true; } | jq -r '.task_id // "unknown"' 2>/dev/null || echo "unknown")
    events_emit_gate_skipped "$_sd" "${_tid:-unknown}" "pre-bash-pr-gate" "CLAUDE_EVENTS_HOOK_SKIP" \
      "$(printf '%s' "$COMMAND" | head -c 200)" 2>/dev/null || true
  fi
  echo "pre-bash-pr-gate: CLAUDE_EVENTS_HOOK_SKIP=1 — skipping gate (logged to events.jsonl if available)" >&2
  exit 0
fi

# Not in a git repo → don't block
git rev-parse --show-toplevel >/dev/null 2>&1 || exit 0
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)

# Repos without build config have no pipeline to gate — skip entirely.
# Why this runs BEFORE the Phase 4 events check: config repos like ~/.claude
# itself have no package.json and are not driven by /dev or /qa, so Phase 4's
# fail-closed-on-missing-events.jsonl must not apply to them.
if [ ! -f "$REPO_ROOT/package.json" ] && [ ! -f "$REPO_ROOT/turbo.json" ]; then
  exit 0
fi

# ---------- Phase 4: events.jsonl primary read (fail-closed when absent) ----------
if [ -f "${CLAUDE_PLUGIN_ROOT}/scripts/events.sh" ]; then
  # shellcheck disable=SC1091
  if . "${CLAUDE_PLUGIN_ROOT}/scripts/events.sh" 2>/dev/null; then
    _EV_STATE_DIR=$(events_state_dir 2>/dev/null || echo "")

    # ---------- Gate comment: enforce evidence.uploaded before gate:build/verify ----------
    # When a gate comment is being posted but no evidence.uploaded event exists and
    # evidence files are present on disk, block — the pipeline skipped the upload step.
    # Fail-open when events.jsonl is absent (full PR gate handles that separately).
    if [ "$IS_GATE_COMMENT" = true ] && [ -n "$_GATE_COMMENT_STAGE" ]; then
      if [ -n "$_EV_STATE_DIR" ] && [ -f "$_EV_STATE_DIR/events.jsonl" ]; then
        _EV_UPLOADED=$(events_latest "$_EV_STATE_DIR" "evidence.uploaded" "stage=${_GATE_COMMENT_STAGE}" 2>/dev/null || echo "")
        if [ -z "$_EV_UPLOADED" ]; then
          _DISK_EVIDENCE=""
          if [ "$_GATE_COMMENT_STAGE" = "build" ]; then
            _DISK_EVIDENCE=$(find "$_EV_STATE_DIR/evidence" -maxdepth 1 -name 'browser-verify-*.png' 2>/dev/null | head -1 || true)
          else
            # tia-*.png only counts for E2E specs; vitest unit test TIA has no PNG evidence.
            # s<N>-* are QA scenario recordings (tester stage).
            _DISK_EVIDENCE=$(find "$_EV_STATE_DIR/evidence" -maxdepth 1 \( -name 'tia-*.png' -o -name 's[0-9]*.webm' \) 2>/dev/null | head -1 || true)
          fi
          if [ -n "$_DISK_EVIDENCE" ]; then
            printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: gate:%s comment requires evidence to be uploaded to GitHub first. Evidence files exist in %s/evidence/ but no evidence.uploaded event found for stage=%s. Run the upload-evidence skill BEFORE posting the gate comment."}}\n' \
              "$_GATE_COMMENT_STAGE" "$_EV_STATE_DIR" "$_GATE_COMMENT_STAGE"
            exit 0
          fi
        fi
      fi
      # Evidence uploaded (or no evidence on disk, or no events.jsonl) — allow.
      exit 0
    fi
    # ---------- End gate comment enforcement ----------

    # ---------- Draft PR: lighter gate (init event only) ----------
    # For draft PRs, also try to resolve state dir from the --head <branch> worktree
    # when the CWD's state dir has no events.jsonl. This handles the /fix workflow
    # where the fix worktree has its own events.jsonl but the session CWD does not.
    if [ "$IS_DRAFT" = true ]; then
      _DRAFT_SD="$_EV_STATE_DIR"

      # If CWD state dir has no events.jsonl, look up the head branch's worktree
      if [ -z "$_DRAFT_SD" ] || [ ! -f "$_DRAFT_SD/events.jsonl" ]; then
        _HEAD_BRANCH=$(printf '%s' "$COMMAND" \
          | grep -oE -- '--head[= ][^[:space:]"]+' | head -1 \
          | sed 's/--head[= ]//')
        if [ -n "$_HEAD_BRANCH" ]; then
          _BR_REF="refs/heads/$_HEAD_BRANCH"
          _HEAD_WT=$(git worktree list --porcelain 2>/dev/null \
            | awk -v br="$_BR_REF" \
              '/^worktree/{wt=$2} $0==("branch " br){print wt; exit}')
          if [ -n "$_HEAD_WT" ] && [ -d "$_HEAD_WT" ]; then
            _DRAFT_SD=$(cd "$_HEAD_WT" \
              && . "${CLAUDE_PLUGIN_ROOT}/scripts/events.sh" 2>/dev/null \
              && events_state_dir 2>/dev/null || echo "")
          fi
        fi
      fi

      if [ -z "$_DRAFT_SD" ] || [ ! -f "$_DRAFT_SD/events.jsonl" ]; then
        echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED (draft PR): events.jsonl not found. Run /fix [issue] to initialize, or /dev <issue> for the full pipeline."}}'
        exit 0
      fi
      if ! events_validate "$_DRAFT_SD/events.jsonl" >/dev/null 2>&1; then
        printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED (draft PR): events.jsonl failed validation at %s."}}\n' "$_DRAFT_SD/events.jsonl"
        exit 0
      fi
      _EV_INIT=$(events_latest "$_DRAFT_SD" "init" 2>/dev/null || echo "")
      if [ -z "$_EV_INIT" ]; then
        echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED (draft PR): events.jsonl has no init event. Run /fix [issue] to initialize."}}'
        exit 0
      fi
      # Draft PR: require evidence.uploaded event when UI files (.tsx/.jsx/.css/.svg) changed.
      # Checks that upload-evidence was actually called — not just that files exist on disk.
      _EV_UPLOADED=$(events_latest "$_DRAFT_SD" "evidence.uploaded" "stage=build" 2>/dev/null || echo "")
      if [ -z "$_EV_UPLOADED" ]; then
        _UI_CHANGED=$(git diff HEAD~1 HEAD --name-only 2>/dev/null | grep -E '\.(tsx|jsx|css|svg)$' || true)
        if [ -n "$_UI_CHANGED" ]; then
          echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED (draft PR): UI files changed but no evidence.uploaded event found. Run upload-evidence to post browser-verify screenshots to GitHub before creating the PR."}}'
          exit 0
        fi
      fi

      # Draft PR: also enforce evidence-flows declared in plan.md for browser-verify-*
      # flows. The draft is created after BUILD — browser-verify evidence must exist.
      # Subagents that emit stage.passed(build) with evidence=[] bypass the hard gate;
      # this check catches that bypass at PR-creation time.
      _DRAFT_PLAN="$_DRAFT_SD/plan.md"
      if [ -f "$_DRAFT_PLAN" ] \
         && [ -f "${CLAUDE_PLUGIN_ROOT}/scripts/store_evidence.sh" ] \
         && command -v check_evidence_parity >/dev/null 2>&1; then
        . "${CLAUDE_PLUGIN_ROOT}/scripts/store_evidence.sh" 2>/dev/null || true
        _EV_MODE=$(grep -E '^evidence-mode:' "$_DRAFT_PLAN" | head -1 | sed 's/^evidence-mode:[[:space:]]*//')
        if [ "$_EV_MODE" != "none" ]; then
          _FLOWS=$(grep -E '^evidence-flows:' "$_DRAFT_PLAN" | head -1 | sed 's/^evidence-flows:[[:space:]]*//')
          if [ -n "$_FLOWS" ]; then
            # Only check browser-verify-* flows for draft PRs (tia-* and s<N>-* are verify/qa stage)
            _BV_FLOWS=$(printf '%s' "$_FLOWS" | tr ',' '\n' | grep -E '^\s*browser-verify-' | tr '\n' ',' | sed 's/,$//')
            if [ -n "$_BV_FLOWS" ]; then
              _DRAFT_PARITY_ERR=$(check_evidence_parity "$_DRAFT_SD" 2>&1 1>/dev/null || true)
              # Only fail on browser-verify flow mismatches
              _BV_PARITY_ERR=$(printf '%s' "${_DRAFT_PARITY_ERR}" | grep 'browser-verify' || true)
              if [ -n "$_BV_PARITY_ERR" ]; then
                _BV_MSG=$(printf '%s' "$_BV_PARITY_ERR" | tr '\n' ';' | sed 's/;$//')
                printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED (draft PR): plan.md browser-verify evidence-flows not satisfied — %s. Capture browser-verify screenshots before creating the draft PR, or remove the flows from plan.md."}}\n' "$_BV_MSG"
                exit 0
              fi
            fi
          fi
        fi
      fi
      # Draft PR with valid init event and evidence-flows satisfied — allow.
      exit 0
    fi
    # ---------- End draft PR gate ----------

    if [ -n "$_EV_STATE_DIR" ] && [ -f "$_EV_STATE_DIR/events.jsonl" ]; then
      # Present — events is authoritative.
      if ! events_validate "$_EV_STATE_DIR/events.jsonl" >/dev/null 2>&1; then
        printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: events.jsonl failed validation at %s (Phase 2 fail-closed)."}}\n' "$_EV_STATE_DIR/events.jsonl"
        exit 0
      fi

      _EV_BUILD=$(events_latest "$_EV_STATE_DIR" "stage.passed" "stage=build" 2>/dev/null || echo "")
      [ -z "$_EV_BUILD" ] && { echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: no stage.passed(build) event. Run /dev BUILD."}}'; exit 0; }

      _EV_REVIEW=$(events_latest "$_EV_STATE_DIR" "stage.passed" "stage=review" 2>/dev/null || echo "")
      [ -z "$_EV_REVIEW" ] && { echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: no stage.passed(review) event. Run /dev REVIEW until APPROVED."}}'; exit 0; }
      # Review must contain APPROVED in summary (case-insensitive, word-boundary —
      # NOT_APPROVED / DISAPPROVED / UNAPPROVED / "not approved" / "disapproved" must not match).
      _EV_REVIEW_SUMMARY=$(printf '%s' "$_EV_REVIEW" | jq -r '.summary // ""')
      # 1. Reject explicit negative tokens first (anywhere in summary).
      _EV_REVIEW_NEGATED=$(printf '%s' "$_EV_REVIEW_SUMMARY" | grep -ciE '(NOT[ _-]*APPROVED|UN[ _-]*APPROVED|DIS[ _-]*APPROVED)' || true)
      if [ "${_EV_REVIEW_NEGATED:-0}" -gt 0 ]; then
        echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: stage.passed(review).summary contains a negation of APPROVED (e.g. NOT_APPROVED / UNAPPROVED / DISAPPROVED / not approved)."}}'
        exit 0
      fi
      # 2. Require a positive, word-bounded APPROVED token.
      _EV_REVIEW_APPROVED=$(printf '%s' "$_EV_REVIEW_SUMMARY" | grep -ciE '(^|[^A-Za-z_-])APPROVED([^A-Za-z_-]|$)' || true)
      [ "${_EV_REVIEW_APPROVED:-0}" -lt 1 ] && { echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: stage.passed(review).summary does not contain APPROVED."}}'; exit 0; }

      _EV_VERIFY=$(events_latest "$_EV_STATE_DIR" "stage.passed" "stage=verify" 2>/dev/null || echo "")
      [ -z "$_EV_VERIFY" ] && { echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: no stage.passed(verify) event. Run VERIFY (/dev) or QA (/qa)."}}'; exit 0; }
      _EV_VERIFY_WRITER=$(printf '%s' "$_EV_VERIFY" | jq -r '.writer // ""')
      case "$_EV_VERIFY_WRITER" in
        builder|tester) ;;
        *) echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: stage.passed(verify).writer must be builder or tester."}}'; exit 0 ;;
      esac

      # Evidence verification (Phase 6) — for each filename in the build/verify
      # evidence arrays, re-hash and compare against the <hash8> suffix embedded
      # in the filename. Phase 6c: filenames without a hash8 suffix are rejected
      # outright (the 6a backward-compat pass-through has been removed). When
      # the helper itself is missing we still fall back to trusting the emitter
      # so a botched $HOME/.claude layout doesn't wedge PR creation globally.
      if [ -f "${CLAUDE_PLUGIN_ROOT}/scripts/store_evidence.sh" ]; then
        # shellcheck disable=SC1091
        . "${CLAUDE_PLUGIN_ROOT}/scripts/store_evidence.sh" 2>/dev/null || true
        _EV_BAD=""
        for _stage_ev in "$_EV_BUILD" "$_EV_VERIFY"; do
          _ev_list=$(printf '%s' "$_stage_ev" | jq -r '.evidence[]? // empty' 2>/dev/null || echo "")
          [ -z "$_ev_list" ] && continue
          while IFS= read -r _ev_file; do
            [ -z "$_ev_file" ] && continue
            if ! store_evidence_verify "$_EV_STATE_DIR" "$_ev_file" >/dev/null 2>&1; then
              _EV_BAD="$_ev_file"
              break
            fi
          done <<EV_LIST_EOF
$_ev_list
EV_LIST_EOF
          [ -n "$_EV_BAD" ] && break
        done

        if [ -n "$_EV_BAD" ]; then
          printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: evidence verification failed for %s (missing file or content-addressed hash8 mismatch under %s/evidence/)."}}\n' "$_EV_BAD" "$_EV_STATE_DIR"
          exit 0
        fi

        # Phase 6 strict mode: every file under $STATE_DIR/evidence/ MUST
        # carry a valid hash8 suffix. Catches writers whose logical names
        # escaped the per-stage glob (prefix drift) — such files would
        # otherwise be invisible to the per-event check above but still
        # live on disk as unhashed, untracked evidence.
        if [ -d "$_EV_STATE_DIR/evidence" ]; then
          _EV_ORPHAN=""
          for _f in "$_EV_STATE_DIR"/evidence/*; do
            [ -f "$_f" ] || continue
            _fname="${_f##*/}"
            # Skip companion metadata sidecars — they describe evidence files
            # but are not themselves evidence subject to hash8 verification.
            case "$_fname" in
              *.metadata.json) continue ;;
            esac
            if ! store_evidence_verify "$_EV_STATE_DIR" "$_fname" >/dev/null 2>&1; then
              _EV_ORPHAN="$_fname"
              break
            fi
          done
          if [ -n "$_EV_ORPHAN" ]; then
            printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: unmigrated evidence %s under %s/evidence/ lacks a <hash8> suffix or fails hash verification. Orchestrator must call store_evidence_migrate before emitting stage.passed."}}\n' "$_EV_ORPHAN" "$_EV_STATE_DIR"
            exit 0
          fi
        fi
      fi

      # ---------- Evidence-flows contract enforcement ----------
      # plan.md declares the evidence contract via:
      #   evidence-flows: <comma-separated list of flow logical names>
      # Each declared flow MUST have at least one matching file under
      # $STATE_DIR/evidence/. Type-prefix conventions:
      #   browser-verify-* / tia-*  → ≥1 .png (multiple steps allowed)
      #   s<N>-*                     → ≥1 .webm (one scenario video per flow)
      #
      # Why: store_evidence_verify only validates files the orchestrator already
      # chose to put in stage.passed.evidence — it does NOT cross-check against
      # the plan's contract. A pipeline can emit `[a.png, b.png]`, pass the hash
      # check on those two, and ship even though plan.md declared 5 flows. This
      # block closes that gap. The plan is the contract; runtime evidence must
      # satisfy it.
      #
      # Cutover consistency: declaring s<N>-* (E2E scenarios) implicitly admits
      # production-code-path testing → cutover-phase MUST be true so the
      # production-path metadata check below actually applies. Otherwise the
      # cutover guard skips and a writer can ship E2E claims with no
      # production-path evidence. Reject that combination as a contradiction.
      if [ -f "$_EV_STATE_DIR/plan.md" ] \
         && command -v check_evidence_parity >/dev/null 2>&1; then
        _PARITY_ERR=$(check_evidence_parity "$_EV_STATE_DIR" 2>&1 1>/dev/null || true)
        if [ -n "$_PARITY_ERR" ]; then
          # Compose a single-line message for the JSON payload.
          _PARITY_MSG=$(printf '%s' "$_PARITY_ERR" | tr '\n' ';' | sed 's/;$//')
          printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: plan.md evidence-flows contract not satisfied — %s. Required: each declared flow must have ≥1 matching file under %s/evidence/. Conventions: browser-verify-*/tia-* require .png, s<N>-* require .webm. Either capture the missing evidence OR amend evidence-flows in plan.md."}}\n' "$_PARITY_MSG" "$_EV_STATE_DIR"
          exit 0
        fi

        _CUTOVER_INCON=$(check_cutover_consistency "$_EV_STATE_DIR" 2>&1 1>/dev/null || true)
        if [ -n "$_CUTOVER_INCON" ]; then
          # Strip stray quotes for safe JSON embedding.
          _CUTOVER_MSG=$(printf '%s' "$_CUTOVER_INCON" | tr '\n' ' ' | tr -d '"')
          printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: %s"}}\n' "$_CUTOVER_MSG"
          exit 0
        fi
      fi
      # ---------- End evidence-flows contract enforcement ----------

      # ---------- Cutover phase enforcement ----------
      # When $STATE_DIR/plan.md declares cutover-phase: true, the gate REQUIRES
      # at least one evidence file with production_path_exercised: true AND
      # harness != "unit-test-mock" in its companion .metadata.json.
      #
      # Round-trip and unit-test-mock evidence cannot prove a cutover because
      # they mock the very boundaries (CSRF, cookies, undici headers, Next.js
      # routing) where cutover bugs live.
      if [ -f "$_EV_STATE_DIR/plan.md" ]; then
        # grep -c emits the count + exits 1 on no-match; swallow the exit and
        # take only the first line so multiline noise can't corrupt the int test.
        _CUTOVER=$(grep -cE '^[[:space:]]*cutover-phase:[[:space:]]*true[[:space:]]*$' "$_EV_STATE_DIR/plan.md" 2>/dev/null | head -1)
        _CUTOVER="${_CUTOVER:-0}"
        if [ "$_CUTOVER" -gt 0 ] 2>/dev/null; then
          _PROD_OK=0
          if [ -d "$_EV_STATE_DIR/evidence" ]; then
            for _meta in "$_EV_STATE_DIR"/evidence/*.metadata.json; do
              [ -f "$_meta" ] || continue
              _exercised=$(jq -r '.production_path_exercised // false' "$_meta" 2>/dev/null || echo "false")
              _harness=$(jq -r '.harness // ""' "$_meta" 2>/dev/null || echo "")
              if [ "$_exercised" = "true" ] && [ "$_harness" != "unit-test-mock" ] && [ -n "$_harness" ]; then
                _PROD_OK=$((_PROD_OK + 1))
              fi
            done
          fi
          if [ "$_PROD_OK" -lt 1 ]; then
            printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: plan.md declares cutover-phase: true but no evidence under %s/evidence/ has production_path_exercised: true with non-mock harness in its .metadata.json. Cutover phases require real-environment verification (real server + real browser + real session). Round-trip / unit-test-mock evidence is insufficient. See ${CLAUDE_PLUGIN_ROOT}/rules/orchestration.md \\"Cutover phase contract\\"."}}\n' "$_EV_STATE_DIR"
            exit 0
          fi
        fi
      fi
      # ---------- End cutover phase enforcement ----------

      # All checks passed — allow PR creation.
      exit 0
    fi
    # events.jsonl absent — fail-closed.
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: events.jsonl not found. Run /dev <issue> or /qa <issue> to initialize. For ad-hoc fix branches, use /fix [issue] which creates a draft PR with a lighter gate."}}'
    exit 0
  fi
fi

exit 0
