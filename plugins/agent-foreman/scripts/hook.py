#!/usr/bin/env python3
"""Hook commands of Codex agents; adapters/codex.py passes them with -c.

  hook.py session            SessionStart: keep Codex's own session id under
                             the id the foreman chose (AF_SESSION_ALIAS), so
                             transcript.py and launch.py --resume find it
  hook.py guard [--no-edit]  PreToolUse: refuse `gh pr merge`, since the
                             foreman merges, and with --no-edit the edit tool

A refused call exits 2 with the reason on stderr, which Codex shows the
agent. Anything else that goes wrong lets the call through and prints
nothing, so a hook never breaks the agent.
"""
import json
import os
import re
import sys

from adapters.base import NEVER_MERGE
from adapters.codex import EDIT_TOOLS, record_session

MERGE = re.compile(r"\b" + r"\s+".join(map(re.escape, NEVER_MERGE.split())) + r"\b")


def refusal(data, no_edit):
    if no_edit and data.get("tool_name") in EDIT_TOOLS:
        return "this agent judges the change and edits no file"
    if MERGE.search(json.dumps(data.get("tool_input"))):
        return "the foreman merges pull requests; an agent never runs gh pr merge"
    return None


def main(argv):
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(data, dict):
        return 0
    if argv[:1] == ["session"]:
        if os.environ.get("AF_SESSION_ALIAS") and isinstance(data.get("session_id"), str):
            record_session(os.environ["AF_SESSION_ALIAS"], data)
        return 0
    if argv[:1] == ["guard"]:
        reason = refusal(data, "--no-edit" in argv[1:])
        if reason:
            print(reason, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    try:
        code = main(sys.argv[1:])
    except Exception:
        code = 0
    sys.exit(code)
