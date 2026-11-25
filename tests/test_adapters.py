import json
import os
import subprocess
import sys
import unittest

from helpers import SCRIPTS, TempHome

import adapters
import config
from adapters import claude, codex


class Interface(unittest.TestCase):
    def test_every_adapter_defines_the_interface(self):
        for kind, module in adapters.ADAPTERS.items():
            for name in adapters.REQUIRED:
                self.assertTrue(hasattr(module, name), f"{kind} lacks {name}")
            self.assertEqual(module.KIND, kind)

    def test_every_adapter_has_its_screen_page(self):
        for kind in adapters.KINDS:
            self.assertTrue(os.path.isfile(os.path.join(config.SKILL_DIR, "adapters", f"{kind}.md")), kind)

    def test_unknown_kind(self):
        with self.assertRaises(ValueError):
            adapters.get("nope")
        self.assertEqual(adapters.kind_of({}), "claude")
        self.assertEqual(adapters.kind_of({"agent": "x"}), "x")


class Claude(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.cfg = config.load()

    def tearDown(self):
        self.home.close()

    def test_command(self):
        argv, env, clear = claude.command(self.cfg, "sonnet", name="issue-1", session_id="abc", bundle="/b",
                                          environ={})
        self.assertEqual(argv, ["claude", "--name", "issue-1", "--session-id", "abc",
                                "--model", "sonnet", "--dangerously-skip-permissions", "--plugin-dir", "/b",
                                "--disallowedTools", "Bash(gh pr merge:*)"])
        self.assertEqual(env, {})
        self.assertIn("ANTHROPIC_BASE_URL", clear)
        argv, _, _ = claude.command(self.cfg, "opus", print_mode=True, environ={}, no_edit=True)
        self.assertEqual(argv, ["claude", "-p", "--output-format", "json", "--model", "opus",
                                "--dangerously-skip-permissions", "--disallowedTools",
                                "Edit,Write,NotebookEdit,Bash(gh pr merge:*)"])

    def test_plugin_dirs_load_whole_after_the_bundle(self):
        argv, _, _ = claude.command(self.cfg, "sonnet", bundle="/b", environ={}, plugin_dirs=["/p1", "/p2"])
        self.assertEqual(argv[argv.index("--plugin-dir"):], ["--plugin-dir", "/b", "--plugin-dir", "/p1",
                                                            "--plugin-dir", "/p2", "--disallowedTools",
                                                            "Bash(gh pr merge:*)"])

    def test_token_missing(self):
        cfg = config.merge(self.cfg, {
            "gateways": {"gw": {"kind": "anthropic-compatible", "base_url": "https://x", "token_env": "T",
                                "auth": "bearer", "models": {"m": {"id": "m-1", "context": 10}}}},
            "profiles": {"p": {"gateway": "gw", "model": "m", "roles": {"opus": "m", "sonnet": "m", "haiku": "m"}}}})
        with self.assertRaises(adapters.TokenMissing) as e:
            claude.command(cfg, "p", environ={})
        self.assertEqual(e.exception.variable, "T")
        argv, env, _ = claude.command(cfg, "p", environ={"T": "v"})
        self.assertEqual(argv[:3], ["claude", "--model", "m-1"])
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "v")

    def test_skill_name_and_layout(self):
        self.assertEqual(claude.skill_name("local-skills:deep-clean-code"), "foreman-kit:deep-clean-code")
        files = claude.bundle_layout({"tidy": {"SKILL.md": b"x", "scripts/run.py": b"y"}})
        self.assertEqual(sorted(files), [".claude-plugin/plugin.json", "hooks/hooks.json", "skills/tidy/SKILL.md",
                                         "skills/tidy/scripts/run.py"])
        self.assertEqual(json.loads(files[".claude-plugin/plugin.json"])["name"], "foreman-kit")

    def test_last_answers(self):
        sid = "0123abcd-0000"
        lines = [{"type": "user", "message": {"content": "q1"}},
                 {"type": "assistant", "message": {"content": [{"type": "text", "text": "a1"}]}},
                 {"type": "user", "message": {"content": "q2"}},
                 {"type": "assistant", "message": {"content": [{"type": "text", "text": "a2"}]}}]
        self.home.write(f"projects/x/{sid}.jsonl", "\n".join(json.dumps(x) for x in lines))
        root = os.path.join(self.home.root, "projects")
        self.assertEqual(claude.last_answers(sid, 1, root=root), (["a2"], 2))
        self.assertEqual(claude.last_answers(sid, 5, root=root), (["a1", "a2"], 2))
        with self.assertRaises(adapters.NoTranscript):
            claude.last_answers("ffff0000-1111", 1, root=root)


