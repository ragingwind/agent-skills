#!/usr/bin/env python3
"""Facts for the foreman's retro: what happened in a project's finished
tasks, read from their archived task folders and the project's log. Facts
only: the foreman reads them against the loop and proposes changes to the
person, who decides.

Usage:
  retro.py facts --project OWNER/REPO [--task TASK ...] [--since TIME]

It reads each `<project folder>/tasks/<task>/` (clone.py archive puts a
finished task's folder there): loop.json, status.jsonl, reviews/ and
gates.jsonl; and the project's log.jsonl. --task picks tasks (repeat it);
--since keeps the tasks whose last status line is at or after TIME
(`YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SSZ`, such as the last retro's): the tasks
that finished since. The lead could write in these folders, so a line or
file of the wrong shape is skipped and named under `unreadable`, never
trusted or fatal.

Prints one JSON object:
  tasks       per task: difficulty, trivial, the last round, minutes per
              step, each time it went back (from a step to an earlier one),
              its stop lines, its review findings by role, its gate runs and
              what blocked, its log events, and its idle time (below)
  steps       per step over the tasks: how many ran it, total and median
              minutes, how often a task went back to it and from where, and
              the skills it used
  roles       per role: its verdicts, and its findings by severity with
              their lines and tasks
  gate        per check: how many runs it blocked and warned in
  idle        the tasks' idle time, summed
  events      the log events of those tasks, counted (stall, exited, ...)
  open        the open items the last setup left (the `setup` log event)
  previous    the last retro (the `retro` log event): what it changed and
              the facts it expected to change
  unreadable  files or lines that could not be read

Idle time is the time when none of the task's steps was running, between
its first step line and its last. A step runs from its `start` (or a
`progress` line) to its `end` or `stop`; a work-loop step that starts ends
any other work-loop step left open, since the lead runs one at a time.
Each gap goes to the line before it: `end <step> (<outcome>)`, or `stop
<step> (<kind>)` with the kind its REPORT names (ready, decision, blocked,
waiting). `idle` holds `minutes`, `span_minutes` and `by_event`.

Exit codes: 2 = bad arguments.
"""
import argparse
import calendar
import glob
import json
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict

from config import REPO, log_path, project_dir
from status import parse_time

SEVERITIES = ("must-fix", "should-fix", "could", "mismatch")
STEP_EVENTS = ("start", "end", "progress", "stop")
LINE_MAX = 200
FINDING = re.compile(r"^(?:[-*+]|\d+[.)])?\s*[*_]*(must-fix|should-fix|could)[*_]*\s*:\s*(.*)$|"
                     r"^(?:[-*+]|\d+[.)])?\s*[*_]*(mismatch)[*_]*\s*\(", re.I)
NO_FINDING = {"", "none", "none.", "n/a", "-"}
STOP_KIND = re.compile(r"^(?:REPORT:\s*)?(ready|decision|blocked|waiting)\b", re.I)


def since_time(text):
    """Seconds since the epoch of `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SSZ`, or None."""
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return calendar.timegm(time.strptime(text, fmt))
        except (TypeError, ValueError):
            continue
    return None


def read_jsonl(path, unreadable):
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    unreadable.append(f"{path}:{n}")
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        pass
    return rows


def read_json(path, unreadable):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        unreadable.append(path)
        return None


def findings(text):
    """(severity, line) for each finding line of a review answer."""
    out = []
    for line in str(text or "").splitlines():
        line = line.strip()
        m = FINDING.match(line)
        if not m or (m.group(1) and m.group(2).strip().strip("*_").lower() in NO_FINDING):
            continue
        sev = (m.group(1) or m.group(3)).lower()
        finding = f"{sev}: {m.group(2).strip()}" if m.group(1) else line[line.lower().index("mismatch"):]
        out.append((sev, finding[:LINE_MAX]))
    return out


def is_name_list(value):
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def _step(row):
    return row.get("step") or row.get("stage")


def _status_rows(path, unreadable):
    rows = []
    for r in read_jsonl(path, unreadable):
        if r.get("event") not in STEP_EVENTS:
            continue
        well_formed = (isinstance(_step(r), str) and isinstance(r.get("round", 0) or 0, int)
                       and isinstance(r.get("time", ""), str))
        if not well_formed:
            unreadable.append(f"{path}: a {r.get('event')} line of the wrong shape")
            continue
        rows.append(r)
    return rows


def _timeline(rows, order):
    minutes, opened, back, stops, last_round = defaultdict(float), {}, [], [], 0
    for r in rows:
        step, at = _step(r), parse_time(r.get("time"))
        last_round = max(last_round, r.get("round") or 0)
        if r["event"] == "start" and at is not None:
            opened[step] = at
        elif r["event"] == "end":
            if step in opened and at is not None:
                minutes[step] += (at - opened.pop(step)) / 60
            to = r.get("to")
            if to in order and step in order and order.index(to) < order.index(step):
                back.append({"from": step, "to": to, "outcome": r.get("outcome"), "round": r.get("round")})
        elif r["event"] == "stop":
            stops.append({"step": step, "done": r.get("done"), "blocked": r.get("blocked")})
    return minutes, back, stops, last_round


