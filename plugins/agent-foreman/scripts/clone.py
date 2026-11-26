#!/usr/bin/env python3
"""Every agent that touches files works in its own clone, which this script
makes, recognizes and removes.

A clone lives at `~/.cache/agent-foreman/work/<owner>-<repo>/<task>/<agent>`
on the agent's machine. It is cloned from a local repository (the project's
checkout on that machine, or the lead's clone for a role agent), then its
`origin` is set to the source's `origin` URL and fetched, so `git push` and
`gh` reach GitHub and not the source. It starts detached at --ref with no
local branch; the agent cuts its own. --no-push points origin's push URL
nowhere, for an agent that only judges: `gh` still finds the repository, and
`git push` to origin fails (a push to a URL named outright still works; this
is not a sandbox). A marker in `.git` records that agent-foreman made it.

Usage:
  clone.py make --project OWNER/REPO --task TASK --agent AGENT (--ref REF | --pr N [--ref SHA])
                [--from PATH] [--machine MACHINE] [--no-push] [--fresh] [--force]
                [--instructions-from SHA]
  clone.py check PATH [--machine MACHINE]
  clone.py trust PATH --pane PANE [--machine MACHINE] [--kind KIND] [--timeout SECONDS]
  clone.py remove --project OWNER/REPO --task TASK [--agent AGENT] [--machine MACHINE] [--force]
  clone.py archive --project OWNER/REPO --task TASK [--machine MACHINE]

make: --from defaults to the project's checkout on that machine (its
settings); --ref is what to check out (detached), such as `origin/main` or a
head SHA. An existing clone of the same agent is kept (status `exists`);
--fresh removes it first, under the same rules as remove.
--pr N, for the tester: fetches the pull request's head (`pull/<N>/head`)
from origin into the clone, so any machine's checkout will do, even one that
never saw the lead's branch. --ref then defaults to that head; a --ref
given too (the head the foreman names) is checked out after that fetch.
--instructions-from SHA, for a judging agent: the files an agent reads as
instructions (`.claude/`, `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md`, at any
depth) are put back as commit SHA has them (the base branch's head on GitHub,
fetched from origin when the clone lacks it), so a change to them under
review cannot steer the agent that reviews it. The diff it reviews is the
commits', unchanged. A SHA it cannot get is an error.

check: whether PATH is a clone agent-foreman made under the work root. Only
such a folder's trust question may be answered for the person.

trust: run right after starting an agent in herdr pane PANE, in clone PATH.
It reads the pane every second. When the agent asks whether to trust its
folder, it answers Yes, but only when check says PATH is ours and the pane
runs in PATH. It returns when the agent is idle at its input line, with
"answered" saying whether there was a question. Anything else (not our
clone, `launch.py:` on the screen, no input line within --timeout, default
90) is an error with the screen's last rows; a question it did not answer
goes to the person. KIND is the profile's agent kind (default claude).

remove: one agent's clone, or with no --agent every clone of the task and
its task folder (`~/.local/state/agent-foreman/tasks/<owner>-<repo>/<task>`, the
task's records: archive it first). It refuses a folder without the marker, a
folder holding the caller's working directory, and, unless --force, a clone
with changes to tracked files or, for a clone that can push, commits that are
on no remote.

archive: copies the task folder from MACHINE to the foreman's project folder
(`config.py paths --project` state, `projects/<owner>-<repo>/tasks/<task>`) and
checks that every file arrived. Run it on the foreman's machine.

MACHINE is a herdr machine label, or `local` (the default); a remote machine
runs this same file over SSH. Prints one JSON object.

Exit codes: 1 = refused or git failed, 2 = bad arguments, 3 = setup needed.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

WORK = "~/.cache/agent-foreman/work"
TASKS = "~/.local/state/agent-foreman/tasks"
MARK = "agent-foreman.json"
NO_PUSH = "no-push-from-this-clone"
INSTRUCTIONS = [":(glob)**/.claude/**", ":(glob)**/CLAUDE.md", ":(glob)**/CLAUDE.local.md", ":(glob)**/AGENTS.md"]


# --- runs on the agent's machine; standard library only ---------------------

def _git(*args, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def _root():
    return os.path.realpath(os.path.expanduser(WORK))


def clone_path(key, task, agent):
    return os.path.join(_root(), key, task, agent)


def check(path):
    real = os.path.realpath(os.path.expanduser(path))
    if not real.startswith(_root() + os.sep):
        return {"ours": False, "path": real, "reason": f"not under {WORK}"}
    mark = os.path.join(real, ".git", MARK)
    if not os.path.isfile(mark):
        return {"ours": False, "path": real, "reason": "no agent-foreman marker in .git"}
    with open(mark, encoding="utf-8") as f:
        return {"ours": True, "path": real, **json.load(f)}


def _unsafe(path, push=True, restored=()):
    """Why removing a clone would lose work, or "". A clone that cannot push
    (--no-push) holds a judging agent's checkout of commits that live in the
    lead's clone, so only its tracked-file changes count."""
    changed = [f for f in _git("diff", "--name-only", "HEAD", cwd=path).splitlines() if f not in restored]
    if changed:
        return "changes to tracked files: " + ", ".join(changed[:5])
    if not push:
        return ""
    local = _git("rev-list", "--max-count=5", "HEAD", "--branches", "--not", "--remotes", cwd=path)
    if local:
        return "commits on no remote: " + ", ".join(sha[:9] for sha in local.splitlines())
    return ""


