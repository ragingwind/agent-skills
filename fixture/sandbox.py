#!/usr/bin/env python3
"""A sandbox on GitHub for a live run of agent-foreman: a private repository
that holds the fixture project, with its tasks as issues. Make one for a run,
and delete it after.

fixture/run.py runs the foreman's scripted part on this machine, with a
stand-in for GitHub. A live run in a sandbox covers what run.py leaves out:
real pull requests, CI and merges, setup, the foreman's watching and its
herdr tabs.

Usage:
  python3 fixture/sandbox.py create [--owner OWNER]
  python3 fixture/sandbox.py list [--owner OWNER]
  python3 fixture/sandbox.py delete OWNER/NAME

create makes the private repository OWNER/agent-foreman-sandbox-<UTC time>
from fixture/repo, with the sandbox description, and pushes its main branch.
It then opens one issue per fixture/tasks/<n>.md: the first line, without
its `# `, is the title, and the rest is the body. It prints the repository,
the clone command, the issues and the delete command as JSON. OWNER defaults
to the account `gh` is logged in to.

list prints OWNER's sandboxes: the repositories whose name starts with
agent-foreman-sandbox- and whose description is the sandbox description.

delete removes OWNER/NAME only when it is such a sandbox, and refuses any
other repository. GitHub needs the token scope delete_repo for it
(`gh auth refresh -h github.com -s delete_repo`). It does not remove what the
foreman made for the repository on this machine: its project settings, task
folders and clones.
"""
import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run import GIT, materialize  # noqa: E402

PREFIX = "agent-foreman-sandbox-"
DESCRIPTION = "agent-foreman sandbox, made by fixture/sandbox.py; safe to delete"
OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?")
REPO = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+")
SCOPE = "gh auth refresh -h github.com -s delete_repo"


def gh(*args, cwd=None):
    r = subprocess.run(["gh", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {(r.stderr or r.stdout).strip()[:400]}")
    return r.stdout


def tasks():
    """(task, title, body) for each fixture/tasks/<n>.md, in task order."""
    out = []
    paths = glob.glob(os.path.join(HERE, "tasks", "*.md"))
    for path in sorted(paths, key=lambda p: int(os.path.basename(p)[:-3])):
        with open(path, encoding="utf-8") as f:
            first, _, body = f.read().partition("\n")
        if not first.startswith("# "):
            raise ValueError(f"{path}: the first line is not a `# ` title")
        out.append((os.path.basename(path)[:-3], first[2:].strip(), body.strip() + "\n"))
    return out


def create(owner):
    issues = tasks()
    name = PREFIX + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    repo = f"{owner}/{name}"
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, name)
        materialize(os.path.join(HERE, "repo"), src)
        for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "Start the stock project"]):
            r = subprocess.run(GIT + ["-C", src, *args], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(f"git {args[0]} failed: {(r.stderr or r.stdout).strip()[:400]}")
        gh("repo", "create", repo, "--private", "--description", DESCRIPTION, "--source", src, "--remote", "origin",
           "--push")
    made = []
    try:
        for task, title, body in issues:
            url = gh("issue", "create", "--repo", repo, "--title", title, "--body", body).strip().splitlines()[-1]
            made.append({"task": task, "number": int(url.rsplit("/", 1)[1]), "title": title, "url": url})
    except (RuntimeError, ValueError, IndexError) as e:
        raise RuntimeError(f"{e}. {repo} was made; delete it with `python3 fixture/sandbox.py delete {repo}`")
    return {"repo": repo, "url": f"https://github.com/{repo}", "clone": f"gh repo clone {repo}", "issues": made,
            "delete": f"python3 fixture/sandbox.py delete {repo}"}


def is_sandbox(info):
    return info.get("name", "").startswith(PREFIX) and info.get("description") == DESCRIPTION


def listed(owner):
    rows = json.loads(gh("repo", "list", owner, "--limit", "1000", "--json",
                         "nameWithOwner,name,description,visibility,createdAt"))
    return [{"repo": r["nameWithOwner"], "visibility": r["visibility"], "created": r["createdAt"]}
            for r in rows if is_sandbox(r)]


def delete(repo):
    info = json.loads(gh("repo", "view", repo, "--json", "name,description"))
    if not is_sandbox(info):
        raise ValueError(f"{repo} is not a sandbox this script made: its name does not start with {PREFIX} or its "
                         f"description is not the sandbox description. Nothing was deleted")
    try:
        gh("repo", "delete", repo, "--yes")
    except RuntimeError as e:
        raise RuntimeError(f"{e}. Deleting needs the token scope delete_repo: `{SCOPE}`")
    return {"repo": repo, "deleted": True}


def main(argv):
    ap = argparse.ArgumentParser(prog="sandbox.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["create", "list", "delete"])
    ap.add_argument("repo", nargs="?", metavar="OWNER/NAME", help="delete: the sandbox to delete")
    ap.add_argument("--owner", help="create, list: the account or organization (default: the logged-in account)")
    args = ap.parse_args(argv)
    if args.command == "delete":
        if not args.repo or not REPO.fullmatch(args.repo):
            print("sandbox.py: delete needs OWNER/NAME", file=sys.stderr)
            return 2
        if args.owner:
            print("sandbox.py: delete takes no --owner; the owner is in OWNER/NAME", file=sys.stderr)
            return 2
    elif args.repo:
        print(f"sandbox.py: {args.command} takes no OWNER/NAME", file=sys.stderr)
        return 2
    if args.owner is not None and not OWNER.fullmatch(args.owner):
        print(f"sandbox.py: --owner must be a GitHub account or organization name, not {args.owner!r}",
              file=sys.stderr)
        return 2
    try:
        if args.command == "delete":
            out = delete(args.repo)
        else:
            owner = args.owner or gh("api", "user", "--jq", ".login").strip()
            out = create(owner) if args.command == "create" else listed(owner)
    except (RuntimeError, ValueError) as e:
        print(f"sandbox.py: {e}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