def _gap_label(row):
    """What a gap after this end or stop line waited on."""
    step = _step(row)
    if row["event"] == "end":
        return f"end {step} ({row['outcome']})" if isinstance(row.get("outcome"), str) else f"end {step}"
    m = STOP_KIND.match(str(row.get("done") or "").strip())
    kind = m.group(1).lower() if m else ("blocked" if row.get("blocked") else "other")
    return f"stop {step} ({kind})"


def _idle(rows, work):
    """The task's idle time (module docstring), from its step lines in order."""
    timed = [(at, r) for at, r in ((parse_time(r.get("time")), r) for r in rows) if at is not None]
    by_event, running, before = defaultdict(float), set(), None
    for at, r in timed:
        if before is not None and not running and at > before[0]:
            by_event[before[1]] += (at - before[0]) / 60
        step = _step(r)
        if r["event"] in ("start", "progress"):
            if r["event"] == "start" and step in work:
                running -= work
            running.add(step)
        else:
            running.discard(step)
            before = (at, _gap_label(r))
        if running:
            before = None
    times = [at for at, _ in timed]
    return {"minutes": round(sum(by_event.values()), 1),
            "span_minutes": round((max(times) - min(times)) / 60, 1) if times else 0,
            "by_event": {k: round(v, 1) for k, v in sorted(by_event.items(), key=lambda kv: -kv[1])}}


def _reviews(folder, unreadable):
    reviews = defaultdict(lambda: {"runs": 0, "verdicts": Counter(), "findings": []})
    for meta_file in sorted(glob.glob(os.path.join(folder, "reviews", "*.meta.json"))):
        meta = read_json(meta_file, unreadable)
        if not isinstance(meta, dict) or not meta.get("role"):
            continue
        stats = reviews[meta["role"]]
        stats["runs"] += 1
        stats["verdicts"][meta.get("verdict") or ("failed run" if meta.get("ok") is not True else "no verdict")] += 1
        answer = read_json(meta_file[:-len(".meta.json")] + ".json", unreadable)
        text = answer.get("result") if isinstance(answer, dict) else ""
        stats["findings"] += findings(text if isinstance(text, str) else "")
    return reviews


def _gate_runs(folder, unreadable):
    path = os.path.join(folder, "gates.jsonl")
    gates = []
    for g in read_jsonl(path, unreadable):
        if not is_name_list(g.get("blocked", [])) or not is_name_list(g.get("warned", [])):
            unreadable.append(f"{path}: a run of the wrong shape")
            continue
        gates.append(g)
    return gates


def task_facts(folder, events, unreadable):
    task = os.path.basename(folder)
    loop = read_json(os.path.join(folder, "loop.json"), unreadable)
    if loop is not None and not isinstance(loop, dict):
        unreadable.append(os.path.join(folder, "loop.json"))
    loop = loop if isinstance(loop, dict) else {}
    loop_steps = [s for w in ("work", "check") for s in (loop.get(w) if isinstance(loop.get(w), list) else [])
                  if isinstance(s, dict) and isinstance(s.get("id"), str)]
    order = [s["id"] for s in loop_steps]
    rows = _status_rows(os.path.join(folder, "status.jsonl"), unreadable)
    minutes, back, stops, last_round = _timeline(rows, order)
    reviews = _reviews(folder, unreadable)
    gates = _gate_runs(folder, unreadable)
    times = [t for t in (parse_time(r.get("time")) for r in rows) if t is not None]
    work = {s["id"] for s in (loop.get("work") if isinstance(loop.get("work"), list) else [])
            if isinstance(s, dict) and isinstance(s.get("id"), str)}
    return {"task": task, "first": min(times) if times else None, "last": max(times) if times else None,
            "difficulty": loop.get("difficulty"), "trivial": loop.get("trivial"),
            "round": last_round, "order": order,
            "skills": {s["id"]: [x for x in s.get("skills", []) if isinstance(x, str)]
                       if isinstance(s.get("skills", []), list) else [] for s in loop_steps},
            "ran": sorted({_step(r) for r in rows if r["event"] == "start"}),
            "minutes": {k: round(v, 1) for k, v in minutes.items()}, "back": back, "stops": stops,
            "reviews": {k: {"runs": v["runs"], "verdicts": dict(v["verdicts"]),
                            "findings": Counter(s for s, _ in v["findings"]),
                            "lines": [line for _, line in v["findings"]]} for k, v in reviews.items()},
            "gate_runs": [{"before_ready": g.get("before_ready"), "pass": g.get("pass"),
                           "blocked": g.get("blocked", []), "warned": g.get("warned", [])} for g in gates],
            "events": dict(Counter(e.get("event") for e in events if e.get("task") == task)),
            "idle": _idle(rows, work)}


