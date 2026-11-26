#!/usr/bin/env python3
"""Stamp the tester's answers of one round and copy them into the lead's task
folder as the red team's and QA's answers, with the meta launch.py writes
for a role's run, so `loop.py post`, `gate.py record` and the merge gate
read them as any role's answer.

Usage:
  stamp.py --project OWNER/REPO --task TASK --head SHA --profile PROFILE
           [--round K] [--session-id UUID] [--from MACHINE] [--to MACHINE]

--from is the tester's machine and --to the lead's, each a herdr machine
label or `local` (the default); on a remote one this same file runs over
SSH. On the tester's machine it reads, from the tester folder (`status.py
dir --testing`), round K's `reviews/redteam-<K>.md` and, when QA ran,
`reviews/qa-<K>.md` (K: by default the last round with a red team answer),
and the head of the tester's clone (agent `tester`), which must be --head,
the head the foreman asked it to test. Each answer must end with a
`Verdict:` line. On the lead's machine it writes each as
`reviews/<role>-1-<n>.json` ({"result": <answer>}) and
`<role>-1-<n>.meta.json`, n one past the role's highest, never over a file.
The meta holds the role, agent `tester`, --profile and its model, the head,
when the answer was written (`ended`), ok, the verdict, --session-id, and
the file it came from. A profile that is loop.json's lead_profile is
refused: the gate would refuse it too.

The tester can write in its folder as the lead can in its task folder, so a
stamped answer counts only on the gate's terms, as any role's answer: at the
head, on a profile not the lead's, and, with post_answers, posted whole on
the pull request (`loop.py post`).

Prints one JSON object: {"round": K, "head": SHA, "stamped": [{"role",
"answer", "verdict"}, ...]}.

Exit codes: 1 = refused or a machine failed, 2 = bad arguments, 3 = setup needed.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

TESTING = "~/.local/state/agent-foreman/testing"
TASKS = "~/.local/state/agent-foreman/tasks"
WORK = "~/.cache/agent-foreman/work"
ROLES = ("redteam", "qa")


# --- runs on a machine; standard library only ---------------------------------

def _iso(seconds):
    return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def read(key, task, round=None):
    """Round `round`'s answers in the tester folder, and the tester clone's head."""
    reviews = os.path.expanduser(f"{TESTING}/{key}/{task}/reviews")
    names = os.listdir(reviews) if os.path.isdir(reviews) else []
    rounds = sorted(int(m.group(1)) for m in (re.fullmatch(r"redteam-(\d+)\.md", n) for n in names) if m)
    k = round or (rounds[-1] if rounds else None)
    if k not in rounds:
        return {"error": f"no red team answer for round {k or 'any'} in {reviews}"}
    answers = {}
    for role in ROLES:
        path = os.path.join(reviews, f"{role}-{k}.md")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                answers[role] = {"file": path, "text": f.read(), "ended": _iso(os.path.getmtime(path))}
    clone = os.path.expanduser(f"{WORK}/{key}/{task}/tester")
    head = subprocess.run(["git", "-C", clone, "rev-parse", "HEAD"], capture_output=True, text=True)
    if head.returncode != 0:
        return {"error": f"no tester clone at {clone}: {head.stderr.strip()[:200]}"}
    return {"round": k, "head": head.stdout.strip(), "answers": answers}


def write(key, task, answers):
    """Each {"role", "result", "meta"} into the lead's task folder's reviews/, as `<role>-1-<n>`."""
    folder = os.path.expanduser(f"{TASKS}/{key}/{task}")
    if not os.path.isdir(folder):
        return {"error": f"no task folder at {folder}"}
    try:
        with open(os.path.join(folder, "loop.json"), encoding="utf-8") as f:
            lead = json.load(f).get("lead_profile")
    except (OSError, ValueError, AttributeError):
        lead = None
    if lead and any(a["meta"].get("profile") == lead for a in answers):
        return {"error": f"profile {lead} is the lead's (loop.json); the gate refuses its answers"}
    reviews = os.path.join(folder, "reviews")
    os.makedirs(reviews, exist_ok=True)
    written = []
    for a in answers:
        taken = [int(m.group(1)) for m in (re.fullmatch(rf"{a['role']}-1-(\d+)\.json", n)
                                           for n in os.listdir(reviews)) if m]
        base = os.path.join(reviews, f"{a['role']}-1-{max(taken, default=0) + 1}")
        with open(base + ".json", "x", encoding="utf-8") as f:
            json.dump({"result": a["result"]}, f)
        with open(base + ".meta.json", "x", encoding="utf-8") as f:
            json.dump(a["meta"], f, indent=2)
        written.append(base + ".json")
    return {"written": written}


def run(request):
    op = request.pop("op")
    try:
        return {"read": read, "write": write}[op](**request)
    except (OSError, RuntimeError) as e:
        return {"error": str(e)}


# --- runs on the foreman's machine --------------------------------------------

def stamped(found, head, profile, model, session_id, source):
    """The answers to write, or an error: each with a verdict, at the head asked for."""
    from gate import last_verdict
    if not found["head"].startswith(head):
        return None, f"the tester's clone is at {found['head']}, not at {head}"
    out = []
    for role, answer in found["answers"].items():
        verdict = last_verdict(answer["text"])
        if not verdict:
            return None, f"{answer['file']} ends with no Verdict line"
        meta = {"role": role, "agent": "tester", "profile": profile, "model": model, "head": found["head"],
                "ended": answer["ended"], "ok": True, "verdict": verdict,
                "session_id": session_id, "source": f"{source}:{answer['file']}"}
        out.append({"role": role, "result": answer["text"], "meta": meta})
    return out, None


def main(argv):
    if argv[:1] == ["_run"]:
        print(json.dumps(run(json.loads(argv[1]))))
        return 0
    import clone
    from config import EXIT_SETUP_NEEDED, NAME, REPO, load
    ap = argparse.ArgumentParser(prog="stamp.py", description="the tester's answers as the red team's and QA's")
    ap.add_argument("--project", required=True, metavar="OWNER/REPO")
    ap.add_argument("--task", required=True)
    ap.add_argument("--head", required=True, metavar="SHA", help="the head the tester was asked to test")
    ap.add_argument("--profile", required=True, help="the profile the tester runs on")
    ap.add_argument("--round", type=int, metavar="K")
    ap.add_argument("--session-id", metavar="UUID")
    ap.add_argument("--from", dest="source", default="local", metavar="MACHINE", help="the tester's machine")
    ap.add_argument("--to", dest="dest", default="local", metavar="MACHINE", help="the lead's machine")
    args = ap.parse_args(argv)
    problem = ("--project must look like owner/name" if not REPO.match(args.project) else
               "--task may hold letters, digits, '.', '_' and '-' only" if not NAME.match(args.task) else
               "--head takes a commit SHA" if not re.fullmatch(r"[0-9a-f]{7,64}", args.head) else
               "--round takes a round number, 1 or more" if args.round is not None and args.round < 1 else None)
    if problem:
        print(f"stamp.py: {problem}", file=sys.stderr)
        return 2
    profiles = load(args.project).get("profiles", {})
    if args.profile not in profiles:
        print(f"stamp.py: {args.profile} is not a profile", file=sys.stderr)
        return EXIT_SETUP_NEEDED
    key, me = args.project.replace("/", "-"), sys.modules[__name__]
    try:
        found = clone.on_machine(args.source, {"op": "read", "key": key, "task": args.task, "round": args.round},
                                 module=me)
        if "error" in found:
            raise RuntimeError(found["error"])
        answers, why = stamped(found, args.head, args.profile, profiles[args.profile].get("model"),
                               args.session_id, args.source)
        if why:
            raise RuntimeError(why)
        done = clone.on_machine(args.dest, {"op": "write", "key": key, "task": args.task, "answers": answers},
                                module=me)
        if "error" in done:
            raise RuntimeError(done["error"])
    except (ValueError, RuntimeError) as e:
        print(f"stamp.py: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"round": found["round"], "head": found["head"],
                      "stamped": [{"role": a["role"], "answer": path, "verdict": a["meta"]["verdict"]}
                                  for a, path in zip(answers, done["written"])]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
