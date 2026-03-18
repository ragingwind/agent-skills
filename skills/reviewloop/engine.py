#!/usr/bin/env python3
"""Review Loop Engine — core logic for bidirectional review loop.

Called by hooks/review-loop-stop.sh on Stop events, or inline via
  python3 engine.py --inline --cwd <path>

Reads state from .claude/review-loop.local.md, invokes reviewer agent
in the background, posts results as PR comments, and returns hook
decision JSON.
"""

import concurrent.futures
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import threading

import yaml

PLUGIN_ROOT = os.environ.get(
    "CLAUDE_PLUGIN_ROOT", os.path.dirname(os.path.abspath(__file__))
)
CONFIG_PATH = os.path.join(PLUGIN_ROOT, "config.yaml")


def get_branch_slug(cwd):
    """Get sanitized current branch name for use as directory name.

    Returns a filesystem-safe slug (e.g., 'feat/auth' → 'feat-auth').
    Falls back to 'default' if branch detection fails.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            # Sanitize: replace / and other unsafe chars with -
            slug = re.sub(r"[^a-zA-Z0-9._-]", "-", branch)
            return slug
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "default"


def get_project_slug(cwd):
    """Get a filesystem-safe slug from the project directory path.

    Mirrors Claude Code's project slug convention (path separators → dashes).
    e.g., '/Users/me/Workspaces/my-app' → 'Users-me-Workspaces-my-app'
    """
    normalized = os.path.normpath(cwd).lstrip(os.sep)
    return re.sub(r"[^a-zA-Z0-9._-]", "-", normalized)


def get_reviewloops_dir(cwd, branch_slug=None):
    """Get the per-project, per-branch reviewloops directory path.

    Returns: ~/.claude/plugins/reviewloop/<project-slug>/<branch>/
    Creates the directory if it doesn't exist.
    """
    if branch_slug is None:
        branch_slug = get_branch_slug(cwd)
    base = os.path.join(
        os.path.expanduser("~"), ".claude", "plugins", "reviewloop"
    )
    dirpath = os.path.join(base, get_project_slug(cwd), branch_slug)
    os.makedirs(dirpath, exist_ok=True)
    return dirpath


def load_config():
    """Load review loop configuration."""
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def parse_state(state_path):
    """Parse YAML frontmatter from state file."""
    with open(state_path) as f:
        content = f.read()

    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None

    return yaml.safe_load(match.group(1))


def update_state(state_path, state):
    """Write updated state back to file."""
    frontmatter = yaml.dump(state, default_flow_style=False, allow_unicode=True)
    with open(state_path, "w") as f:
        f.write(f"---\n{frontmatter}---\n")


def run_cmd(cmd, timeout=30, cwd=None):
    """Run a shell command and return stdout."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def notify(title, message, cwd=None, desktop=False):
    """Send event notification via event log file and optionally desktop.

    The event log file (.claude/reviewloop-events.log) allows the
    orchestrator to poll for progress and display it in the terminal.
    Desktop notifications (via terminal-notifier) are sent only when
    desktop=True (controlled by config defaults.desktop_notification).
    """
    # Append to event log file (for orchestrator polling)
    if cwd:
        import datetime
        rl_dir = get_reviewloops_dir(cwd)
        event_log = os.path.join(rl_dir, "reviewloop-events.log")
        try:
            with open(event_log, "a") as f:
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                f.write(f"[{ts}] {title}: {message}\n")
        except OSError:
            pass

    # macOS desktop notification (optional)
    if desktop:
        try:
            subprocess.run(
                ["terminal-notifier", "-title", title, "-message", message, "-sound", "default"],
                capture_output=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass


def _in_tmux():
    """Check if we're running inside a tmux session."""
    return bool(os.environ.get("TMUX"))


def _tmux_log_pane(log_path, title):
    """Open a tmux split pane that tail -f's the log file. Returns pane ID or None."""
    if not _in_tmux():
        return None
    try:
        result = subprocess.run(
            [
                "tmux", "split-window", "-h", "-d",
                "-p", "35",
                "-P", "-F", "#{pane_id}",
                "bash", "-c",
                f"printf '\\033]0;{title}\\007'; tail -f {shlex.quote(log_path)}",
            ],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _tmux_close_pane(pane_id):
    """Close a tmux pane by ID."""
    if not pane_id:
        return
    try:
        subprocess.run(
            ["tmux", "kill-pane", "-t", pane_id],
            capture_output=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def approve():
    """Output approve decision and exit."""
    print(json.dumps({"decision": "approve"}))
    sys.exit(0)


def block(reason):
    """Output block decision with reason and exit."""
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def post_pr_comment(state, body):
    """Post a comment on the PR — single source of truth for all exchanges."""
    tag = f"<!-- reviewloop:round-{state['round']} -->"
    tagged_body = f"{tag}\n{body}"
    subprocess.run(
        [
            "gh", "pr", "comment", str(state["pr_number"]),
            "-R", state["repo"], "--body", tagged_body,
        ],
        capture_output=True, text=True, timeout=30,
    )


def get_pr_review_comments(state):
    """Get previous review loop comments from PR."""
    tag = "reviewloop"
    comments_json = run_cmd(
        f"gh api repos/{state['repo']}/issues/{state['pr_number']}/comments "
        f"--jq '[.[] | select(.body | contains(\"<!-- {tag}:\"))] | .[].body'",
        timeout=15,
    )
    return comments_json


def extract_implementer_summary(hook_input, cwd):
    """Extract a summary of what the implementer did from recent commits."""
    log = run_cmd(
        "git log --oneline -5 --no-decorate", timeout=10, cwd=cwd
    )
    return log if log else "(no recent commits)"


def format_impl_comment(round_num, summary):
    """Format implementer response as PR comment."""
    return (
        f"## 🔄 Implementer Response (Round {round_num})\n\n"
        f"**Recent changes:**\n```\n{summary}\n```\n"
    )


def format_review_comment(round_num, reviewer_name, verdict, response):
    """Format reviewer response as PR comment."""
    return (
        f"## 🔄 Review (Round {round_num}) — {reviewer_name}\n\n"
        f"{response}\n"
    )


def _strip_markdown_inline(text):
    """Strip common markdown inline formatting: bold, italic, code spans."""
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)  # *italic*, **bold**, ***both***
    text = re.sub(r"`(.*?)`", r"\1", text)                # `code`
    return text.strip()


def parse_verdict(response):
    """Parse VERDICT line from reviewer response.

    Returns (verdict, findings_text).
    verdict is one of: APPROVED, CHANGES_REQUIRED, NEEDS_DISCUSSION, or UNKNOWN.
    Handles markdown-formatted verdict lines (e.g., **VERDICT: APPROVED**).
    """
    lines = response.strip().split("\n")

    verdict = "UNKNOWN"
    for line in reversed(lines):
        cleaned = _strip_markdown_inline(line.strip())
        match = re.match(r"^VERDICT:\s*(APPROVED|CHANGES_REQUIRED|NEEDS_DISCUSSION)", cleaned)
        if match:
            verdict = match.group(1)
            break

    # Findings = everything except the verdict line
    findings_lines = [l for l in lines if not re.match(
        r"^VERDICT:\s*", _strip_markdown_inline(l.strip())
    )]
    findings = "\n".join(findings_lines).strip()

    return verdict, findings


def parse_reviewers(reviewer_str, config=None):
    """Parse reviewer string into a list, filtering out disabled agents.

    Supports:
    - "all": returns all enabled agent keys from config
    - comma-separated: "claude,opencode" → ["claude", "opencode"]
    - single: "claude" → ["claude"]

    Agents with `enabled: false` in config are excluded.
    """
    if not reviewer_str:
        return []
    if reviewer_str.strip().lower() == "all":
        if config and "agents" in config:
            return [
                k for k, v in config["agents"].items()
                if v.get("enabled", True)
            ]
        return []
    names = [r.strip() for r in reviewer_str.split(",") if r.strip()]
    # Filter disabled agents even when explicitly listed
    if config and "agents" in config:
        return [
            n for n in names
            if config["agents"].get(n, {}).get("enabled", True)
        ]
    return names


# Verdict severity order: higher index = stricter
_VERDICT_SEVERITY = {
    "APPROVED": 0,
    "UNKNOWN": 1,
    "NEEDS_DISCUSSION": 2,
    "CHANGES_REQUIRED": 3,
}


def aggregate_verdicts(results):
    """Aggregate multiple reviewer verdicts. Strictest verdict wins.

    Args:
        results: list of (reviewer_name, verdict, findings, response) tuples

    Returns:
        (final_verdict, combined_findings, all_responses)
    """
    if not results:
        return "UNKNOWN", "", ""

    strictest = "APPROVED"
    all_findings = []
    all_responses = []

    for name, verdict, findings, response in results:
        if _VERDICT_SEVERITY.get(verdict, 1) > _VERDICT_SEVERITY.get(strictest, 0):
            strictest = verdict
        if findings:
            all_findings.append(f"### {name}\n{findings}")
        all_responses.append(f"### {name}\n{response}")

    return strictest, "\n\n".join(all_findings), "\n\n".join(all_responses)


def build_prompt(state, config, pr_view, pr_comments, pr_diff, cwd):
    """Assemble the full reviewer prompt from config templates + PR data."""
    prompts = config["prompts"]
    output_cfg = config.get("output", {})
    max_diff = output_cfg.get("max_diff_bytes", 51200)

    # Truncate diff if too large
    if len(pr_diff.encode("utf-8", errors="replace")) > max_diff:
        pr_diff = pr_diff[:max_diff] + "\n\n... (truncated, full diff available via gh pr diff)"

    # Project-specific custom context
    custom_ctx = ""
    ctx_file = os.path.join(cwd, ".claude/review-context.md")
    if os.path.exists(ctx_file):
        with open(ctx_file) as f:
            custom_ctx = f.read()

    # Variable substitution map
    variables = {
        "pr_number": str(state["pr_number"]),
        "round": str(state["round"]),
        "max_rounds": str(state["max_rounds"]),
        "pr_description": pr_view,
        "pr_comments": pr_comments,
        "pr_diff": pr_diff,
        "custom_context": custom_ctx,
    }

    # Assemble sections
    sections = [
        prompts["preamble"],
        f"## PR Description\n{pr_view}",
    ]

    if pr_comments:
        sections.append(f"## Previous Review Comments\n{pr_comments}")

    if custom_ctx:
        sections.append(f"## Project Context\n{custom_ctx}")

    sections.extend([
        f"## Current Diff\n```diff\n{pr_diff}\n```",
        prompts["diff_review"],
        prompts["holistic_review"],
        prompts["verdict_instructions"],
    ])

    full_prompt = "\n\n".join(s for s in sections if s)

    # Variable substitution
    for k, v in variables.items():
        full_prompt = full_prompt.replace(f"{{{k}}}", v)

    return full_prompt


def _stream_process(proc, timeout, log_path):
    """Read stdout line-by-line, tee to log file, enforce wall-clock timeout."""
    timer = threading.Timer(timeout, lambda: proc.kill())
    timer.start()
    output_lines = []
    log_file = open(log_path, "w") if log_path else None
    try:
        for line in proc.stdout:
            output_lines.append(line)
            if log_file:
                log_file.write(line)
                log_file.flush()
        proc.wait(timeout=10)
    finally:
        timer.cancel()
        if log_file:
            log_file.close()

    if proc.returncode != 0:
        stderr_out = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"Agent exited {proc.returncode}: {stderr_out[:500]}")
    return "".join(output_lines)


def invoke_agent(agent_config, prompt_file, cwd, log_path=None):
    """Invoke the reviewer agent CLI and return stdout (headless)."""
    cmd = agent_config["command"]
    mode = agent_config.get("prompt_mode", "stdin")
    timeout = agent_config.get("timeout", 300)

    # Strip CLAUDECODE to bypass nested-session detection.
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    if mode == "stdin":
        with open(prompt_file) as f:
            prompt_text = f.read()
        proc = subprocess.Popen(
            cmd, shell=True, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=cwd, env=env,
        )
        proc.stdin.write(prompt_text)
        proc.stdin.close()
        return _stream_process(proc, timeout, log_path)

    elif mode == "arg":
        with open(prompt_file) as f:
            prompt_text = f.read()
        full_cmd = f"{cmd} {shlex.quote(prompt_text)}"
        proc = subprocess.Popen(
            full_cmd, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=cwd, env=env,
        )
        return _stream_process(proc, timeout, log_path)

    elif mode == "file":
        full_cmd = cmd.replace("{prompt_file}", shlex.quote(prompt_file))
        proc = subprocess.Popen(
            full_cmd, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=cwd, env=env,
        )
        return _stream_process(proc, timeout, log_path)

    else:
        raise ValueError(f"Unknown prompt_mode: {mode}")


def main():
    # --inline mode: read cwd from argv instead of stdin (for in-session use)
    if "--inline" in sys.argv:
        if "--cwd" in sys.argv:
            idx = sys.argv.index("--cwd")
            cwd = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else os.getcwd()
        else:
            cwd = os.getcwd()
        hook_input = {"cwd": cwd}
    else:
        hook_input = json.loads(sys.stdin.read())
        cwd = hook_input.get("cwd", os.getcwd())

    # State file is per-project, per-branch under ~/.claude/plugins/reviewloop/
    branch_slug = get_branch_slug(cwd)
    rl_dir = get_reviewloops_dir(cwd, branch_slug)
    state_path = os.path.join(rl_dir, "review-loop.local.md")

    # No state file → not in a review loop
    if not os.path.exists(state_path):
        approve()
        return

    state = parse_state(state_path)
    if not state or not state.get("active"):
        approve()
        return

    if state.get("phase") != "implementing":
        approve()
        return

    # Load config
    try:
        config = load_config()
    except Exception as e:
        sys.stderr.write(f"reviewloop: config error: {e}\n")
        state["phase"] = "error"
        update_state(state_path, state)
        notify("Review Loop Error", f"Config error: {e}", cwd=cwd)
        approve()
        return

    desktop_notify = config["defaults"].get("desktop_notification", False)

    # Increment round
    state["round"] = state.get("round", 0) + 1

    # Max rounds check
    max_rounds = state.get("max_rounds", config["defaults"]["max_rounds"])
    if state["round"] > max_rounds:
        state["phase"] = "max_rounds"
        update_state(state_path, state)
        post_pr_comment(
            state,
            f"⚠️ Review loop ended: max rounds ({max_rounds}) reached.",
        )
        approve()
        return

    pr = state["pr_number"]
    repo = state["repo"]

    # --- Event: collecting PR data ---
    notify("Review Loop", f"Round {state['round']}: collecting PR data...", cwd=cwd, desktop=desktop_notify)

    pr_diff = run_cmd(f"gh pr diff {pr} -R {repo}", timeout=30)
    pr_comments = get_pr_review_comments(state)
    pr_view = run_cmd(f"gh pr view {pr} -R {repo}", timeout=15)

    # Post implementer summary
    impl_summary = extract_implementer_summary(hook_input, cwd)
    post_pr_comment(state, format_impl_comment(state["round"], impl_summary))

    # Build reviewer prompt
    prompt = build_prompt(state, config, pr_view, pr_comments, pr_diff, cwd)

    # Write prompt to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", prefix="reviewloop-prompt-", delete=False
    ) as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        # Parse reviewer list (supports comma-separated: "claude,opencode")
        reviewer_str = state.get("reviewer", config["defaults"]["reviewer"])
        reviewer_names = parse_reviewers(reviewer_str, config=config)
        strategy = config["defaults"].get("review_strategy", "parallel")

        # Validate all reviewers exist and are available
        valid_reviewers = []
        for rname in reviewer_names:
            agent_cfg = config["agents"].get(rname)
            if not agent_cfg:
                notify("Review Loop Error", f"Unknown agent: {rname}, skipping", cwd=cwd, desktop=desktop_notify)
                continue
            check_cmd = agent_cfg.get("check", "")
            if check_cmd:
                check_result = subprocess.run(
                    check_cmd, shell=True, capture_output=True, timeout=5
                )
                if check_result.returncode != 0:
                    notify("Review Loop Error", f"Agent '{rname}' not available, skipping", cwd=cwd, desktop=desktop_notify)
                    continue
            valid_reviewers.append(rname)

        # Skip reviewers that already APPROVED in a previous round
        already_approved = state.get("approved_reviewers", [])
        skipped_approved = []
        if already_approved:
            skipped_approved = [r for r in valid_reviewers if r in already_approved]
            valid_reviewers = [r for r in valid_reviewers if r not in already_approved]
            if skipped_approved:
                notify(
                    "Review Loop",
                    f"Round {state['round']}: skipping already-approved reviewers: {', '.join(skipped_approved)}",
                    cwd=cwd, desktop=desktop_notify,
                )

        # --- Dry-run: show plan and exit without invoking reviewers ---
        dry_run = "--dry-run" in sys.argv
        if dry_run:
            skipped = [r for r in reviewer_names if r not in valid_reviewers and r not in skipped_approved]
            disabled = [
                k for k, v in config["agents"].items()
                if not v.get("enabled", True)
            ]
            plan = {
                "dry_run": True,
                "pr_number": pr,
                "repo": repo,
                "round": state["round"],
                "strategy": strategy,
                "reviewer_spec": reviewer_str,
                "resolved_reviewers": valid_reviewers,
                "skipped_approved": skipped_approved,
                "skipped_reviewers": skipped,
                "disabled_agents": disabled,
                "agents": {
                    r: {
                        "command": config["agents"][r]["command"],
                        "description": config["agents"][r].get("description", r),
                        "timeout": config["agents"][r].get("timeout", 300),
                        "enabled": config["agents"][r].get("enabled", True),
                    }
                    for r in valid_reviewers
                },
            }
            print(json.dumps(plan, indent=2))
            sys.exit(0)

        if not valid_reviewers:
            # All reviewers already approved — loop is done
            if already_approved:
                state["phase"] = "approved"
                update_state(state_path, state)
                post_pr_comment(
                    state,
                    f"✅ Review loop complete: all reviewers previously APPROVED ({', '.join(already_approved)})",
                )
                notify("Review Loop ✅", f"PR #{pr} APPROVED — all reviewers cleared", cwd=cwd, desktop=desktop_notify)
                approve()
                return

            state["phase"] = "error"
            update_state(state_path, state)
            post_pr_comment(
                state,
                f"❌ Review loop error: no valid reviewers found from '{reviewer_str}'",
            )
            notify("Review Loop Error", f"No valid reviewers: {reviewer_str}", cwd=cwd, desktop=desktop_notify)
            approve()
            return

        # --- Event: reviewers started ---
        state["phase"] = "reviewing"
        update_state(state_path, state)

        reviewer_label = ", ".join(valid_reviewers)
        notify(
            "Review Loop",
            f"Round {state['round']}: {len(valid_reviewers)} reviewer(s) ({reviewer_label}) — {strategy}",
            cwd=cwd, desktop=desktop_notify,
        )

        def _run_single_reviewer(rname):
            """Invoke a single reviewer and return (name, verdict, findings, response) or error tuple."""
            agent_cfg = config["agents"][rname]
            log_path = os.path.join(
                rl_dir, f"reviewloop-round-{state['round']}-{rname}.log"
            )
            notify("Review Loop", f"Round {state['round']}: reviewer ({rname}) started", cwd=cwd, desktop=desktop_notify)

            log_pane = _tmux_log_pane(
                log_path, f"Review Round {state['round']} — {rname} — PR #{pr}"
            )
            try:
                response = invoke_agent(agent_cfg, prompt_file, cwd, log_path=log_path)
            except (subprocess.TimeoutExpired, RuntimeError) as e:
                _tmux_close_pane(log_pane)
                notify("Review Loop Error", f"Reviewer {rname} failed: {str(e)[:60]}", cwd=cwd, desktop=desktop_notify)
                return (rname, "ERROR", "", f"Agent error: {e}")
            _tmux_close_pane(log_pane)

            verdict, findings = parse_verdict(response)
            description = agent_cfg.get("description", rname)
            notify("Review Loop", f"Round {state['round']}: {rname} → {verdict}", cwd=cwd, desktop=desktop_notify)

            # Post individual reviewer comment
            post_pr_comment(
                state,
                format_review_comment(state["round"], description, verdict, response),
            )
            return (rname, verdict, findings, response)

        # Execute reviewers: parallel or sequential
        results = []
        if strategy == "parallel" and len(valid_reviewers) > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(valid_reviewers)) as pool:
                futures = {pool.submit(_run_single_reviewer, rn): rn for rn in valid_reviewers}
                for future in concurrent.futures.as_completed(futures):
                    results.append(future.result())
        else:
            for rname in valid_reviewers:
                results.append(_run_single_reviewer(rname))

        # Filter out errors
        ok_results = [r for r in results if r[1] != "ERROR"]
        err_results = [r for r in results if r[1] == "ERROR"]

        if not ok_results:
            state["phase"] = "error"
            update_state(state_path, state)
            post_pr_comment(state, "❌ Review loop error: all reviewers failed")
            notify("Review Loop Error", "All reviewers failed", cwd=cwd, desktop=desktop_notify)
            approve()
            return

        # Aggregate verdicts (include already-approved reviewers as implicit APPROVED)
        implicit_approved = [
            (name, "APPROVED", "", f"(Previously approved in earlier round)")
            for name in already_approved
        ]
        final_verdict, combined_findings, combined_responses = aggregate_verdicts(
            ok_results + implicit_approved
        )

        notify(
            "Review Loop",
            f"Round {state['round']}: all reviewers completed → {final_verdict}",
            cwd=cwd, desktop=desktop_notify,
        )

        # Post error summary if any reviewers failed
        if err_results:
            err_names = ", ".join(r[0] for r in err_results)
            post_pr_comment(
                state,
                f"⚠️ Some reviewers failed: {err_names} (results from remaining reviewers used)",
            )

        # Same-issue detection (based on combined findings)
        findings_hash = hashlib.sha256(combined_findings.encode()).hexdigest()[:12]
        if findings_hash == state.get("same_issue_hash", ""):
            state["same_issue_count"] = state.get("same_issue_count", 0) + 1
        else:
            state["same_issue_count"] = 0
            state["same_issue_hash"] = findings_hash

        same_threshold = config["defaults"].get("same_issue_threshold", 2)
        if state["same_issue_count"] >= same_threshold:
            state["phase"] = "disagreement"
            update_state(state_path, state)
            post_pr_comment(
                state,
                "⚠️ Review loop ended: unresolvable disagreement "
                f"(same findings {state['same_issue_count'] + 1} times).",
            )
            approve()
            return

        # Track reviewers that gave APPROVED this round
        newly_approved = [r[0] for r in ok_results if r[1] == "APPROVED"]
        if newly_approved:
            prev_approved = state.get("approved_reviewers", [])
            state["approved_reviewers"] = list(set(prev_approved + newly_approved))

        # Act on aggregated verdict
        if final_verdict == "APPROVED":
            state["phase"] = "approved"
            update_state(state_path, state)
            verdict_summary = " / ".join(f"{r[0]}={r[1]}" for r in ok_results)
            post_pr_comment(state, f"✅ Review loop complete: APPROVED ({verdict_summary})")
            notify("Review Loop ✅", f"PR #{pr} APPROVED (Round {state['round']})", cwd=cwd, desktop=desktop_notify)
            approve()
        else:
            # CHANGES_REQUIRED or NEEDS_DISCUSSION or UNKNOWN → block
            state["phase"] = "implementing"
            update_state(state_path, state)
            notify(
                "Review Loop ⚠️",
                f"PR #{pr} Round {state['round']}: {final_verdict} — check PR comments",
                cwd=cwd,
                desktop=desktop_notify,
            )
            feedback = (
                f"## Review Feedback (Round {state['round']}) — "
                f"Posted to PR #{state['pr_number']}\n\n"
                f"{combined_responses}\n\n"
                f"---\n"
                f"Address the findings above. For items you disagree with, explain why.\n"
                f"Commit and push your changes — the next review round will run automatically."
            )
            block(feedback)

    finally:
        # Clean up temp file
        try:
            os.unlink(prompt_file)
        except OSError:
            pass


if __name__ == "__main__":
    main()
