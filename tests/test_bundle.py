import io
import json
import os
import re
import unittest
import zipfile
from unittest import mock

from helpers import TempHome, run

import bundle
import config
import loop as loops


class Bundle(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.skill = os.path.dirname(self.home.write("skills/tidy/SKILL.md", "---\nname: tidy\n---\nTidy."))
        self.home.write("skills/tidy/scripts/run.py", "print('hi')")
        self.home.write("skills/tidy/__pycache__/x.pyc", "junk")
        self.home.write("state/agent-foreman/projects/o-r/project.json",
                        {"repo": "o/r", "machines": {"local": "/src/r"}, "bundle": {"skills": ["p:tidy"]}})
        patcher = mock.patch.object(bundle, "local_skills", return_value={"p:tidy": self.skill})
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in loops.KIT:
            self.home.write(f"kit/skills/{name}/SKILL.md", f"---\nname: {name}\n---\nDo {name}.")
        kit = mock.patch.object(bundle, "KIT_DIR", os.path.join(self.home.root, "kit", "skills"))
        kit.start()
        self.addCleanup(kit.stop)
        self.kit = [f"foreman-kit:{n}" for n in loops.KIT]

    def tearDown(self):
        self.home.close()

    def test_same_content_same_hash_and_change_makes_new(self):
        h1, files, skills, _ = bundle.build("o/r", [])
        h2, _, _, _ = bundle.build("o/r", [])
        self.assertEqual(h1, h2)
        self.assertEqual(skills, ["foreman-kit:tidy"] + self.kit)
        self.assertIn("skills/tidy/scripts/run.py", files)
        self.assertIn("skills/cross-check/SKILL.md", files)  # every default skill is carried
        self.assertNotIn("skills/tidy/__pycache__/x.pyc", files)
        for rel in ("bundle.json", ".claude-plugin/plugin.json", "config.json", "loop.md", "scripts/launch.py",
                    "scripts/config.py", "scripts/transcript.py", "scripts/gate.py", "scripts/status.py",
                    "scripts/clone.py", "scripts/loop.py", "scripts/heartbeat.py", "scripts/fulltest.py",
                    "scripts/hook.py", "scripts/adapters/__init__.py",
                    "scripts/adapters/base.py", "scripts/adapters/claude.py", "scripts/adapters/codex.py"):
            self.assertIn(rel, files)
        self.assertEqual(json.loads(files["bundle.json"]), {"agents": ["claude", "codex"]})  # one bundle, every kind
        self.home.write("skills/tidy/SKILL.md", "---\nname: tidy\n---\nTidy more.")
        h3, _, _, _ = bundle.build("o/r", [])
        self.assertNotEqual(h1, h3)

    def test_every_script_starts_from_the_bundle(self):
        h, files, _, _ = bundle.build("o/r", [])
        path, _ = bundle.write_local(h, files)
        for name in bundle.BUNDLED:
            if name == "heartbeat.py":
                continue  # a hook command with no --help; test_status runs it
            r = run(name, "--help", cwd=os.path.join(path, "scripts"))
            self.assertEqual(r.returncode, 0, f"{name}: {r.stderr[-300:]}")

    def test_a_script_that_a_bundled_script_runs_is_bundled(self):
        here = os.path.dirname(os.path.abspath(bundle.__file__))
        scripts = {n for n in os.listdir(here) if n.endswith(".py")}
        for name in bundle.BUNDLED:
            with open(os.path.join(here, name)) as f:
                named = set(re.findall(r'"([a-z_]+\.py)"', f.read())) & scripts
            self.assertEqual(named - set(bundle.BUNDLED), set(), name)  # gate.py and loop.py run fulltest.py

    def test_heartbeat_hooks_point_at_the_bundled_script(self):
        _, files, _, _ = bundle.build("o/r", [])
        hooks = json.loads(files["hooks/hooks.json"])["hooks"]
        commands = [h["command"] for event in ("PostToolUse", "Stop") for group in hooks[event] for h in group["hooks"]]
        self.assertEqual(commands, ['python3 "${CLAUDE_PLUGIN_ROOT}/scripts/heartbeat.py" post',
                                    'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/heartbeat.py" stop'])
        self.assertIn("scripts/heartbeat.py", files)
        self.assertIn(".claude-plugin/plugin.json", files)  # the bundle root is the plugin root

    def test_settings_change_makes_new_hash(self):
        h1, _, _, _ = bundle.build("o/r", [])
        self.home.write("config/agent-foreman/config.json", {"launch": {"permission": "default"}})
        h2, _, _, _ = bundle.build("o/r", [])
        self.assertNotEqual(h1, h2)

    def test_written_once_then_cached(self):
        h, files, _, _ = bundle.build("o/r", [])
        path, status = bundle.write_local(h, files)
        self.assertEqual(status, "built")
        self.assertTrue(os.path.isfile(os.path.join(path, "skills", "tidy", "SKILL.md")))
        self.assertEqual(bundle.write_local(h, files), (path, "cached"))

    def test_zip_holds_every_file(self):
        _, files, _, _ = bundle.build("o/r", [])
        with zipfile.ZipFile(io.BytesIO(bundle.zipped(files))) as z:
            self.assertEqual({n: z.read(n) for n in z.namelist()}, files)

    def test_unknown_skill_stops(self):
        with self.assertRaises(SystemExit) as e:
            bundle.build("o/r", ["p:gone"])
        self.assertEqual(e.exception.code, config.EXIT_SETUP_NEEDED)

    def test_two_skills_with_one_name_stop(self):
        with mock.patch.object(bundle, "local_skills", return_value={"p:tidy": self.skill, "tidy": self.skill}):
            with self.assertRaises(SystemExit) as e:
                bundle.build("o/r", ["tidy"])
        self.assertEqual(e.exception.code, config.EXIT_SETUP_NEEDED)

    def test_project_without_settings_stops(self):
        with self.assertRaises(SystemExit) as e:
            bundle.build("o/other", [])
        self.assertEqual(e.exception.code, config.EXIT_SETUP_NEEDED)

    def test_loop_skills_project_first_then_bundle_then_warning(self):
        self.home.write("config/agent-foreman/config.json",
                        {"loop": {"work": [{"id": "simplify", "skills": ["tidy", "scenario", "ghost"]}]}})
        _, files, skills, warnings = bundle.build("o/r", [], project_names=["scenario"])
        self.assertEqual(skills, ["foreman-kit:tidy"] + self.kit)  # bundle.skills and the loop name the same skill
        self.assertFalse(any(rel.startswith("skills/scenario/") for rel in files))  # a project skill stays put
        self.assertEqual(len(warnings), 1)
        self.assertIn("ghost", warnings[0])

    def test_a_replacement_comes_from_the_project_or_the_person(self):
        self.home.write("config/agent-foreman/config.json", {"skills": {"cross-check": "scenario", "simplify": "tidy"}})
        _, files, skills, warnings = bundle.build("o/r", [], project_names=["scenario"])
        self.assertEqual((skills.count("foreman-kit:tidy"), warnings), (1, []))
        self.assertIn("skills/cross-check/SKILL.md", files)  # the default stays in the bundle for the flow and record

    def test_a_plugin_dir_skill_goes_with_its_plugin_not_as_a_copy(self):
        flow = os.path.dirname(os.path.dirname(self.home.write("flow/.claude-plugin/plugin.json", {"name": "flow"})))
        self.home.write("flow/skills/impl/SKILL.md", "---\nname: impl\n---\n")
        self.home.write("config/agent-foreman/config.json",
                        {"plugin_dirs": [flow], "loop": {"work": [{"id": "build", "skills": ["tdd", "impl"]}]}})
        plugins = [{"id": "flow@inline", "scope": "session", "enabled": True, "installPath": flow}]
        with mock.patch.object(bundle, "plugin_list", return_value=plugins), \
                mock.patch.object(bundle, "local_skills",
                                  return_value={"p:tidy": self.skill, "flow:impl": os.path.join(flow, "skills", "impl")}):
            h1, files, skills, warnings = bundle.build("o/r", [])
        self.assertEqual((skills[-1], warnings), ("flow:impl", []))
        self.assertFalse(any(rel.startswith("skills/impl/") for rel in files))  # not a copy among foreman-kit's
        self.assertIn("plugins/flow/skills/impl/SKILL.md", files)  # but the whole plugin, carried along
        self.assertIn("plugins/flow/.claude-plugin/plugin.json", files)
        self.assertEqual(json.loads(files["config.json"])["plugins"], ["flow"])
        h2, files, _, _ = bundle.build("o/r", [])  # without the plugin listed: nothing carried
        self.assertEqual(json.loads(files["config.json"])["plugins"], [])
        self.assertNotEqual(h1, h2)

    def test_a_missing_default_skill_is_a_warning(self):
        os.remove(os.path.join(self.home.root, "kit", "skills", "smoke", "SKILL.md"))
        _, _, skills, warnings = bundle.build("o/r", [])
        self.assertNotIn("foreman-kit:smoke", skills)
        self.assertTrue(any("default skill smoke is missing" in w for w in warnings))

    def test_unknown_or_disabled_machine(self):
        machines = {"off": {"target": "h", "enabled": False}}
        with mock.patch.object(bundle, "herdr_machines", return_value=machines):
            for label in ("ghost", "off"):
                with self.assertRaises(SystemExit) as e:
                    bundle.main(["push", label, "--project", "o/r"])
                self.assertEqual(e.exception.code, 2)

    def test_bad_arguments(self):
        for argv in (["push", "--project", "o/r"], ["build", "--project", "bad"]):
            with self.assertRaises(SystemExit) as e:
                bundle.main(argv)
            self.assertEqual(e.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
