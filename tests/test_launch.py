import json
import os
import shutil
import stat
import subprocess
import unittest

from helpers import SCRIPTS, TempHome, providers, run

# A token-factory provider whose one model is named p.
GATEWAY = providers({"id": "gw", "base_url": "https://gw.example/anthropic", "auth": "bearer",
                     "token_env": "HF_TEST_TOKEN", "models": [{"id": "model-1", "name": "p", "context": 100000}]})


class Launch(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_skill_mode_dry_run(self):
        r = run("launch.py", "sonnet", "--name", "issue-1", "--session-id", "abc-123", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("command: claude --name issue-1 --session-id abc-123 --model sonnet "
                      "--dangerously-skip-permissions", r.stdout)
        self.assertNotIn("--plugin-dir", r.stdout)

    def test_a_worktree_setting_is_refused(self):
        self.home.write("config/agent-foreman/config.json", {"launch": {"worktree": True}})
        r = run("launch.py", "sonnet", "--name", "issue-1", "--dry-run")
        self.assertEqual(r.returncode, 3)
        self.assertIn("launch: unknown key 'worktree'", r.stderr)

    def test_bundle_mode_adds_plugin_dir_and_uses_bundle_settings(self):
        root = os.path.join(self.home.root, "bundle")
        shutil.copytree(SCRIPTS, os.path.join(root, "scripts"))
        self.home.write("bundle/bundle.json", {"agent": "claude"})
        self.home.write("bundle/config.json", {"gateways": {"anthropic": {"kind": "anthropic"}},
                                               "profiles": {"opus": {"gateway": "anthropic", "model": "opus"}},
                                               "launch": {"permission": "default"}})
        r = run("launch.py", "opus", "--dry-run", cwd=os.path.join(root, "scripts"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"command: claude --model opus --plugin-dir {root}", r.stdout)

    def test_bundle_loads_its_plugin_dirs_whole(self):
        root = os.path.join(self.home.root, "bundle")
        shutil.copytree(SCRIPTS, os.path.join(root, "scripts"))
        self.home.write("bundle/plugins/flow/.claude-plugin/plugin.json", {"name": "flow"})
        self.home.write("bundle/bundle.json", {"agent": "claude"})
        settings = {"gateways": {"anthropic": {"kind": "anthropic"}},
                    "profiles": {"opus": {"gateway": "anthropic", "model": "opus"}},
                    "launch": {"permission": "default"}, "plugins": ["flow"]}
        self.home.write("bundle/config.json", settings)
        r = run("launch.py", "opus", "--dry-run", cwd=os.path.join(root, "scripts"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"--plugin-dir {root} --plugin-dir {root}/plugins/flow --disallowedTools", r.stdout)
        self.home.write("bundle/config.json", {**settings, "plugins": ["flow", "gone"]})
        r = run("launch.py", "opus", "--dry-run", cwd=os.path.join(root, "scripts"))
        self.assertEqual(r.returncode, 3)
        self.assertIn("the bundle lacks the plugin", r.stderr)

    def test_profile_for_another_agent_than_the_bundle_is_setup(self):
        root = os.path.join(self.home.root, "bundle")
        shutil.copytree(SCRIPTS, os.path.join(root, "scripts"))
        self.home.write("bundle/config.json", {"gateways": {"anthropic": {"kind": "anthropic"}},
                                               "profiles": {"opus": {"gateway": "anthropic", "model": "opus"}},
                                               "launch": {"permission": "default"}})
        for marker in ({"agents": ["elsewhere"]}, {"agent": "elsewhere"}):  # a bundle from before codex: one kind
            self.home.write("bundle/bundle.json", marker)
            r = run("launch.py", "opus", "--dry-run", cwd=os.path.join(root, "scripts"))
            self.assertEqual(r.returncode, 3)
            self.assertIn("this bundle serves elsewhere", r.stderr)

    def test_unknown_agent_kind_is_setup(self):
        self.home.write("config/agent-foreman/providers.json", providers(sonnet={"agent": "nope"}))
        r = run("launch.py", "sonnet", "--dry-run")
        self.assertEqual(r.returncode, 3)
        self.assertIn("agent 'nope' is not supported", r.stderr)

    def test_models_without_sonnet_still_launch(self):
        self.home.write("config/agent-foreman/providers.json",
                        {"providers": [{"id": "anthropic", "models": [{"id": "opus"}, {"id": "haiku"}]}],
                         "tiers": {"low": ["haiku"], "mid": ["haiku", "opus"], "high": ["opus", "haiku"]}})
        r = run("launch.py", "opus", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--model opus", r.stdout)

    def test_resume_continues_a_session(self):
        r = run("launch.py", "opus", "--name", "7", "--resume", "abc-123", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--name 7 --resume abc-123 --model opus", r.stdout)
        self.assertNotIn("--session-id", r.stdout)
        for extra in (["--session-id", "x"], ["--print", "--prompt-file", "p", "--out", "o"]):
            r = run("launch.py", "opus", "--resume", "abc-123", "--dry-run", *extra)
            self.assertEqual(r.returncode, 2, extra)
            self.assertIn("--resume continues a pane agent's session", r.stderr)

    def test_no_edit(self):
        r = run("launch.py", "opus", "--no-edit", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--disallowedTools 'Edit,Write,NotebookEdit,Bash(gh pr merge:*)'", r.stdout)
        # no agent may merge: the foreman does, after the gate
        self.assertIn("--disallowedTools 'Bash(gh pr merge:*)'", run("launch.py", "opus", "--dry-run").stdout)

    def test_unknown_profile_is_setup(self):
        self.assertEqual(run("launch.py", "nope", "--dry-run").returncode, 3)

    def test_bad_settings_is_setup(self):
        self.home.write("config/agent-foreman/config.json", {"launch": {"permission": "maybe"}})
        r = run("launch.py", "sonnet", "--dry-run")
        self.assertEqual(r.returncode, 3)
        self.assertIn("permission", r.stderr)

    def test_gateway_token_missing_then_set_without_printing_it(self):
        self.home.write("config/agent-foreman/providers.json", GATEWAY)
        env = {"HF_TEST_TOKEN": ""}
        r = run("launch.py", "p", "--dry-run", env=env)
        self.assertEqual(r.returncode, 4)
        self.assertIn("HF_TEST_TOKEN", r.stderr)
        r = run("launch.py", "p", "--dry-run", env={"HF_TEST_TOKEN": "secret-value-xyz"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ANTHROPIC_AUTH_TOKEN", r.stdout)
        self.assertNotIn("secret-value-xyz", r.stdout + r.stderr)

    def test_bad_project_argument(self):
        self.assertEqual(run("launch.py", "sonnet", "--project", "bad", "--dry-run").returncode, 2)
        r = run("launch.py", "--dry-run")  # the foreman always names the profile
        self.assertEqual(r.returncode, 2)
        self.assertIn("profile", r.stderr)


FAKE_CLAUDE = """#!/usr/bin/env python3
import json, os, sys
prompt = sys.stdin.read().strip()
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "garbage":
    print("not json")
    sys.exit(1)
out = {"type": "result", "subtype": "success", "is_error": False, "session_id": "s-1",
       "total_cost_usd": 0.01, "permission_denials": [],
       "result": "|".join([prompt, " ".join(sys.argv[1:]), os.environ.get("ANTHROPIC_BASE_URL", "-")]),
       "status": [os.environ.get("AF_STATUS_FILE", "-"), os.environ.get("AF_AGENT", "-")]}
if os.environ.get("FAKE_RESULT"):
    out["result"] = os.environ["FAKE_RESULT"]
if mode == "error":
    out.update(is_error=True, subtype="error_during_execution", result="rate limited")
print(json.dumps(out))
if mode == "exit-after-result":
    sys.stderr.write("x" * 3000 + "disk full")
    sys.exit(2)
"""


class PromptMode(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        bindir = os.path.join(self.home.root, "bin")
        os.makedirs(bindir)
        path = os.path.join(bindir, "claude")
        with open(path, "w") as f:
            f.write(FAKE_CLAUDE)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        self.env = {"PATH": bindir + os.pathsep + os.environ["PATH"]}
        self.prompt = self.home.write("prompt.txt", "review #7")
        self.out = os.path.join(self.home.root, "runs", "review-1.json")

    def tearDown(self):
        self.home.close()

    def launch(self, *args, **env):
        return run("launch.py", *args, "--print", "--prompt-file", self.prompt, "--out", self.out,
                   env={**self.env, **env})

    def test_one_run_keeps_the_result_and_prints_a_summary(self):
        r = self.launch("opus", "--session-id", "abc", ANTHROPIC_BASE_URL="https://leaked.example")
        self.assertEqual(r.returncode, 0, r.stderr)
        summary = json.loads(r.stdout)
        self.assertEqual((summary["ok"], summary["session_id"], summary["cost"], summary["out"]),
                         (True, "s-1", 0.01, self.out))
        prompt, argv, base = json.load(open(self.out))["result"].split("|")
        self.assertEqual(prompt, "review #7")
        self.assertEqual(argv, "-p --output-format json --session-id abc --model opus --dangerously-skip-permissions "
                               "--disallowedTools Bash(gh pr merge:*)")
        self.assertEqual(base, "-")  # an inherited gateway variable never reaches an Anthropic agent

    def test_gateway_profile_reaches_the_agent(self):
        self.home.write("config/agent-foreman/providers.json", GATEWAY)
        r = self.launch("p", HF_TEST_TOKEN="secret-value-xyz")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.load(open(self.out))["result"].split("|")[2], "https://gw.example/anthropic")
        self.assertNotIn("secret-value-xyz", r.stdout + r.stderr)

    def test_failed_run_exits_5(self):
        for mode, words in (("error", "rate limited"), ("garbage", "not json")):
            r = self.launch("opus", FAKE_MODE=mode)
            self.assertEqual(r.returncode, 5, mode)
            summary = json.loads(r.stdout)
            self.assertFalse(summary["ok"])
            self.assertIn(words, summary["error"])

    def test_exit_code_and_stderr_are_recorded(self):
        r = self.launch("opus", FAKE_MODE="exit-after-result", FAKE_RESULT="done\nVerdict: approved")
        self.assertEqual(r.returncode, 5)
        summary = json.loads(r.stdout)
        self.assertEqual((summary["ok"], summary["verdict"]), (False, ""))
        self.assertTrue(summary["error"].startswith("exit 2 after a result: "), summary["error"])
        self.assertTrue(summary["error"].endswith("disk full"))
        with open(self.out[:-5] + ".meta.json") as f:
            meta = json.load(f)
        self.assertEqual((meta["ok"], meta["exit_code"], len(meta["stderr"])), (False, 2, 2000))
        self.assertTrue(meta["stderr"].endswith("disk full"))
        self.launch("opus")
        with open(self.out[:-5] + ".meta.json") as f:
            meta = json.load(f)
        self.assertEqual((meta["ok"], meta["exit_code"], meta["stderr"]), (True, 0, ""))

    def test_status_file_is_handed_over_or_cleared(self):
        r = self.launch("opus", "--status", "~/runs/o-r/7/status.jsonl", HOME=self.home.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.load(open(self.out))["status"],
                         [os.path.join(self.home.root, "runs", "o-r", "7", "status.jsonl"), "opus"])
        r = self.launch("opus", AF_STATUS_FILE="/lead/status.jsonl", AF_AGENT="lead")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.load(open(self.out))["status"], ["-", "-"])  # never the starter's file

    def git_checkout(self):
        repo = os.path.join(self.home.root, "clone")
        subprocess.run(["git", "init", "-q", repo], check=True)
        subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q",
                        "--allow-empty", "-m", "x"], check=True)
        return repo, subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    def test_task_folder_and_run_record(self):
        task = os.path.join(self.home.root, "task")
        out = os.path.join(task, "reviews", "pair-1-1.json")
        clone, head = self.git_checkout()
        self.home.write("config/agent-foreman/providers.json", GATEWAY)
        r = run("launch.py", "p", "--print", "--prompt-file", self.prompt, "--out", out, "--role", "pair",
                "--name", "pair-1", "--task-dir", task, env={**self.env, "HF_TEST_TOKEN": "t"}, workdir=clone)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.load(open(out))["status"], [os.path.join(task, "status.jsonl"), "pair-1"])
        meta = json.load(open(out[:-5] + ".meta.json"))
        self.assertEqual((meta["role"], meta["agent"], meta["profile"], meta["gateway"], meta["model"], meta["head"],
                          meta["ok"], meta["session_id"]), ("pair", "pair-1", "p", "gw", "p", head, True, "s-1"))
        self.assertTrue(meta["started"] <= meta["ended"])
        self.assertRegex(meta["ended"], r"\.\d{6}Z$")  # to the microsecond, so runs in one second still sort
        r = self.launch("opus", FAKE_MODE="error")
        self.assertFalse(json.load(open(self.out[:-5] + ".meta.json"))["ok"])
        r = run("launch.py", "opus", "--task-dir", task, "--dry-run", env=self.env)
        self.assertIn("AF_TASK_DIR", r.stdout.split("set:")[1].split("\n")[0])
        self.assertNotIn(task, r.stdout)

    def test_verdict_in_the_summary(self):
        r = self.launch("opus", FAKE_RESULT="must-fix: none\n**Verdict: approved**")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["verdict"], "approved")
        with open(self.out[:-5] + ".meta.json") as f:
            self.assertEqual(json.load(f)["verdict"], "approved")
        self.assertEqual(json.loads(self.launch("opus", FAKE_RESULT="no verdict here").stdout)["verdict"], "")

    def test_role_run_must_land_in_the_task_folder(self):
        task = os.path.join(self.home.root, "task")
        inside = os.path.join(task, "reviews", "pair-1-1.json")
        clone, _ = self.git_checkout()
        cases = [(["--name", "pair-1", "--out", inside], clone, "--task-dir"),
                 (["--task-dir", task, "--out", inside], clone, "--name"),
                 (["--task-dir", task, "--name", "pair-1", "--out", self.out], clone, "reviews/"),
                 (["--task-dir", task, "--name", "pair-1", "--out", inside], self.home.root, "not a git checkout")]
        for extra, where, words in cases:
            r = run("launch.py", "opus", "--print", "--prompt-file", self.prompt, "--role", "pair", *extra,
                    env=self.env, workdir=where)
            self.assertEqual(r.returncode, 2, extra)
            self.assertIn(words, r.stderr)
        self.assertFalse(os.path.exists(task))
        self.assertFalse(os.path.exists(self.out))

    def test_paths_with_a_tilde(self):
        prompt = "~/" + os.path.relpath(self.prompt, self.home.root)
        out = "~/runs/tilde.json"
        r = run("launch.py", "opus", "--print", "--prompt-file", prompt, "--out", out,
                env={**self.env, "HOME": self.home.root})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.home.root, "runs", "tilde.json")))

    def test_status_in_dry_run_names_only(self):
        r = run("launch.py", "opus", "--name", "t-7", "--status", "/x/status.jsonl", "--dry-run", env=self.env)
        self.assertIn("AF_STATUS_FILE", r.stdout.split("set:")[1].split("\n")[0])
        self.assertNotIn("/x/status.jsonl", r.stdout)
        r = run("launch.py", "opus", "--dry-run", env=self.env)
        self.assertIn("AF_STATUS_FILE", r.stdout.split("clear:")[1].split("\n")[0])

    def test_print_needs_files(self):
        self.assertEqual(run("launch.py", "opus", "--print", "--prompt-file", self.prompt, env=self.env).returncode, 2)
        self.assertEqual(run("launch.py", "opus", "--print", "--prompt-file", "/no/such", "--out", self.out,
                             env=self.env).returncode, 2)


CODEX = providers({"id": "openai", "agent": "codex", "models": [{"id": "gpt-5.5", "name": "gpt"}]})

FAKE_CODEX = """#!/usr/bin/env python3
import json, os, sys
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "garbage":
    print("not json")
    sys.exit(1)
prompt = sys.stdin.read().strip()
linked = sorted(os.listdir(".agents/skills")) if os.path.isdir(".agents/skills") else []
text = os.environ.get("FAKE_RESULT") or json.dumps({"prompt": prompt, "argv": sys.argv[1:], "linked": linked,
                                                    "alias": os.environ.get("AF_SESSION_ALIAS", "-")})
print(json.dumps({"type": "thread.started", "thread_id": "t-1"}))
print(json.dumps({"type": "turn.started"}))
if mode == "fail":
    print(json.dumps({"type": "turn.failed", "error": {"message": "usage limit reached"}}))
    sys.exit(1)
print(json.dumps({"type": "item.completed", "item": {"id": "i0", "type": "agent_message", "text": "working on it"}}))
print(json.dumps({"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": text}}))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}))
"""


class Codex(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.home.write("config/agent-foreman/providers.json", CODEX)
        bindir = os.path.join(self.home.root, "bin")
        os.makedirs(bindir)
        path = os.path.join(bindir, "codex")
        with open(path, "w") as f:
            f.write(FAKE_CODEX)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        self.env = {"PATH": bindir + os.pathsep + os.environ["PATH"]}
        self.prompt = self.home.write("prompt.txt", "review #7")
        self.out = os.path.join(self.home.root, "runs", "review-1.json")

    def tearDown(self):
        self.home.close()

    def clone(self):
        repo = os.path.join(self.home.root, "clone")
        self.home.write("clone/.claude/skills/tidy/SKILL.md", "---\nname: tidy\ndescription: x\n---\n")
        self.home.write("clone/.claude/skills/notes.md", "not a skill")
        self.home.write("clone/.agents/skills/own/SKILL.md", "---\nname: own\ndescription: x\n---\n")
        subprocess.run(["git", "init", "-q", repo], check=True)
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q",
                        "-m", "x"], check=True)
        return repo

    def test_pane_command(self):
        r = run("launch.py", "gpt", "--name", "lead-1", "--session-id", "abc-123", "--dry-run", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("agent:   codex", r.stdout)
        self.assertIn("AF_SESSION_ALIAS", r.stdout.split("set:")[1].split("\n")[0])
        command = r.stdout.split("command: ")[1]
        self.assertTrue(command.startswith("codex --model gpt-5.5 --dangerously-bypass-approvals-and-sandbox -c "),
                        command)
        self.assertIn("hook.py session", command)
        self.assertIn("hook.py guard", command)
        self.assertNotIn("--no-edit", command)
        self.assertTrue(command.strip().endswith("--dangerously-bypass-hook-trust"), command)

    def test_resume_finds_codex_own_id(self):
        r = run("launch.py", "gpt", "--resume", "abc-12345", "--dry-run", env={**self.env, "HOME": self.home.root})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.split("command: ")[1].startswith("codex resume --model gpt-5.5"))
        self.assertTrue(r.stdout.strip().endswith("--last"), r.stdout)  # no record yet: the folder's last session
        self.home.write("state/agent-foreman/sessions/abc-12345.json", {"session_id": "019a-real"})
        r = run("launch.py", "gpt", "--resume", "abc-12345", "--dry-run", env=self.env)
        self.assertTrue(r.stdout.strip().endswith("--dangerously-bypass-hook-trust 019a-real"), r.stdout)

    def test_prompt_mode_reads_json_lines(self):
        clone = self.clone()
        r = run("launch.py", "gpt", "--print", "--prompt-file", self.prompt, "--out", self.out, "--no-edit",
                env={**self.env, "AF_SESSION_ALIAS": "lead-alias-1"}, workdir=clone)
        self.assertEqual(r.returncode, 0, r.stderr)
        summary = json.loads(r.stdout)
        self.assertEqual((summary["ok"], summary["session_id"], summary["cost"]), (True, "t-1", None))
        answer = json.loads(launch_answer(self.out))
        self.assertEqual(answer["prompt"], "review #7")
        self.assertEqual(answer["argv"][:4], ["exec", "--json", "--model", "gpt-5.5"])
        self.assertIn("guard --no-edit", " ".join(answer["argv"]))
        self.assertEqual(answer["alias"], "-")  # a role never writes over its starter's session record
        self.assertEqual(answer["linked"], ["own", "tidy"])

    def test_prompt_mode_verdict_and_failure(self):
        r = run("launch.py", "gpt", "--print", "--prompt-file", self.prompt, "--out", self.out,
                env={**self.env, "FAKE_RESULT": "- could: none\n\nVerdict: approved"})
        self.assertEqual(json.loads(r.stdout)["verdict"], "approved")
        with open(self.out) as f:  # the gate reads the answer file in Claude Code's names
            saved = json.load(f)
        self.assertEqual((saved["result"], saved["session_id"], saved["is_error"], saved["usage"]["output_tokens"]),
                         ("- could: none\n\nVerdict: approved", "t-1", False, 2))
        for mode, words in (("fail", "usage limit reached"), ("garbage", "not json")):
            r = run("launch.py", "gpt", "--print", "--prompt-file", self.prompt, "--out", self.out,
                    env={**self.env, "FAKE_MODE": mode})
            self.assertEqual(r.returncode, 5, mode)
            self.assertIn(words, json.loads(r.stdout)["error"])

    def test_bundle_skills_are_linked_and_kept_out_of_git(self):
        root = os.path.join(self.home.root, "bundle")
        shutil.copytree(SCRIPTS, os.path.join(root, "scripts"))
        self.home.write("bundle/bundle.json", {"agents": ["claude", "codex"]})
        self.home.write("bundle/config.json", {"gateways": {"openai": {"kind": "openai"}},
                                               "profiles": {"gpt": {"gateway": "openai", "model": "gpt-5.5",
                                                                    "agent": "codex"}},
                                               "launch": {"permission": "bypass"}})
        self.home.write("bundle/.claude-plugin/plugin.json", {"name": "foreman-kit"})
        self.home.write("bundle/skills/commit/SKILL.md", "---\nname: commit\n---\n")
        self.home.write("bundle/plugins/flow/.claude-plugin/plugin.json", {"name": "flow"})
        self.home.write("bundle/plugins/flow/skills/plan/SKILL.md", "---\nname: plan\n---\n")
        clone = self.clone()
        for _ in range(2):
            r = run("launch.py", "gpt", "--print", "--prompt-file", self.prompt, "--out", self.out, env=self.env,
                    cwd=os.path.join(root, "scripts"), workdir=clone)
            self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(launch_answer(self.out))["linked"], ["flow--plan", "foreman-kit--commit", "own",
                                                                         "tidy"])
        skills = os.path.join(clone, ".agents", "skills")
        self.assertEqual(os.readlink(os.path.join(skills, "foreman-kit--commit")), os.path.join(root, "skills", "commit"))
        self.assertEqual(os.readlink(os.path.join(skills, "tidy")), os.path.join("..", "..", ".claude", "skills", "tidy"))
        self.assertFalse(os.path.islink(os.path.join(skills, "own")))
        with open(os.path.join(clone, ".git", "info", "exclude")) as f:
            excluded = [line for line in f.read().splitlines() if line.startswith("/")]
        self.assertEqual(excluded, ["/.agents/skills/foreman-kit--commit", "/.agents/skills/flow--plan",
                                    "/.agents/skills/tidy"])
        status = subprocess.run(["git", "-C", clone, "status", "--porcelain"], capture_output=True, text=True)
        self.assertEqual(status.stdout, "")

    def test_codex_on_a_compatible_gateway_is_setup(self):
        self.home.write("config/agent-foreman/providers.json", GATEWAY)
        self.home.write("config/agent-foreman/config.json", {})
        bad = providers({"id": "gw", "base_url": "https://gw.example/anthropic", "auth": "bearer",
                         "token_env": "HF_TEST_TOKEN", "models": [{"id": "model-1", "name": "p", "context": 100000,
                                                                   "agent": "codex"}]})
        self.home.write("config/agent-foreman/providers.json", bad)
        r = run("launch.py", "p", "--dry-run", env={**self.env, "HF_TEST_TOKEN": "t"})
        self.assertEqual(r.returncode, 3)
        self.assertIn("codex cannot run on gateway gw", r.stderr)


def launch_answer(out):
    with open(out) as f:
        return json.load(f)["result"]


if __name__ == "__main__":
    unittest.main()