def _remove_one(path, force):
    found = check(path)
    if not found["ours"]:
        return found["reason"]
    here = os.path.realpath(os.getcwd())
    if here == found["path"] or here.startswith(found["path"] + os.sep):
        return "the working directory is inside it; run from outside"
    if not force:
        reason = _unsafe(found["path"], found.get("push", True), set(found.get("restored", [])))
        if reason:
            return reason + " (--force removes it anyway)"
    shutil.rmtree(found["path"])
    return ""


def remove(key, task, agent=None, force=False):
    task_dir = os.path.join(_root(), key, task)
    paths = [clone_path(key, task, agent)] if agent else (
        sorted(os.path.join(task_dir, d) for d in os.listdir(task_dir)) if os.path.isdir(task_dir) else [])
    removed, refused = [], []
    for path in paths:
        if not os.path.exists(path):
            continue
        reason = _remove_one(path, force)
        (refused.append({"path": path, "reason": reason}) if reason else removed.append(path))
    if not agent and not refused:
        records = os.path.join(os.path.expanduser(TASKS), key, task)
        if os.path.isdir(records):
            shutil.rmtree(records)
            removed.append(records)
    for empty in (task_dir, os.path.dirname(task_dir)):
        if os.path.isdir(empty) and not os.listdir(empty):
            os.rmdir(empty)
    return {"removed": removed, "refused": refused}


def restore_instructions(dest, sha):
    """Put the agent-instruction files back as commit `sha` has them. Returns
    the paths it changed."""
    has_commit = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=dest,
                                capture_output=True).returncode == 0
    if not has_commit:
        _git("fetch", "--quiet", "origin", sha, cwd=dest)
    restored = []
    for line in _git("diff", "--name-status", "--no-renames", sha, "HEAD", "--", *INSTRUCTIONS, cwd=dest).splitlines():
        status, path = line.split("\t", 1)
        if status == "A":
            os.remove(os.path.join(dest, path))
        else:
            _git("checkout", "--quiet", sha, "--", path, cwd=dest)
        restored.append(path)
    return restored


def make(key, task, agent, source, ref, fresh=False, force=False, no_push=False, instructions_from=None, pr=None):
    dest = clone_path(key, task, agent)
    if os.path.exists(dest):
        if not fresh:
            found = check(dest)
            if not found["ours"]:
                return {"error": f"{dest} exists and is not a clone agent-foreman made: {found['reason']}"}
            return {"path": dest, "status": "exists", "head": _git("rev-parse", "HEAD", cwd=dest)}
        reason = _remove_one(dest, force)
        if reason:
            return {"error": f"cannot replace {dest}: {reason}"}
    source = os.path.realpath(os.path.expanduser(source))
    if not os.path.isdir(os.path.join(source, ".git")):
        return {"error": f"{source} is not a git checkout"}
    try:
        origin = _git("remote", "get-url", "origin", cwd=source)
    except RuntimeError:
        return {"error": f"{source} has no origin remote to push to"}
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        _git("clone", "--quiet", source, dest)
        _git("remote", "set-url", "origin", origin, cwd=dest)
        if no_push:
            _git("remote", "set-url", "--push", "origin", NO_PUSH, cwd=dest)
        _git("fetch", "--quiet", "--prune", "origin", cwd=dest)
        if pr:
            _git("fetch", "--quiet", "origin", f"pull/{pr}/head", cwd=dest)
            ref = ref or _git("rev-parse", "FETCH_HEAD", cwd=dest)
        _git("checkout", "--quiet", "--detach", ref, cwd=dest)
        # The branch `git clone` made is the source's, not the agent's; the agent cuts its own.
        for branch in _git("for-each-ref", "--format=%(refname:short)", "refs/heads/", cwd=dest).split():
            _git("branch", "--quiet", "-D", branch, cwd=dest)
        restored = restore_instructions(dest, instructions_from) if instructions_from else []
        with open(os.path.join(dest, ".git", MARK), "w", encoding="utf-8") as f:
            json.dump({"project": key, "task": task, "agent": agent, "source": source, "ref": ref, "pr": pr,
                       "push": not no_push, "restored": restored,
                       "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f)
        head = _git("rev-parse", "HEAD", cwd=dest)
    except RuntimeError as e:
        shutil.rmtree(dest, ignore_errors=True)
        return {"error": str(e)}
    return {"path": dest, "status": "made", "origin": origin, "push": not no_push, "head": head,
            "restored": restored}


def run(request):
    op = request.pop("op")
    try:
        return {"make": make, "check": check, "remove": remove}[op](**request)
    except (OSError, RuntimeError) as e:
        return {"error": str(e)}


# --- runs where the command is given ----------------------------------------

def on_machine(label, request, saved=None):
    if label == "local":
        return run(dict(request))
    if saved is None:
        from config import herdr_machines
        saved = herdr_machines()
    if label not in saved:
        raise ValueError(f"{label} is not a saved herdr machine")
    with open(os.path.abspath(__file__), encoding="utf-8") as f:
        source = f.read()
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", saved[label]["target"],
                        "python3 - _run " + shlex.quote(json.dumps(request))],
                       input=source, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{label}: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout)