def facts(repo, tasks=None, since=None):
    """The retro's facts; `since` is seconds since the epoch, or None."""
    unreadable = []
    root = os.path.join(project_dir(repo), "tasks")
    log = read_jsonl(log_path(repo), unreadable)
    task_names = tasks or sorted(e for e in (os.listdir(root) if os.path.isdir(root) else [])
                                 if os.path.isdir(os.path.join(root, e)))
    per_task = []
    for task_name in task_names:
        folder = os.path.join(root, task_name)
        if not os.path.isdir(folder):
            unreadable.append(f"{folder} (no archived task folder)")
            continue
        t = task_facts(folder, log, unreadable)
        if since is not None and (t["last"] is None or t["last"] < since):
            continue
        per_task.append(t)

    steps = defaultdict(lambda: {"ran": 0, "minutes": [], "back_from": Counter(), "skills": set()})
    roles = defaultdict(lambda: {"verdicts": Counter(), "findings": Counter(), "lines": []})
    gate = defaultdict(lambda: {"blocked": 0, "warned": 0})
    events = Counter()
    idle = {"minutes": 0.0, "span_minutes": 0.0, "by_event": Counter()}
    for t in per_task:
        for key in ("minutes", "span_minutes"):
            idle[key] += t["idle"][key]
        idle["by_event"].update(t["idle"]["by_event"])
        for step in t["order"]:
            s = steps[step]
            s["skills"].update(t["skills"].get(step, []))
            if step in t["ran"]:
                s["ran"] += 1
            if step in t["minutes"]:
                s["minutes"].append(t["minutes"][step])
        for b in t["back"]:
            steps[b["to"]]["back_from"][f"from {b['from']} ({b['outcome']})"] += 1
        for role, r in t["reviews"].items():
            roles[role]["verdicts"].update(r["verdicts"])
            roles[role]["findings"].update(r["findings"])
            roles[role]["lines"] += [f"{t['task']}: {line}" for line in r["lines"]]
        for g in t["gate_runs"]:
            for name in g["blocked"]:
                gate[name]["blocked"] += 1
            for name in g["warned"]:
                gate[name]["warned"] += 1
        events.update(t["events"])
    last_setup = next((e for e in reversed(log) if e.get("event") == "setup" and isinstance(e.get("data"), dict)
                       and isinstance(e["data"].get("open"), list)), None)
    last_retro = next((e for e in reversed(log) if e.get("event") == "retro"), None)
    stamp = lambda seconds: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds)) if seconds is not None else None
    return {
        "project": repo,
        "tasks": [{**{k: v for k, v in t.items() if k not in ("order", "skills", "ran", "first", "last")},
                   "first": stamp(t["first"]), "last": stamp(t["last"])} for t in per_task],
        "steps": {k: {"ran": v["ran"], "minutes": round(sum(v["minutes"]), 1),
                      "median_minutes": round(statistics.median(v["minutes"]), 1) if v["minutes"] else None,
                      "back_to": sum(v["back_from"].values()), "back_from": dict(v["back_from"]),
                      "skills": sorted(v["skills"])} for k, v in steps.items()},
        "roles": {k: {"verdicts": dict(v["verdicts"]), "findings": dict(v["findings"]), "lines": v["lines"]}
                  for k, v in roles.items()},
        "gate": dict(gate),
        "idle": {"minutes": round(idle["minutes"], 1), "span_minutes": round(idle["span_minutes"], 1),
                 "by_event": {k: round(v, 1) for k, v in idle["by_event"].most_common()}},
        "events": dict(events),
        "open": last_setup["data"]["open"] if last_setup else [],
        "previous": {k: last_retro.get(k) for k in ("time", "text", "data")} if last_retro else None,
        "unreadable": unreadable,
    }


def main(argv):
    ap = argparse.ArgumentParser(prog="retro.py", description="facts for the foreman's retro")
    ap.add_argument("command", choices=["facts"])
    ap.add_argument("--project", required=True, metavar="OWNER/REPO")
    ap.add_argument("--task", action="append", default=[], help="a task to read (repeat it); default: every one")
    ap.add_argument("--since", metavar="TIME", help="only tasks whose first status line is at or after TIME")
    args = ap.parse_args(argv)
    if not REPO.match(args.project):
        print(f"retro.py: --project must look like owner/name, not {args.project!r}", file=sys.stderr)
        return 2
    if any(not t or "/" in t or t.startswith(".") for t in args.task):
        print("retro.py: --task names a task folder, such as 12", file=sys.stderr)
        return 2
    since = since_time(args.since) if args.since else None
    if args.since and since is None:
        print(f"retro.py: --since takes YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ, not {args.since!r}", file=sys.stderr)
        return 2
    print(json.dumps(facts(args.project, args.task or None, since), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
