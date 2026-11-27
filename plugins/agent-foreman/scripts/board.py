#!/usr/bin/env python3
"""Show existing Foreman records as a plain list in one Herdr pane."""

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import subprocess
import sys
from threading import Event, Thread
import time
import unicodedata

import adapters
import config
from gate import latest_answers
import status
from transcript import SESSION


REPORT = re.compile(r"^(?:REPORT:\s*)?(decision|blocked|waiting|ready)\b", re.IGNORECASE)
PANE = re.compile(r"w[0-9a-z]+:p[0-9a-z]+", re.IGNORECASE)
ANSI_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def ledger_leads(repo, profiles):
    """Read the named columns of the current Tasks table."""
    try:
        lines = Path(config.ledger_path(repo)).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    columns = ()
    leads = {}
    for line in lines:
        if line.startswith("## "):
            columns = ()
        if not line.startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in re.split(r"(?<!\\)\|", line.strip("|"))]
        if set(("Task", "Machine", "Pane", "Profile", "Session")) <= set(cells):
            columns = cells
            continue
        if not columns or len(cells) != len(columns):
            continue
        row = dict(zip(columns, cells))
        task, machine, session = row["Task"].lstrip("#"), row["Machine"], row["Session"]
        if not config.NAME.fullmatch(task) or not PANE.fullmatch(row["Pane"]):
            continue
        profile = profiles.get(row["Profile"])
        kind = adapters.kind_of(profile) if profile is not None else None
        leads.setdefault(machine, {})[task] = {
            "pane": row["Pane"], "session": session if SESSION.fullmatch(session) else "", "kind": kind,
        }
    return leads


def short(value):
    """Keep one line of a record and discard terminal control characters."""
    if not isinstance(value, str):
        return ""
    line = next((line.strip() for line in ANSI_CSI.sub("", value).splitlines() if line.strip()), "")
    clean = "".join(c for c in line if not unicodedata.category(c).startswith("C"))
    return clean[:177] + "..." if len(clean) > 180 else clean


def notes(folder, lead, stall):
    try:
        with (folder / "status.jsonl").open(encoding="utf-8", errors="replace") as stream:
            lines = deque(stream, maxlen=status.TAIL)
    except FileNotFoundError:
        return {}
    task_loop = status.load_loop(str(folder / "status.jsonl")) if lead else None
    checks = task_loop.get("check", []) if isinstance(task_loop, dict) else []
    if isinstance(checks, list):
        verification = {str(step.get("id", "")) for step in checks if isinstance(step, dict)} - {""}
        if verification:
            filtered = []
            for line in lines:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and str(row.get("step")) not in verification:
                    filtered.append(line)
            lines = filtered
    return status.summarize(lines, stall)


def read_records(repo, leads, working, stall):
    """Read the latest records on the machine that owns the task folders."""
    rows = []
    root = Path(status.project_root(repo)).expanduser()
    if not root.exists():
        return rows
    for folder in sorted(root.iterdir()):
        if not config.NAME.fullmatch(folder.name) or folder.is_symlink() or not folder.is_dir():
            continue
        task = folder.name
        lead = leads.get(task)
        current = notes(folder, lead, stall)
        if lead or current.get("stage_event"):
            summary = short(current.get("done")) or short(current.get("blocked"))
            marker = REPORT.match(summary) if current.get("stopped") else None
            state = marker[1].lower() if marker else (
                "blocked" if current.get("stopped") and current.get("blocked") else
                "ready" if current.get("stopped") and current.get("step") == "finalize" else
                "stopped" if current.get("stopped") else "stalled" if current.get("stalled") else
                short(current.get("step")) or short(current.get("stage")) or "pending"
            )
            row = {"task": task, "role": "lead" if lead else "task", "state": state, "summary": summary}
            if lead and lead.get("session") and lead.get("kind") in adapters.KINDS:
                row["session"] = lead["session"]
                if lead["pane"] not in working:
                    try:
                        answers, _ = adapters.get(lead["kind"]).last_answers(lead["session"], 1)
                    except (adapters.NoTranscript, OSError, ValueError):
                        answers = []
                    if answers:
                        row["reply"] = short(answers[-1])
            rows.append(row)
        for _, meta, answer in latest_answers(folder):
            rows.append({"task": task, "role": meta["role"], "agent": short(meta.get("agent")),
                         "state": (short(meta.get("verdict")) or "completed") if meta["ok"] else "failed",
                         "summary": short(answer), "head": short(meta.get("head"))[:12]})
    return rows


def herdr_command(machine, *args):
    return ["herdr", *([] if machine == config.LOCAL else ["--machine", machine]), *args]


def working_panes(machine, leads):
    if not leads:
        return set()
    try:
        run = subprocess.run(herdr_command(machine, "agent", "list"), capture_output=True, text=True,
                             timeout=5, check=True)
        agents = json.loads(run.stdout)["result"]["agents"]
        return {agent["pane_id"] for agent in agents if agent.get("agent_status") == "working"}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        return {lead["pane"] for lead in leads.values()}


def machine_records(repo, machine, leads, stall, saved, bundles):
    if machine != config.LOCAL:
        if not saved.get(machine, {}).get("enabled"):
            raise ValueError("Herdr machine profile is unavailable")
        if machine not in bundles:
            raise ValueError("supply --remote-bundle using bundle.py push")
    request = {"leads": leads, "working": sorted(working_panes(machine, leads)), "stall": stall}
    if machine == config.LOCAL:
        return read_records(repo, **request)
    from remote import remote_argv

    script = bundles[machine] / "scripts" / "board.py"
    argv = remote_argv(saved[machine]["target"], ["python3", str(script), "read", "--project", repo])
    run = subprocess.run(argv, input=json.dumps(request), capture_output=True, text=True, timeout=15)
    if run.returncode:
        raise ValueError("SSH or remote bundle read failed")
    lines = run.stdout.splitlines()
    return json.loads(lines[-1] if lines else "null")


