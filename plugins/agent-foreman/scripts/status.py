#!/usr/bin/env python3
"""Status files: what each lead reports, and what the foreman reads.

A task's records live in one task folder on its machine,
`~/.local/state/agent-foreman/tasks/<owner>-<repo>/<task>/`; its status file is
`status.jsonl` there. launch.py --task-dir hands the folder to an agent as
AF_TASK_DIR and the status file as AF_STATUS_FILE. The bundle's hooks append
`heartbeat` and `turn-end` lines; the lead appends a `start` and an `end` line
for each step it runs, `progress` lines during a long one, and a `stop` line
at a stop point that no step leads to (a decision, blocked). The foreman
writes the verification session's lines with --file.

A task's testing session (its tester, which runs the red team and QA) keeps
its own folder on the tester's machine,
`~/.local/state/agent-foreman/testing/<owner>-<repo>/<task>/`: its brief,
task.md, the answers it writes in reviews/, and its status.jsonl. It sits
outside tasks/, so nothing takes it for a second copy of the task, and
`dir --testing` and `path --testing` name it.

Every `end` line carries its evidence in --done: the skills the step ran and
where their record is (`plan.md 4 rows; scenario.md 6 steps`, the commits).
`note` refuses an `end` line without it; the foreman checks the evidence
against the records (gate.py record) before the task goes on.

When the task folder holds `loop.json` (loop.py render --json), `note` refuses
a stage or step that is not in the task's loop, and an `end` line without an
--outcome that the step has. When the next step is the foreman's, it says to
stop there and wait. It refuses an `end` line for a step of the foreman's
without --file. A lead never passes --file, so this stops a lead that would
end the foreman's step itself by mistake. It does not stop one that passes
--file on purpose; the foreman's log catches that (SKILL.md, Merge gate). It prints what to do next: at `start`, the step
itself; at `end`, the step the outcome leads to, which it also records as
`to`. An `end` line whose outcome leads to `stop` is a stop point. At a
`start` line written to AF_STATUS_FILE, it renames the agent's herdr tab to
the stage's label (when HERDR_TAB_ID is set).

Usage:
  status.py dir --project OWNER/REPO --task TASK [--testing]
  status.py path --project OWNER/REPO --task TASK [--testing]
  status.py note --stage ID [--step ID] --event start|end|progress|stop [--outcome NAME] [--round N]
                 [--done TEXT] [--blocked TEXT] [--file FILE]
  status.py read --project OWNER/REPO [--machine MACHINE] [--stall MINUTES]

`dir` prints the task folder and `path` its status file, with `~`, for the
machine to expand. `note` writes to
--file, or to AF_STATUS_FILE. `read` reads every task's status file on the
project's machines (one SSH call per remote machine) and prints, per task:
the last stage line with its step, the last heartbeat and its agent, the
minutes since the last line, and `stalled` when that is more than --stall
minutes (default: the settings' ops.stall_minutes) and the lead is not at a
stop point. Under `testing` it prints the same for each task's testing
session, from the tester folders on those machines (status_reader.py runs
on each). Per machine it also prints the free disk space of the home
directory's disk, `low` under the settings' ops.disk_min_free_gb.

Exit codes: 2 = bad arguments, 1 = a machine could not be read.
"""
import argparse
import calendar
import json
import os
import shlex
import subprocess
import sys
import time

from config import LOCAL, NAME, REPO

TASKS = "~/.local/state/agent-foreman/tasks"
TESTING = "~/.local/state/agent-foreman/testing"
READER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "status_reader.py")
EVENTS = ["start", "end", "progress", "stop"]
STOP = "stop"
BEATS = ["heartbeat", "turn-end"]
TAIL = 200


def root_for(repo, testing=False):
    """Where the project's task folders sit: the build sessions', or with `testing` the testers'."""
    return f"{TESTING if testing else TASKS}/{repo.replace('/', '-')}"


def dir_for(repo, task, testing=False):
    return f"{root_for(repo, testing)}/{task}"


def path_for(repo, task, testing=False):
    return f"{dir_for(repo, task, testing)}/status.jsonl"