TRUST_POLL = 1


def _herdr(label, *args):
    command = (["herdr"] if label == "local" else ["herdr", "--machine", label]) + list(args)
    r = subprocess.run(command, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(command)}: {(r.stderr or r.stdout).strip()[:200]}")
    return r.stdout


def _pane(label, pane):
    try:
        data = json.loads(_herdr(label, "pane", "get", pane))
    except ValueError:
        raise RuntimeError(f"herdr pane get {pane} printed no JSON") from None
    if "error" in data:
        raise RuntimeError(f"herdr pane get {pane}: {data['error'].get('message', data['error'])}")
    return data["result"]["pane"]


def _last_rows(screen, n=12):
    return "\n".join([line for line in screen.splitlines() if line.strip()][-n:])


def trust(label, pane, path, kind, timeout, saved=None):
    import adapters
    adapter = adapters.get(kind)
    found = on_machine(label, {"op": "check", "path": path}, saved)
    if found.get("error"):
        return {"ready": False, "answered": False, "error": found["error"]}
    if not found["ours"]:
        return {"ready": False, "answered": False,
                "error": f"{found['path']} is not a clone agent-foreman made ({found['reason']}); "
                         "its trust question goes to the person"}
    answered = False
    end = time.monotonic() + timeout
    while True:
        info = _pane(label, pane)
        screen = _herdr(label, "pane", "read", pane, "--source", "visible", "--lines", "40")
        if adapter.TRUST_SCREEN in screen:
            if not answered:
                where = info.get("foreground_cwd") or info.get("cwd") or ""
                if os.path.normpath(where) != found["path"]:
                    return {"ready": False, "answered": False,
                            "error": f"pane {pane} runs in {where}, not in {found['path']}; "
                                     "its trust question goes to the person"}
                for key in adapter.TRUST_KEYS:
                    _herdr(label, "pane", "send-keys", pane, key)
                answered = True
        elif info.get("agent_status") == "idle":
            return {"ready": True, "answered": answered}
        elif "launch.py:" in screen and not info.get("agent"):
            return {"ready": False, "answered": answered, "error": "launch.py stopped; read its exit line",
                    "screen": _last_rows(screen)}
        if time.monotonic() >= end:
            return {"ready": False, "answered": answered,
                    "error": f"no input line within {timeout} seconds", "screen": _last_rows(screen)}
        time.sleep(TRUST_POLL)


def archive(label, key, task, dest, saved=None):
    """Copy a task folder from a machine to `dest` on this one, then compare
    the file lists. Returns {"archived": dest, "files": n} or {"error": ...}."""
    src = f"{TASKS}/{key}/{task}"
    os.makedirs(dest, exist_ok=True)
    if label == "local":
        root = os.path.expanduser(src)
        if not os.path.isdir(root):
            return {"error": f"no task folder at {root}"}
        shutil.copytree(root, dest, dirs_exist_ok=True)
        want = sorted(os.path.relpath(os.path.join(d, n), root) for d, _, ns in os.walk(root) for n in ns)
    else:
        if saved is None:
            from config import herdr_machines
            saved = herdr_machines()
        if label not in saved:
            raise ValueError(f"{label} is not a saved herdr machine")
        target = saved[label]["target"]
        quoted = src.replace("~/", "$HOME/", 1)
        listing = subprocess.run(["ssh", "-o", "BatchMode=yes", target, f'cd "{quoted}" && find . -type f'],
                                 capture_output=True, text=True)
        if listing.returncode != 0:
            return {"error": f"no task folder at {src} on {label}: {listing.stderr.strip()[:200]}"}
        want = sorted(os.path.normpath(l) for l in listing.stdout.split("\n") if l.strip())
        pack = subprocess.Popen(["ssh", "-o", "BatchMode=yes", target, f'tar -C "{quoted}" -cf - .'],
                                stdout=subprocess.PIPE)
        unpack = subprocess.run(["tar", "-C", dest, "-xf", "-"], stdin=pack.stdout, capture_output=True)
        pack.wait()
        if pack.returncode != 0 or unpack.returncode != 0:
            return {"error": f"copying from {label} failed: {unpack.stderr.decode(errors='replace')[:200]}"}
    got = {os.path.relpath(os.path.join(d, n), dest) for d, _, ns in os.walk(dest) for n in ns}
    lost = [f for f in want if f not in got]
    if lost:
        return {"error": f"{len(lost)} file(s) did not arrive: {', '.join(lost[:5])}"}
    return {"archived": dest, "files": len(want)}