def render(repo, views, errors):
    priority = {"decision": 0, "blocked": 1, "failed": 2}
    lines = [f"Foreman {repo}"]
    rows = [(machine, row) for machine, view in views.items() for row in view]
    for machine, row in sorted(rows, key=lambda item: (priority.get(item[1]["state"], 3),
                                                       item[1]["task"], item[0], item[1]["role"],
                                                       item[1].get("agent", ""))):
        detail = list(dict.fromkeys(filter(None, (short(row["summary"]), short(row.get("reply"))))))
        if row.get("head"):
            detail.append(f"at {row['head']}")
        if row.get("agent") and row["agent"] != row["role"]:
            detail.insert(0, short(row["agent"]))
        columns = (f"#{row['task']}", machine, row["role"], row["state"])
        lines.append("  ".join([*(short(column) for column in columns), " | ".join(detail)]).rstrip())
    lines.extend(f"{short(machine)}: stale ({short(error)})" for machine, error in sorted(errors.items()))
    if not rows and not errors:
        lines.append("No reports")
    return "\n".join(lines)


def wait_for_settle(machine, pane, events, stop):
    """Report each settle of the pane's agent after Herdr observes it working.

    A settled wait that times out stays armed: the agent may settle before the next wait starts.
    """
    working = False
    while not stop.is_set():
        until = [] if working else ["--until", "working"]
        try:
            run = subprocess.run(herdr_command(machine, "agent", "wait", pane, "--timeout", "5000", *until),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=7)
        except (OSError, subprocess.SubprocessError):
            stop.wait(1)
            continue
        if run.returncode:
            stop.wait(1)
        elif working:
            events.put((machine, pane))
            working = False
        else:
            working = True


def refresh(repo, machines, leads, stall, saved, bundles, views, errors):
    with ThreadPoolExecutor(max_workers=max(1, min(len(machines), 8))) as pool:
        pending = {machine: pool.submit(machine_records, repo, machine, leads.get(machine, {}), stall, saved, bundles)
                   for machine in machines}
        for machine, future in pending.items():
            try:
                rows = future.result()
                keys = ("task", "role", "state", "summary")
                if not isinstance(rows, list) or any(
                    not isinstance(row, dict) or any(not isinstance(row.get(key), str) for key in keys)
                    for row in rows
                ):
                    raise ValueError("invalid reader response")
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                errors[machine] = str(exc)
                continue
            old = {(row["task"], row.get("session")): row.get("reply") for row in views.get(machine, [])}
            for row in rows:
                if row.get("session") and "reply" not in row:
                    row["reply"] = old.get((row["task"], row["session"]))
            views[machine] = rows
            errors.pop(machine, None)


def saved_machines(machines):
    try:
        return config.herdr_machines() if any(machine != config.LOCAL for machine in machines) else {}
    except (SystemExit, OSError, subprocess.SubprocessError):
        return {}


def watch(repo, cfg, bundles, interval, once=False):
    machines = list(cfg.get("machines", {})) or [config.LOCAL]
    views, errors, workers = {}, {}, {}
    events = Queue()
    deadline, previous = 0, ""
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                saved = saved_machines(machines)
                leads = ledger_leads(repo, cfg["profiles"])
                wanted = {(machine, lead["pane"]) for machine in machines for lead in leads.get(machine, {}).values()
                          if machine == config.LOCAL or (machine in bundles and saved.get(machine, {}).get("enabled"))}
                for key in workers.keys() - wanted:
                    workers.pop(key).set()
                if not once:
                    for machine, pane in wanted - workers.keys():
                        stop = workers[machine, pane] = Event()
                        Thread(target=wait_for_settle, args=(machine, pane, events, stop), daemon=True).start()
                selected, deadline = set(machines), time.monotonic() + interval
            else:
                try:
                    item = events.get(timeout=remaining)
                except Empty:
                    continue
                selected = set()
                if item in wanted:
                    selected.add(item[0])
                while not events.empty():
                    item = events.get_nowait()
                    if item in wanted:
                        selected.add(item[0])
            refresh(repo, selected, leads, cfg["ops"]["stall_minutes"], saved, bundles, views, errors)
            output = render(repo, views, errors)
            if output != previous:
                if previous and sys.stdout.isatty():
                    print("\x1b[2J\x1b[H", end="")
                print(output, flush=True)
                previous = output
            if once:
                return int(bool(errors))
    except KeyboardInterrupt:
        return 0
    finally:
        for stop in workers.values():
            stop.set()


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("watch", "read"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--remote-bundle", action="append", default=[], metavar="MACHINE=/PATH")
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if not config.REPO.fullmatch(args.project) or args.interval < 1:
        parser.error("give --project OWNER/REPO and an interval of at least one second")
    bundles = {}
    for item in args.remote_bundle:
        machine, sep, path = item.partition("=")
        if not machine or not sep or not Path(path).is_absolute() or machine in bundles:
            parser.error("give one --remote-bundle MACHINE=/PATH per remote machine")
        bundles[machine] = Path(path)
    if args.command == "read":
        try:
            request = json.load(sys.stdin)
            print(json.dumps(read_records(args.project, **request), ensure_ascii=False))
        except (OSError, ValueError, TypeError) as exc:
            parser.error(f"could not read task records ({exc})")
        return 0
    return watch(args.project, config.load(args.project), bundles, args.interval, args.once)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