def load_loop(status_file):
    """The task's loop.json next to the status file, or None."""
    path = os.path.join(os.path.dirname(os.path.abspath(status_file)), "loop.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def check_note(task_loop, stage, step):
    """(the step's entry, problem): a stage line must name a stage of the
    task's loop, and a step in that stage; with no step, the stage's first."""
    steps = [s for w in ("work", "check") for s in task_loop.get(w, [])]
    stages = []
    for s in steps:
        if s["stage"] not in stages:
            stages.append(s["stage"])
    if stage not in stages:
        return None, f"stage {stage!r} is not in this task's loop; its stages are {', '.join(stages)}"
    in_stage = [s for s in steps if s["stage"] == stage]
    if not step:
        return in_stage[0], ""
    found = next((s for s in in_stage if s["id"] == step), None)
    if found is None:
        return None, f"step {step!r} is not in stage {stage}; its steps are {', '.join(s['id'] for s in in_stage)}"
    return found, ""


def step_of(task_loop, step_id):
    return next((s for s in task_loop.get("work", []) + task_loop.get("check", []) if s["id"] == step_id), None)


def describe(task_loop, step_id):
    s = step_of(task_loop, step_id)
    if s is None:
        return step_id
    skills = f" Skills: {', '.join(s['skills'])}." if s.get("skills") else ""
    return f"{s['id']} ({s['stage']}, {s['actor']}): {s['does']}{skills}"


def rename_tab(label):
    tab = os.environ.get("HERDR_TAB_ID")
    if tab and label:
        subprocess.run(["herdr", "tab", "rename", tab, label], capture_output=True)


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_time(text):
    try:
        return calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def summarize(lines, stall_minutes, now=None):
    """One task's state from its status lines."""
    now = time.time() if now is None else now
    rows = []
    for raw in lines:
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    stage = next((r for r in reversed(rows) if r.get("event") in EVENTS), {})
    beat = next((r for r in reversed(rows) if r.get("event") in BEATS), {})
    last = parse_time(rows[-1].get("time")) if rows else None
    since = None if last is None else round((now - last) / 60, 1)
    stopped = stage.get("event") == "stop" or (stage.get("event") == "end" and stage.get("to") == STOP)
    return {"stage": stage.get("stage"), "step": stage.get("step"), "stage_event": stage.get("event"),
            "round": stage.get("round"), "outcome": stage.get("outcome"), "to": stage.get("to"),
            "done": stage.get("done"), "blocked": stage.get("blocked") or "",
            "last_beat": beat.get("event"), "last_beat_agent": beat.get("agent"), "minutes_since": since,
            "stopped": stopped, "stalled": not stopped and (since is None or since > stall_minutes)}


def read_machine(label, repo, saved):
    """{"tasks": {task: [lines]}, "testing": {task: [lines]}, "free_gb": n}
    from one machine (status_reader.py). `saved`: herdr machines, label ->
    info."""
    args = [root_for(repo), root_for(repo, testing=True), str(TAIL)]
    reader = None
    if label == LOCAL:
        argv = [sys.executable, READER, *args]
    else:
        if label not in saved:
            raise ValueError(f"{label} is not a saved herdr machine")
        with open(READER, encoding="utf-8") as f:
            reader = f.read()
        argv = ["ssh", "-o", "BatchMode=yes", saved[label]["target"], "python3 - " + shlex.join(args)]
    out = subprocess.run(argv, capture_output=True, text=True, input=reader)
    if out.returncode != 0:
        raise RuntimeError(f"{label}: {out.stderr.strip()[:300]}")
    return json.loads(out.stdout or "{}")


def main(argv):
    ap = argparse.ArgumentParser(prog="status.py", description="agent-foreman status files")
    ap.add_argument("command", choices=["dir", "path", "note", "read"])
    ap.add_argument("--project", metavar="OWNER/REPO")
    ap.add_argument("--task")
    ap.add_argument("--machine")
    ap.add_argument("--stall", type=float)
    ap.add_argument("--file")
    ap.add_argument("--stage")
    ap.add_argument("--step", default="")
    ap.add_argument("--event", choices=EVENTS)
    ap.add_argument("--outcome", help="with --event end: the outcome of the step, one of its next keys")
    ap.add_argument("--round", type=int)
    ap.add_argument("--done", default="")
    ap.add_argument("--blocked", default="")
    ap.add_argument("--testing", action="store_true", help="dir, path: the task's tester folder")
    args = ap.parse_args(argv)
    if args.project and not REPO.match(args.project):
        print(f"status.py: --project must look like owner/name, not {args.project!r}", file=sys.stderr)
        return 2

    if args.command in ("dir", "path"):
        if not (args.project and args.task):
            print(f"status.py: {args.command} needs --project and --task", file=sys.stderr)
            return 2
        if not NAME.match(args.task):
            print(f"status.py: --task may hold letters, digits, '.', '_' and '-' only, not {args.task!r}",
                  file=sys.stderr)
            return 2
        where = dir_for if args.command == "dir" else path_for
        print(where(args.project, args.task, args.testing))
        return 0

    if args.command == "note":
        path = args.file or os.environ.get("AF_STATUS_FILE")
        if not (path and args.stage and args.event):
            print("status.py: note needs --stage, --event and a status file (--file or AF_STATUS_FILE)",
                  file=sys.stderr)
            return 2
        if args.outcome and args.event != "end":
            print("status.py: --outcome goes with --event end", file=sys.stderr)
            return 2
        if args.event == "end" and not args.done.strip():
            print("status.py: --event end needs --done, the step's evidence: the skills it ran and where their "
                  "record is, such as \"work-breakdown: plan.md 4 rows; cross-check: scenario.md 6 steps\" "
                  "(loop.md, Evidence)", file=sys.stderr)
            return 2
        path = os.path.expanduser(path)
        task_loop = load_loop(path)
        entry, target = None, None
        if task_loop is not None:
            entry, problem = check_note(task_loop, args.stage, args.step)
            if not problem and args.event == "end":
                outcomes = list(entry["next"])
                if entry["actor"] == "foreman" and not args.file:
                    problem = (f"step {entry['id']} is the foreman's, and the foreman writes its end line: write "
                               f"a stop line and report waiting (loop.md, Stop points)")
                elif args.outcome not in outcomes:
                    problem = (f"--event end needs --outcome, one of {', '.join(outcomes)} "
                               f"(step {entry['id']}), not {args.outcome!r}")
                else:
                    target = entry["next"][args.outcome]
            if problem:
                print(f"status.py: {problem}", file=sys.stderr)
                return 2
        row = {"time": now_iso(), "stage": args.stage, "step": args.step or (entry or {}).get("id", ""),
               "event": args.event, "round": args.round, "done": args.done, "blocked": args.blocked}
        if args.outcome:
            row.update(outcome=args.outcome, to=target)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if entry is not None:
            if args.event == "start":
                if not args.file:
                    rename_tab(entry.get("label", "").replace("<N>", str(args.round or 1)))
                print("now: " + describe(task_loop, entry["id"]))
            elif args.event == "end":
                target_step = step_of(task_loop, target)
                if target == STOP:
                    print("next: stop: no step follows; this is a stop point.")
                elif target_step is not None and target_step["actor"] == "foreman" and not args.file:
                    print("next: " + describe(task_loop, target) + " This step is the foreman's: write a stop "
                          "line and report waiting (loop.md, Stop points); the foreman tells you where to go on.")
                else:
                    print("next: " + describe(task_loop, target))
        return 0

    if not args.project:
        print("status.py: read needs --project", file=sys.stderr)
        return 2
    from config import herdr_machines, load
    cfg = load(args.project)
    stall = args.stall if args.stall is not None else cfg["ops"]["stall_minutes"]
    machines = [args.machine] if args.machine else list(cfg.get("machines", {}))
    saved = herdr_machines() if any(m != LOCAL for m in machines) else {}
    floor = cfg["ops"]["disk_min_free_gb"]
    report, testing, disk, failed = {}, {}, {}, []
    for label in machines:
        try:
            found = read_machine(label, args.project, saved)
        except (ValueError, RuntimeError) as e:
            failed.append(str(e))
            continue
        disk[label] = {"free_gb": found["free_gb"], "low": found["free_gb"] < floor}
        for task, lines in found["tasks"].items():
            report[task] = {"machine": label, **summarize(lines, stall)}
        for task, lines in found.get("testing", {}).items():
            testing[task] = {"machine": label, **summarize(lines, stall)}
    print(json.dumps({"stall_minutes": stall, "tasks": report, "testing": testing, "disk": disk,
                      "unreadable": failed}, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