def main(argv):
    if argv[:1] == ["_run"]:
        print(json.dumps(run(json.loads(argv[1]))))
        return 0
    from config import EXIT_SETUP_NEEDED, NAME, REPO, load
    ap = argparse.ArgumentParser(prog="clone.py", description="agent-foreman agent clones")
    ap.add_argument("command", choices=["make", "check", "trust", "remove", "archive"])
    ap.add_argument("path", nargs="?")
    ap.add_argument("--pane", help="trust: the herdr pane the agent starts in")
    ap.add_argument("--kind", default="claude", help="trust: the profile's agent kind")
    ap.add_argument("--timeout", type=int, default=90, help="trust: seconds to wait for the input line")
    ap.add_argument("--project", metavar="OWNER/REPO")
    ap.add_argument("--task")
    ap.add_argument("--agent")
    ap.add_argument("--ref")
    ap.add_argument("--pr", type=int, help="make: fetch this pull request's head and start there")
    ap.add_argument("--from", dest="source", metavar="PATH")
    ap.add_argument("--machine", default="local")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--instructions-from", metavar="SHA",
                    help="make: put the agent-instruction files back as this commit has them")
    args = ap.parse_args(argv)

    def bad(message):
        print(f"clone.py: {message}", file=sys.stderr)
        return 2

    if args.command == "check":
        if not args.path:
            return bad("check needs a path")
        request = {"op": "check", "path": args.path}
    elif args.command == "trust":
        if not (args.path and args.pane):
            return bad("trust needs the clone's path and --pane")
        if args.timeout < 1:
            return bad("--timeout must be at least 1")
        import adapters
        if args.kind not in adapters.KINDS:
            return bad(f"--kind must be one of: {', '.join(adapters.KINDS)}")
        try:
            out = trust(args.machine, args.pane, args.path, args.kind, args.timeout)
        except (ValueError, RuntimeError) as e:
            print(f"clone.py: {e}", file=sys.stderr)
            return 1
        print(json.dumps({"machine": args.machine, **out}, indent=2))
        return 0 if out["ready"] else 1
    else:
        if not (args.project and REPO.match(args.project)):
            return bad("--project must look like owner/name")
        if not (args.task and NAME.match(args.task)):
            return bad("--task may hold letters, digits, '.', '_' and '-' only")
        if args.agent is not None and not NAME.match(args.agent):
            return bad("--agent may hold letters, digits, '.', '_' and '-' only")
        key = args.project.replace("/", "-")
        if args.command == "archive":
            from config import project_dir
            try:
                out = archive(args.machine, key, args.task, os.path.join(project_dir(args.project), "tasks", args.task))
            except (ValueError, RuntimeError) as e:
                print(f"clone.py: {e}", file=sys.stderr)
                return 1
            print(json.dumps({"machine": args.machine, **out}, indent=2))
            return 1 if out.get("error") else 0
        if args.command == "remove":
            request = {"op": "remove", "key": key, "task": args.task, "agent": args.agent, "force": args.force}
        else:
            if args.pr is not None and args.pr < 1:
                return bad("--pr takes a pull request number")
            if not (args.agent and (args.ref or args.pr)):
                return bad("make needs --agent, and --ref or --pr")
            source = args.source or load(args.project).get("machines", {}).get(args.machine)
            if not source:
                print(f"clone.py: no --from, and project {args.project} names no checkout on {args.machine}",
                      file=sys.stderr)
                return EXIT_SETUP_NEEDED
            if args.instructions_from and not re.fullmatch(r"[0-9a-f]{7,64}", args.instructions_from):
                return bad("--instructions-from takes a commit SHA, such as the base branch's head on GitHub")
            request = {"op": "make", "key": key, "task": args.task, "agent": args.agent, "source": source,
                       "ref": args.ref, "fresh": args.fresh, "force": args.force, "no_push": args.no_push,
                       "instructions_from": args.instructions_from, "pr": args.pr}
    try:
        out = on_machine(args.machine, request)
    except (ValueError, RuntimeError) as e:
        print(f"clone.py: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"machine": args.machine, **out}, indent=2))
    return 1 if out.get("error") or out.get("refused") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
