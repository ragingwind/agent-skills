import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest import TestCase, mock

from helpers import SCRIPTS, TempHome, providers, run

import board
import bundle
import config


REPO = "o/r"
SESSION = "10101010-1010-1010-1010-101010101010"
PROJECT = "state/agent-foreman/projects/o-r"
TASK = ".local/state/agent-foreman/tasks/o-r/7"
STOP = {"event": "stop", "step": "build", "done": "REPORT: decision — Choose the migration"}


class Board(TestCase):
    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        self.local = Path(self.home.root, "local")
        self.remote = Path(self.home.root, "remote")
        self.local.mkdir()
        self.remote.mkdir()
        self.env = {"HOME": str(self.local), "CLAUDE_CONFIG_DIR": ""}

    def put(self, base, relative, data):
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return path

    def status(self, *rows):
        self.put(self.local, f"{TASK}/status.jsonl", "\n".join(map(json.dumps, rows)) + "\n")

    def transcript(self, reply, *earlier):
        entry = {"type": "assistant", "message": {"content": [{"type": "text", "text": reply}]}}
        self.put(self.local, f".claude/projects/task/{SESSION}.jsonl", "\n".join(map(json.dumps, (*earlier, entry))) + "\n")

    def review(self, base, name, *, verdict="pass", ended="2026-11-27T07:00:00Z"):
        self.put(base, f"{TASK}/reviews/{name}.meta.json", {"ok": True, "role": "qa", "agent": "qa-1",
                                                             "verdict": verdict, "head": "a1b2c3d4", "ended": ended})
        self.put(base, f"{TASK}/reviews/{name}.json", {"result": "All six scenarios passed"})

    def test_cli_display_reads_a_real_bundle_on_the_remote_host(self):
        self.home.write(f"{PROJECT}/project.json", {"machines": {"local": "/local", "build": "/remote"}})
        self.home.write("config/agent-foreman/providers.json", providers())
        self.home.write(f"{PROJECT}/ledger.md", f"## Tasks\n\n| Task | Machine | Pane | Profile | Session |\n"
                        f"| --- | --- | --- | --- | --- |\n| 7 | local | w1:p1 | opus | {SESSION} |\n")
        self.status(STOP)
        self.transcript("The migration is reversible")
        self.review(self.remote, "qa-1-1")
        bundle_path = self.remote / "bundle"
        for name, data in bundle.contents(config.load(), {}).items():
            path = bundle_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        fake = Path(self.home.root, "bin")
        self.put(fake, "herdr", "#!/bin/sh\nif [ \"$1\" = machine ]; then\n"
                 "  printf 'machine-id\\tbuild\\tbuild-host\\tdefault\\tenabled\\n'\nelse\n"
                 "  printf '{\"result\":{\"agents\":[]}}\\n'\nfi\n").chmod(0o755)
        self.put(fake, "ssh", f"#!{sys.executable}\nimport os, sys\n"
                 "assert sys.argv[3] == 'build-host'\n"
                 "os.environ.update(HOME=os.environ['REMOTE_HOME'], SHELL=os.environ['FAKE_LOGIN'])\n"
                 "os.chdir(os.environ['REMOTE_HOME'])\n"
                 "os.execv('/bin/sh', ['sh', '-c', sys.argv[4]])\n").chmod(0o755)
        login = self.put(fake, "login", "#!/bin/sh\nexec /bin/sh -c \"$2\"\n")
        login.chmod(0o755)
        env = self.env | {"PATH": f"{fake}{os.pathsep}{os.environ['PATH']}", "REMOTE_HOME": str(self.remote),
                          "FAKE_LOGIN": str(login)}
        result = run("board.py", "watch", "--project", REPO, "--once", "--remote-bundle", f"build={bundle_path}", env=env)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertEqual(result.stdout.splitlines(), [
            "Foreman o/r",
            "#7  local  lead  decision  REPORT: decision — Choose the migration | The migration is reversible",
            "#7  build  qa  pass  qa-1 | All six scenarios passed | at a1b2c3d4",
        ])
        missing = run("board.py", "watch", "--project", REPO, "--once", env=env)
        self.assertEqual(missing.returncode, 1, missing.stderr)
        self.assertIn("#7  local  lead  decision", missing.stdout)
        self.assertIn("build: stale (supply --remote-bundle", missing.stdout)

    def test_cli_empty_and_invalid_project(self):
        empty = run("board.py", "watch", "--project", REPO, "--once", env=self.env)
        self.assertEqual((empty.returncode, empty.stdout), (0, "Foreman o/r\nNo reports\n"), empty.stderr)
        invalid = run("board.py", "watch", "--project", "bad", "--once", env=self.env)
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("OWNER/REPO", invalid.stderr)

    def test_records_keeps_the_lead_decision_after_a_qa_step(self):
        leads = {"7": {"pane": "w1:p1", "kind": "claude", "session": SESSION}}
        self.status(STOP | {"done": STOP["done"] + "\x1b[31m\x07"}, 7,
                    {"event": "end", "step": "qa", "done": "QA reported pass", "to": "stop"})
        self.put(self.local, f"{TASK}/loop.json", {"work": [], "check": [{"id": "qa"}]})
        self.transcript("A plain reply from the Lead", None, {"type": "user", "message": None},
                        {"type": "assistant", "message": {"content": 3}},
                        {"type": "assistant", "message": {"content": [{"type": "text", "text": None}]}})
        self.review(self.local, "qa-1-1", verdict="changes", ended="2026-11-26T07:00:00Z")
        self.review(self.local, "qa-1-2")
        self.put(self.local, f"{TASK}/reviews/bad.meta.json", "incomplete")
        self.put(self.local, f"{TASK}/reviews/invalid.meta.json", {"role": "qa", "ok": "yes", "agent": "qa-1",
                                                                  "ended": "2026-11-28T07:00:00Z"})
        with mock.patch.dict(os.environ, self.env):
            rows = board.read_records(REPO, leads, set(), 30)
            working = board.read_records(REPO, leads, {"w1:p1"}, 30)
        self.assertEqual([(row["role"], row["state"]) for row in rows], [("lead", "decision"), ("qa", "pass")])
        self.assertNotIn("reply", working[0])
        out = board.render(REPO, {"local": rows}, {})
        self.assertIn("A plain reply from the Lead", out)
        self.assertNotIn("QA reported pass", out)
        self.assertNotIn("\x1b", out)
        self.assertNotIn("\x07", out)

    def test_watch_arms_settle_after_working(self):
        events = board.Queue()
        stop = board.Event()
        completed = subprocess.CompletedProcess([], 0)
        with mock.patch.object(board.subprocess, "run", side_effect=[completed, completed]) as command:
            with mock.patch.object(events, "put", side_effect=lambda item: stop.set()) as emit:
                board.wait_for_settle("build", "w1:p1", events, stop)
            self.assertEqual(command.call_count, 2)
            emit.assert_called_once_with(("build", "w1:p1"))
        first, second = [call.args[0] for call in command.call_args_list]
        self.assertEqual(first, ["herdr", "--machine", "build", "agent", "wait", "w1:p1", "--timeout", "5000",
                                 "--until", "working"])
        self.assertEqual(second, first[:-2])

    def test_watch_reports_a_settle_between_two_waits(self):
        # The agent works past one settled wait's timeout and settles before the next wait starts.
        states = ["working", "working", "done", "done"]
        waits = []

        def herdr(argv, **kwargs):
            if not states:
                stop.set()
                return subprocess.CompletedProcess(argv, 1)
            state = states.pop(0)
            until_working = argv[-2:] == ["--until", "working"]
            waits.append("working" if until_working else "settled")
            return subprocess.CompletedProcess(argv, 0 if until_working == (state == "working") else 1)

        events = board.Queue()
        stop = board.Event()
        with (mock.patch.object(board.subprocess, "run", side_effect=herdr),
              mock.patch.object(stop, "wait", return_value=False)):
            board.wait_for_settle("build", "w1:p1", events, stop)
        self.assertEqual(waits, ["working", "settled", "settled", "working"])
        self.assertEqual(events.get_nowait(), ("build", "w1:p1"))
        self.assertTrue(events.empty())

    def test_watch_event_poll_and_recovery(self):
        cfg = {"machines": {"local": "/local", "build": "/remote"}, "profiles": {}, "ops": {"stall_minutes": 30}}
        leads = {"local": {"7": {"pane": "w1:p1"}}, "build": {"7": {"pane": "w1:p2"}}}
        bundles = {"build": Path("/bundle")}
        requests = []
        frame = 0
        clock = 0

        def receive(timeout):
            nonlocal frame, clock
            frame += 1
            if frame == 1:
                self.assertEqual(timeout, 30)
                return ("local", "w1:p1")
            if frame in (2, 3, 4):
                clock += 30
                raise board.Empty
            raise KeyboardInterrupt

        def records(repo, machine, *args):
            requests.append((frame, machine))
            if machine == "local":
                row = {"task": "7", "role": "lead", "state": "decision", "summary": "Choose the migration",
                       "session": SESSION}
                if frame < 2:
                    row["reply"] = "Reply after chat" if frame else "Old reply"
                return [row]
            if frame == 3:
                raise OSError("offline")
            return ([{"task": "7", "role": "qa", "state": "pass", "summary": "Scenario passed"}]
                    if frame == 2 else [])

        events = mock.Mock()
        events.get.side_effect = receive
        events.empty.return_value = True
        out = io.StringIO()
        with (mock.patch.object(board, "Queue", return_value=events),
              mock.patch.object(board, "Thread") as workers,
              mock.patch.object(board, "ledger_leads", return_value=leads),
              mock.patch.object(board, "saved_machines", return_value={"build": {"enabled": True}}),
              mock.patch.object(board, "machine_records", side_effect=records),
              mock.patch.object(board.time, "monotonic", side_effect=lambda: clock),
              contextlib.redirect_stdout(out)):
            self.assertEqual(board.watch(REPO, cfg, bundles, 30), 0)
        self.assertEqual(workers.call_count, 2)
        self.assertIn((1, "local"), requests)
        self.assertNotIn((1, "build"), requests)
        frames = out.getvalue().split("Foreman o/r\n")[1:]
        self.assertEqual(len(frames), 5)
        self.assertIn("decision  Choose the migration | Reply after chat", frames[1])
        self.assertNotIn("Old reply", frames[1])
        self.assertIn("qa  pass  Scenario passed", frames[2])
        self.assertIn("build: stale (offline)", frames[3])
        self.assertIn("qa  pass  Scenario passed", frames[3])
        self.assertNotIn("stale", frames[4])
        self.assertNotIn("Scenario passed", frames[4])