class Codex(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.cfg = config.merge(config.load(), {
            "gateways": {"openai": {"kind": "openai"}},
            "profiles": {"gpt": {"gateway": "openai", "model": "gpt-5.5", "agent": "codex"}}})

    def tearDown(self):
        self.home.close()

    def test_command(self):
        argv, env, clear = codex.command(self.cfg, "gpt", name="lead-1", session_id="abc-12345", bundle="/b",
                                         plugin_dirs=["/p1"])
        self.assertEqual(argv[:4], ["codex", "--model", "gpt-5.5", "--dangerously-bypass-approvals-and-sandbox"])
        self.assertEqual(argv[-1], "--dangerously-bypass-hook-trust")
        options = [argv[i + 1] for i, a in enumerate(argv) if a == "-c"]
        self.assertEqual([o.split("=", 1)[0] for o in options],
                         ["allow_login_shell", "hooks.SessionStart", "hooks.PreToolUse", "hooks.PostToolUse",
                          "hooks.Stop"])
        self.assertEqual(options[0], "allow_login_shell=false")  # the PATH launch.py gave stays in front
        self.assertIn('command="python3 /b/scripts/hook.py session"', options[1])
        self.assertIn('matcher=".*"', options[2])
        self.assertIn("/b/scripts/heartbeat.py post", options[3])
        self.assertNotIn("/p1", " ".join(argv))  # a Claude Code plugin is not Codex's
        self.assertEqual((env, clear), ({"AF_SESSION_ALIAS": "abc-12345"}, set()))
        argv, env, clear = codex.command(self.cfg, "gpt", print_mode=True, no_edit=True)
        self.assertEqual(argv[:5], ["codex", "exec", "--json", "--model", "gpt-5.5"])
        self.assertIn("hook.py guard --no-edit", " ".join(argv))
        self.assertIn(os.path.join(SCRIPTS, "hook.py"), " ".join(argv))  # run from the skill, its own scripts
        self.assertEqual((env, clear), ({}, {"AF_SESSION_ALIAS"}))
        cfg = config.merge(self.cfg, {"launch": {"permission": "default"}})
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", codex.command(cfg, "gpt")[0])

    def test_hook_options_are_toml(self):
        import tomllib
        argv, _, _ = codex.command(self.cfg, "gpt", bundle="/b d/it's", no_edit=True)
        for option in [argv[i + 1] for i, a in enumerate(argv) if a == "-c" and argv[i + 1].startswith("hooks.")]:
            key, value = option.split("=", 1)
            hook = tomllib.loads(f"v = {value}")["v"][0]["hooks"][0]
            self.assertEqual(hook["type"], "command")
            self.assertIn("'/b d/it'\"'\"'s/scripts/", hook["command"])

    def test_parse_print(self):
        lines = [{"type": "thread.started", "thread_id": "t-9"},
                 {"type": "error", "message": "Reconnecting... 1/5"},
                 {"type": "item.completed", "item": {"type": "agent_message", "text": "first"}},
                 {"type": "item.completed", "item": {"type": "command_execution", "status": "completed"}},
                 {"type": "item.completed", "item": {"type": "agent_message", "text": "Verdict: approved"}},
                 {"type": "turn.completed", "usage": {"input_tokens": 1}}]
        text = "\n".join(json.dumps(x) for x in lines) + "\nnot json\n"
        self.assertEqual(codex.parse_print(text), {"ok": True, "result": "Verdict: approved", "session_id": "t-9",
                                                   "cost": None, "denials": []})
        failed = "\n".join(json.dumps(x) for x in lines[:3] + [{"type": "turn.failed",
                                                                "error": {"message": "usage limit"}}])
        self.assertEqual(codex.parse_print(failed)["ok"], False)
        self.assertEqual(codex.parse_print(failed)["result"], "usage limit")
        self.assertEqual(codex.parse_print("boom")["result"], "boom")
        saved = json.loads(codex.answer_file(text))
        self.assertEqual(saved, {"type": "result", "is_error": False, "result": "Verdict: approved", "session_id": "t-9",
                                 "total_cost_usd": None, "permission_denials": [], "usage": {"input_tokens": 1}})
        self.assertEqual(json.loads(codex.answer_file(failed))["is_error"], True)
        self.assertEqual(claude.answer_file('{"result": "x"}'), '{"result": "x"}')

    def test_skill_name_and_links(self):
        self.assertEqual(codex.skill_name("local-skills:tidy"), "foreman-kit:tidy")
        self.assertEqual(codex.bundle_layout({"commit": {"SKILL.md": b"x"}}), {})  # it reads Claude Code's plugin
        bundle = os.path.join(self.home.root, "bundle")
        for rel in ("skills/commit/SKILL.md", "skills/notes/README.md", "plugins/flow/skills/plan/SKILL.md",
                    "plugins/solo/SKILL.md", "work/.claude/skills/tidy/SKILL.md"):
            self.home.write(f"bundle/{rel}" if not rel.startswith("work/") else rel, "---\nname: x\n---\n")
        self.home.write("plugins-none/x", "")
        work = os.path.join(self.home.root, "work")
        self.assertEqual(codex._skill_dirs(bundle, work), [
            ("foreman-kit--commit", os.path.join(bundle, "skills", "commit")),
            ("flow--plan", os.path.join(bundle, "plugins", "flow", "skills", "plan")),
            ("solo--solo", os.path.join(bundle, "plugins", "solo")),
            ("tidy", os.path.join("..", "..", ".claude", "skills", "tidy"))])
        self.assertEqual(codex._skill_dirs(None, os.path.join(self.home.root, "nowhere")), [])

    def session_file(self, root, sid, answers):
        lines = [{"type": "session_meta", "payload": {"id": sid, "cwd": "/c"}}]
        for a in answers:
            lines += [{"type": "event_msg", "payload": {"type": "task_started"}},
                      {"type": "event_msg", "payload": {"type": "task_complete", "last_agent_message": a}}]
        path = os.path.join(root, "2026", "11", "24", f"rollout-2026-11-24T10-00-00-{sid}.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("\n".join(json.dumps(x) for x in lines) + "\n")
        return path

    def test_last_answers_by_codex_id_or_the_foremans(self):
        root = os.path.join(self.home.root, "codex", "sessions")
        path = self.session_file(root, "019a-real-0001", ["a1", None, "a2"])
        self.assertEqual(codex.last_answers("019a-real-0001", 1, root=root), (["a2"], 2))
        self.assertEqual(codex.last_answers("019a-real-0001", 5, root=root), (["a1", "a2"], 2))
        with self.assertRaises(adapters.NoTranscript):
            codex.last_answers("foreman-chosen-1", 1, root=root)
        codex.record_session("foreman-chosen-1", {"session_id": "019a-real-0001", "transcript_path": None})
        self.assertEqual(codex.last_answers("foreman-chosen-1", 1, root=root), (["a2"], 2))
        moved = path + ".moved"
        os.rename(path, moved)
        codex.record_session("foreman-chosen-1", {"session_id": "019a-real-0001", "transcript_path": moved})
        self.assertEqual(codex.last_answers("foreman-chosen-1", 1, root=root), (["a2"], 2))
        codex.record_session("../escape", {"session_id": "x"})
        self.assertFalse(os.path.exists(os.path.join(self.home.root, "state", "agent-foreman", "escape.json")))


class Hook(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def hook(self, *args, data=None, env=None):
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, "hook.py"), *args],
                              input=data if isinstance(data, str) else json.dumps(data), capture_output=True,
                              text=True, env={**os.environ, **(env or {})})

    def test_guard(self):
        merge = {"tool_name": "Bash", "tool_input": {"command": "gh  pr merge 12 --squash"}}
        edit = {"tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch"}}
        test = {"tool_name": "Bash", "tool_input": {"command": "make test"}}
        r = self.hook("guard", data=merge)
        self.assertEqual(r.returncode, 2)
        self.assertIn("never runs gh pr merge", r.stderr)
        self.assertEqual(self.hook("guard", data=edit).returncode, 0)
        r = self.hook("guard", "--no-edit", data=edit)
        self.assertEqual((r.returncode, r.stderr.strip()), (2, "this agent judges the change and edits no file"))
        self.assertEqual(self.hook("guard", "--no-edit", data=test).returncode, 0)
        self.assertEqual(self.hook("guard", data="not json").returncode, 0)
        self.assertEqual(self.hook("guard", data=[1]).returncode, 0)

    def test_session(self):
        data = {"session_id": "019a-real-0002", "transcript_path": "/t.jsonl", "cwd": "/c", "model": "m"}
        r = self.hook("session", data=data, env={"AF_SESSION_ALIAS": "abc-12345"})
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        with open(codex.alias_path("abc-12345")) as f:
            self.assertEqual(json.load(f), {"session_id": "019a-real-0002", "transcript_path": "/t.jsonl", "cwd": "/c"})
        os.remove(codex.alias_path("abc-12345"))
        self.assertEqual(self.hook("session", data=data, env={"AF_SESSION_ALIAS": ""}).returncode, 0)
        self.assertFalse(os.path.exists(codex.alias_path("abc-12345")))


if __name__ == "__main__":
    unittest.main()
