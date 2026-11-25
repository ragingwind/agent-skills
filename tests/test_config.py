import http.server
import io
import json
import os
import subprocess
import threading
import unittest
from unittest import mock

from helpers import TempHome, providers, run

import config

MACHINES = {"m1": {"target": "host-1", "enabled": True}, "off": {"target": "host-2", "enabled": False}}


class ModelLists(unittest.TestCase):
    """`check --models`: each provider with a base_url is asked for its model list."""

    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        seen = self.seen = []

        class Provider(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, self.headers.get("Authorization"), self.headers.get("x-api-key")))
                if not self.path.startswith("/ok/v1/models"):
                    self.send_error(404)
                    return
                if self.headers.get("Authorization") != "Bearer k-123" and self.headers.get("x-api-key") != "k-123":
                    self.send_error(401)
                    return
                second = "after_id=vendor%2Fgood" in self.path
                page = ({"data": [{"id": "vendor/other"}], "has_more": False} if second else
                        {"data": [{"id": "vendor/good"}], "has_more": True, "last_id": "vendor/good"})
                body = json.dumps(page).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}"
        self.home.write("config/agent-foreman/providers.json", providers(
            {"id": "gw", "base_url": f"{url}/ok", "auth": "bearer", "token_env": "GW_KEY",
             "models": [{"id": "vendor/good", "name": "good", "context": 1000},
                        {"id": "vendor/typo", "name": "typo", "context": 1000}]},
            {"id": "keyed", "base_url": f"{url}/ok/", "auth": "x-api-key", "token_env": "GW_KEY",
             "models": [{"id": "vendor/other", "name": "other", "context": 1000}]},
            {"id": "gone", "base_url": f"{url}/missing", "auth": "bearer", "token_env": "GONE_KEY",
             "models": [{"id": "vendor/x", "name": "x", "context": 1000}]}))
        self.env = {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}

    def test_a_model_missing_from_the_list_is_a_problem(self):
        r = run("config.py", "check", "--models", env={**self.env, "GW_KEY": "k-123", "GONE_KEY": "k-9"})
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("model good (vendor/good) at gw: listed", r.stdout)
        self.assertIn("model other (vendor/other) at keyed: listed", r.stdout)  # the second page, by x-api-key
        self.assertIn("model typo (vendor/typo) at gw: not listed: ", r.stdout)
        self.assertIn("lists 2 models, not this one", r.stdout)
        self.assertIn("model x (vendor/x) at gone: unknown: ", r.stdout)
        self.assertIn("/missing/v1/models answered HTTP 404", r.stdout)
        self.assertNotIn("k-123", r.stdout + r.stderr)
        self.assertNotIn("k-9", r.stdout + r.stderr)
        self.assertIn(("/ok/v1/models?limit=1000", None, "k-123"), self.seen)  # the slash in base_url is not doubled

    def test_without_a_key_or_a_list_the_models_are_unknown(self):
        r = run("config.py", "check", "--models", env={**self.env, "GW_KEY": "", "GONE_KEY": ""})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("model typo (vendor/typo) at gw: unknown: token variable GW_KEY is not set", r.stdout)
        self.assertEqual(self.seen, [])  # nothing is asked without a key
        r = run("config.py", "check", env={**self.env, "GW_KEY": "k-123"})
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "ok"))  # plain check uses no network
        self.assertEqual(self.seen, [])


class Levels(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_standard_alone_is_valid(self):
        cfg = config.load()
        self.assertNotIn("profile", cfg["launch"])  # the foreman names the profile at every start
        self.assertEqual(config.validate(cfg), [])

    def test_user_over_standard_and_project_over_user(self):
        self.home.write("config/agent-foreman/config.json",
                        {"launch": {"permission": "default"}, "ops": {"check_minutes": 5}})
        self.home.write("state/agent-foreman/projects/o-r/project.json",
                        {"repo": "o/r", "machines": {"m1": "/src/r"}, "ops": {"check_minutes": 20}})
        user = config.load()
        self.assertEqual(user["launch"]["permission"], "default")
        self.assertEqual(user["ops"]["stall_minutes"], 30)  # untouched key falls back
        project = config.load("o/r")
        self.assertEqual(project["ops"]["check_minutes"], 20)
        self.assertEqual(project["launch"]["permission"], "default")
        self.assertEqual(project["workspace"], "r")
        self.assertEqual(config.validate(project, saved=MACHINES, project=True), [])

    def test_diff_then_merge_gives_the_full_settings(self):
        base = config.standard()
        full = config.merge(base, {"ops": {"batch": 2}, "labels": {"default": "{task}/{stage}"}})
        self.assertEqual(config.diff(base, full), {"ops": {"batch": 2}, "labels": {"default": "{task}/{stage}"}})
        self.assertEqual(config.merge(base, config.diff(base, full)), full)


class Problems(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.cfg = config.load()

    def tearDown(self):
        self.home.close()

    def problems(self, over, project=False, skills=None):
        return config.validate(config.merge(self.cfg, over), saved=MACHINES, skills=skills, project=project)

    def test_unknown_agent_kind(self):
        p = self.problems({"profiles": {"sonnet": {"agent": "nope"}}})
        self.assertTrue(any("agent 'nope' is not supported" in x for x in p))

    def test_unknown_setting(self):
        self.assertIn("unknown setting 'opps'", self.problems({"opps": {}}))

    def test_label_placeholder_and_event(self):
        p = self.problems({"labels": {"default": "{task} {stge}", "events": {"nap": "{task}"}}})
        self.assertTrue(any("{stge}" in x for x in p))
        self.assertTrue(any("'nap'" in x for x in p))

    def test_broken_label_format(self):
        self.assertTrue(any(x.startswith("labels: default") for x in self.problems({"labels": {"default": "{task"}})))

    def test_ops_values(self):
        p = self.problems({"ops": {"check_minutes": 0, "batch": 0, "placement": "random",
                                   "disk_check": "yes", "backoff": {"first_hours": 0, "factor": 0.5}}})
        for word in ("check_minutes", "batch", "placement", "disk_check", "first_hours", "factor"):
            self.assertTrue(any(word in x for x in p), word)

    def test_loop_problems_are_reported(self):
        self.assertIn("loop: work must be a list of steps", self.problems({"loop": {"work": "x"}}))
        p = self.problems({"labels": {"events": {"build": "{task} build", "refactor": "{task} tidy", "nap": "{task}"}}})
        self.assertFalse(any("'build'" in x for x in p))  # a stage of the work loop takes a label
        self.assertTrue(any("'refactor'" in x for x in p))  # a step does not: the tab follows the stages
        self.assertTrue(any("'nap'" in x for x in p))

    def test_unknown_skill_and_shared_short_name(self):
        over = {"bundle": {"skills": ["p:clean", "clean", "p:gone"]}}
        p = self.problems(over, skills={"p:clean": "/x", "clean": "/y"})
        self.assertIn("skill 'p:gone' is not available on this machine", p)
        self.assertTrue(any("share the name clean in the bundle" in x for x in p))

    def test_profile_and_gateway(self):
        p = self.problems({"launch": {"profile": "nope"},
                           "gateways": {"g": {"kind": "anthropic-compatible", "base_url": "ftp://x",
                                              "token_env": "BAD NAME", "auth": "basic", "models": {}}},
                           "profiles": {"p": {"gateway": "g", "model": "m", "roles": {}}}})
        for word in ("launch: unknown key 'profile'; name the profile", "base_url", "token_env", "auth", "model 'm'", "role opus"):
            self.assertTrue(any(word in x for x in p), word)

    def test_project_machines(self):
        over = {"repo": "bad", "machines": {"m1": "relative/path", "off": "/x", "ghost": "/y"}}
        p = self.problems(over, project=True)
        self.assertIn("project: repo must look like owner/name", p)
        self.assertIn("project: machine m1: project path must start with / or ~", p)
        self.assertIn("project: machine off is disabled in herdr", p)
        self.assertTrue(any("machine ghost is not a saved herdr machine" in x for x in p))
        self.assertTrue(any("machines must name" in x for x in self.problems({"repo": "o/r"}, project=True)))

    def test_project_full_test_command(self):
        base = {"repo": "o/r", "workspace": "r", "machines": {"local": "/r"}}
        self.assertEqual(self.problems({**base, "tests": {"full": "make test"}}, project=True), [])
        self.assertIn("project: tests.full must be a command",
                      self.problems({**base, "tests": {"full": " "}}, project=True))
        self.assertIn("project: tests may only name full, the project's full test command",
                      self.problems({**base, "tests": {"unit": "x"}}, project=True))

    def test_project_gate(self):
        base = {"repo": "o/r", "workspace": "r", "machines": {"local": "/r"}}
        good = [{"check": "command", "name": "closing-keyword", "run": "x", "at": "merge"}]
        self.assertEqual(self.problems({**base, "gate": good}, project=True), [])
        p = self.problems({**base, "gate": [{"check": "command", "run": "x"}]}, project=True)
        self.assertIn("project: gate: check 1 needs a name", p)
        self.assertIn("project: gate: must be a list of checks", self.problems({**base, "gate": {}}, project=True))
        self.assertIn("unknown setting 'gate'", self.problems({"gate": good}))  # a project's setting only


TF = {"id": "tf", "base_url": "https://tf.example", "auth": "bearer", "token_env": "TF_API_TOKEN",
      "models": [{"id": "zai-org/GLM-5.3-Flash", "name": "glm", "context": 200000},
                 {"id": "zai-org/GLM-5.3-Air", "name": "glm-air", "context": 128000, "roles": {"haiku": "glm"}}]}
TF_TIERS = {"low": ["glm", "haiku"], "mid": ["glm", "sonnet"], "high": ["opus", "sonnet"]}


class Providers(unittest.TestCase):
    """The models file the person edits, by provider."""

    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def write(self, data):
        self.home.write("config/agent-foreman/providers.json", data)

    def test_init_writes_the_standard_once(self):
        r = run("config.py", "providers", "--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["path"], out["created"], out["problems"]), (config.providers_path(), True, []))
        with open(config.providers_path()) as f, open(config.providers_sample_path()) as sample:
            self.assertEqual(f.read(), sample.read())  # copied as written, for the person to edit
        std = config.standard()
        self.assertEqual({k: config.load()[k] for k in config.MODEL_KEYS}, {k: std[k] for k in config.MODEL_KEYS})
        self.write(providers(tiers={"low": ["haiku"], "mid": ["haiku"], "high": ["opus", "sonnet"]}))
        self.assertFalse(json.loads(run("config.py", "providers", "--init").stdout)["created"])  # an edited file stays
        self.assertEqual(config.load()["tiers"]["mid"], ["haiku"])

    def test_the_sample_holds_the_standard_models(self):
        with open(config.providers_sample_path()) as f:
            sample = json.load(f)
        self.assertEqual(config.providers_problems(sample), [])
        self.assertEqual(sample, providers())  # Claude's own models, opus first
        std = config.standard()
        self.assertEqual(config.from_providers(sample), {k: std[k] for k in config.MODEL_KEYS})

    def test_a_compatible_provider(self):
        self.write(providers(TF, tiers=TF_TIERS))
        cfg = config.load()
        self.assertEqual(cfg["gateways"]["tf"], {"kind": "anthropic-compatible", "base_url": "https://tf.example",
                                                 "auth": "bearer", "token_env": "TF_API_TOKEN",
                                                 "models": {"glm": {"id": "zai-org/GLM-5.3-Flash", "context": 200000},
                                                            "glm-air": {"id": "zai-org/GLM-5.3-Air", "context": 128000}}})
        self.assertEqual(cfg["profiles"]["glm"]["roles"], {"opus": "glm", "sonnet": "glm", "haiku": "glm"})
        self.assertEqual(cfg["profiles"]["glm-air"]["roles"], {"opus": "glm-air", "sonnet": "glm-air", "haiku": "glm"})
        self.assertEqual(cfg["profiles"]["opus"], {"gateway": "anthropic", "model": "opus"})
        self.assertEqual(config.validate(cfg), [])
        self.assertEqual(config.token_names(cfg), ["TF_API_TOKEN"])
        self.assertEqual(config.role_candidates(cfg, "mid", "pair", lead="glm"), ["sonnet", "opus"])

    def test_a_codex_provider(self):
        self.write(providers({"id": "openai", "agent": "codex", "models": [{"id": "gpt-5.5", "name": "gpt"},
                                                                            {"id": "gpt-5.5-mini"}]},
                             tiers={"low": ["haiku"], "mid": ["gpt", "sonnet"], "high": ["opus", "gpt"]}))
        cfg = config.load()
        self.assertEqual(cfg["gateways"]["openai"], {"kind": "openai"})
        self.assertEqual(cfg["profiles"]["gpt"], {"gateway": "openai", "model": "gpt-5.5", "agent": "codex"})
        self.assertEqual(cfg["profiles"]["gpt-5.5-mini"]["agent"], "codex")
        self.assertEqual(cfg["profiles"]["opus"], {"gateway": "anthropic", "model": "opus"})
        self.assertEqual(config.validate(cfg), [])
        self.assertEqual(config.role_candidates(cfg, "mid", "pair", lead="gpt"), ["sonnet", "opus"])
        bad = providers({"id": "openai", "agent": "codex", "base_url": "https://x.example", "auth": "bearer",
                         "token_env": "K", "models": [{"id": "g", "context": 9}]},
                        {"id": "other", "agent": "nope", "models": [{"id": "n"}]})
        p = config.providers_problems(bad)
        for want in ("provider openai: codex runs only on its own login", "provider other: agent must be one of"):
            self.assertTrue(any(want in x for x in p), (want, p))
        self.write(providers(opus={"agent": "codex"}))
        self.assertIn("profile opus: codex cannot run on gateway anthropic (kind anthropic); it runs on openai",
                      config.validate(config.load()))

    def test_problems_in_the_file_s_own_terms(self):
        bad = providers({"id": "tf", "base_url": "ftp://x", "auth": "basic", "token_env": "sk-123 secret",
                         "models": [{"id": "zai-org/GLM"}, {"id": "m", "roles": {"opus": "ghost", "huge": "m"}},
                                    {"id": "sonnet", "context": 9}]},
                        {"id": "anthropic", "auth": "bearer", "models": [{"id": "opus[1m]", "context": 1}]},
                        tiers={"low": ["nope"], "mid": [], "huge": ["opus"]})
        bad["extra"] = 1
        p = config.providers_problems(bad)
        for want in ("unknown key 'extra'", "provider tf: base_url must be the provider's", "provider tf: auth must be",
                     "provider tf: token_env must name", "model zai-org/GLM: needs a name",
                     "model zai-org/GLM: context must be", "roles: opus names 'ghost'", "roles: 'huge' is not",
                     "model sonnet: the name sonnet is taken", "another provider has the same id",
                     "provider anthropic: auth applies only", "context and roles apply only",
                     "tiers: low names 'nope'", "tiers: mid must list", "unknown tier 'huge'", "tiers: high is missing"):
            self.assertTrue(any(want in x for x in p), want)
        self.write(bad)
        r = run("config.py", "check")
        self.assertEqual(r.returncode, 3)
        self.assertIn("provider tf: auth must be", r.stdout)
        self.assertNotIn("gateway tf", r.stdout)  # named once, in the file's terms
        self.assertEqual(json.loads(run("config.py", "providers").stdout)["problems"], p)

    def test_a_file_that_is_not_json_says_where(self):
        self.home.write("config/agent-foreman/providers.json", '{"providers": [],}')
        r = run("config.py", "providers")
        self.assertEqual(r.returncode, 3)
        self.assertIn("providers.json: not valid JSON at line 1, column 18", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_a_placeholder_url_is_refused(self):
        tf = {**TF, "base_url": "https://..."}
        self.assertTrue(any("base_url must be the provider's" in p for p in config.providers_problems(providers(tf))))
        self.assertFalse(config.url_ok("https://..."))
        self.assertTrue(config.url_ok("https://tf.example/anthropic"))

    def test_models_outside_the_file_are_named_and_never_used(self):
        self.home.write("config/agent-foreman/config.json", {"tiers": {"mid": ["haiku"]}, "ops": {"batch": 2}})
        cfg = config.load()
        self.assertEqual((cfg["tiers"]["mid"], cfg["ops"]["batch"]), (["sonnet"], 2))
        r = run("config.py", "check")
        self.assertEqual(r.returncode, 3)
        self.assertIn(f"tiers belong in {config.providers_path()}", r.stdout)
        self.home.write("config/agent-foreman/config.json", {})
        full = config.merge(config.load(), {"tiers": {"mid": ["haiku"]}})
        _, written, problems = config.save("user", full, dry_run=True)
        self.assertTrue(any("models are set in" in x for x in problems), problems)


class MergeById(unittest.TestCase):
    BASE = {"loop": {"work": [{"id": "a", "does": "x", "skills": []}, {"id": "b", "does": "y", "skills": []},
                              {"id": "c", "does": "z", "skills": []}]}}

    def test_one_changed_stage_stores_only_that_stage(self):
        full = config.merge(self.BASE, {"loop": {"work": [{"id": "b", "skills": ["tidy"]}]}})
        self.assertEqual([s["id"] for s in full["loop"]["work"]], ["a", "b", "c"])
        self.assertEqual(full["loop"]["work"][1], {"id": "b", "does": "y", "skills": ["tidy"]})
        self.assertEqual(config.diff(self.BASE, full), {"loop": {"work": [{"id": "b", "skills": ["tidy"]}]}})

    def test_add_after_remove_and_round_trip(self):
        full = config.merge(self.BASE, {"loop": {"work": [{"id": "c", "remove": True},
                                                          {"id": "n", "does": "new", "skills": [], "after": "a"},
                                                          {"id": "f", "does": "first", "skills": [], "after": None}]}})
        self.assertEqual([s["id"] for s in full["loop"]["work"]], ["f", "a", "n", "b"])
        d = config.diff(self.BASE, full)
        self.assertEqual(config.merge(self.BASE, d), full)
        self.assertIn({"id": "c", "remove": True}, d["loop"]["work"])

    def test_standard_unchanged_after_saving_one_stage(self):
        home = TempHome()
        try:
            full = config.load()
            simplify = [s["id"] for s in full["loop"]["work"]].index("simplify")
            full["loop"]["work"][simplify]["skills"] = ["deep-clean-code"]
            _, written, problems = config.save("user", full, saved={}, skills={"deep-clean-code": "/x"})
            self.assertEqual(problems, [])
            self.assertEqual(written, {"loop": {"work": [{"id": "simplify", "skills": ["deep-clean-code"]}]}})
            self.assertEqual(config.load()["loop"]["work"][simplify]["does"],
                             config.standard()["loop"]["work"][simplify]["does"])
        finally:
            home.close()


class Tiers(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_standard_tiers_give_every_checking_role_another_model(self):
        cfg = config.load()
        self.assertEqual(cfg["tiers"], {"low": ["haiku"], "mid": ["sonnet"], "high": ["opus", "sonnet"]})
        self.assertNotIn("fable", json.dumps(cfg["tiers"]))
        self.assertEqual(config.candidate_problems(cfg), [])

    def test_role_tier(self):
        self.assertEqual(config.role_tier("low"), "low")
        self.assertEqual(config.role_tier("low", "redteam"), "mid")
        self.assertEqual(config.role_tier("mid", "qa"), "high")
        self.assertEqual(config.role_tier("high", "redteam"), "high")
        self.assertEqual(config.role_tier("mid", "pair"), "mid")
        with self.assertRaises(ValueError):
            config.role_tier("huge")

    def test_role_candidates_never_the_lead_and_never_lower(self):
        cfg = config.load()
        self.assertEqual(config.lead_profile(cfg, "high"), "opus")
        self.assertEqual(config.role_candidates(cfg, "low", "pair"), ["sonnet", "opus"])
        self.assertEqual(config.role_candidates(cfg, "mid", "redteam"), ["opus"])
        self.assertEqual(config.role_candidates(cfg, "high", "qa"), ["sonnet"])
        self.assertEqual(config.role_candidates(cfg, "high", "qa", lead="sonnet"), ["opus"])  # the lead fell back
        lone = config.merge(cfg, {"tiers": {"high": ["opus"]}})
        self.assertEqual(config.role_candidates(lone, "high", "pair"), [])
        problems = config.validate(lone)
        for role in ("pair", "redteam", "qa"):  # the verification session's roles too
            self.assertTrue(any(f"at high difficulty, role {role} has no profile other than the lead's (opus)" in p
                                for p in problems), role)

    def test_order_and_fallback(self):
        cfg = config.merge(config.load(), {"tiers": {"mid": ["sonnet", "haiku"]}})
        self.assertEqual(config.tier_profiles(cfg, "mid"), ["sonnet", "haiku"])
        self.assertEqual(config.tier_profiles(cfg, "mid", skip=["sonnet"]), ["haiku"])

    def test_tier_problems(self):
        cfg = config.load()
        p = config.validate(config.merge(cfg, {"tiers": {"huge": ["opus"], "mid": [], "high": ["ghost"]}}))
        self.assertTrue(any("unknown tier 'huge'" in x for x in p))
        self.assertIn("tiers: mid must list at least one profile", p)
        self.assertIn("tiers: high names profile 'ghost', which does not exist", p)

    def test_tier_cli(self):
        r = run("config.py", "tier", "--difficulty", "mid", "--role", "redteam")
        self.assertEqual(json.loads(r.stdout), {"tier": "high", "profiles": ["opus"], "pick": "opus"})
        r = run("config.py", "tier", "--difficulty", "mid", "--role", "redteam", "--skip", "opus")
        self.assertEqual(r.returncode, 3)
        r = run("config.py", "tier", "--difficulty", "high")
        self.assertEqual(json.loads(r.stdout)["pick"], "opus")
        r = run("config.py", "tier", "--difficulty", "high", "--role", "pair", "--lead", "sonnet")
        self.assertEqual(json.loads(r.stdout)["profiles"], ["opus"])
        self.assertEqual(run("config.py", "tier").returncode, 2)


class Save(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_user_save_stores_only_differences_and_repeats(self):
        full = config.merge(config.standard(), {"ops": {"batch": 3}})
        path, written, problems = config.save("user", full, saved=MACHINES, skills={})
        self.assertEqual(problems, [])
        self.assertEqual(written, {"ops": {"batch": 3}})
        with open(path) as f:
            first = f.read()
        config.save("user", full, saved=MACHINES, skills={})
        with open(path) as f:
            self.assertEqual(f.read(), first)

    def test_invalid_save_writes_nothing(self):
        full = config.merge(config.standard(), {"ops": {"batch": -1}})
        path, _, problems = config.save("user", full, saved=MACHINES, skills={})
        self.assertTrue(problems)
        self.assertFalse(os.path.exists(path))

    def test_project_save_leaves_out_user_values(self):
        self.home.write("config/agent-foreman/config.json", {"ops": {"batch": 3}})
        full = config.merge(config.load(), {"machines": {"m1": "/src/r"}, "labels": {"default": "{task}"}})
        _, written, problems = config.save("project", full, repo="o/r", saved=MACHINES, skills={})
        self.assertEqual(problems, [])
        self.assertEqual(written, {"machines": {"m1": "/src/r"}, "labels": {"default": "{task}"}, "repo": "o/r"})
        self.assertEqual(config.load("o/r")["ops"]["batch"], 3)

    def test_dry_run_writes_nothing(self):
        full = config.merge(config.standard(), {"ops": {"batch": 3}})
        path, _, problems = config.save("user", full, saved=MACHINES, skills={}, dry_run=True)
        self.assertEqual(problems, [])
        self.assertFalse(os.path.exists(path))


class SaveAStep(unittest.TestCase):
    """A new step is checked where the saved file puts it."""

    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_a_step_out_of_place_is_refused_and_one_in_place_is_saved(self):
        lint = {"id": "lint", "stage": "build", "actor": "lead", "does": "Run the linter.", "skills": [],
                "next": {"done": "verify"}}
        full = config.load()
        full["loop"]["work"].append({**lint, "after": "build"})  # at the end, though it says after build
        _, _, problems = config.save("user", full, dry_run=True)
        self.assertTrue(any("its steps must come one after another" in p for p in problems), problems)
        full = config.load()
        work = full["loop"]["work"]
        work.insert([s["id"] for s in work].index("build") + 1, lint)
        _, written, problems = config.save("user", full)
        self.assertEqual(problems, [])
        self.assertEqual([s for s in written["loop"]["work"] if s["id"] == "lint"][0]["after"], "build")
        self.assertEqual([s["id"] for s in config.load()["loop"]["work"]][:4], ["plan", "plan-check", "build", "lint"])


class Skills(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_plugin_and_user_skills_without_broken_links(self):
        self.home.write("plug/skills/tidy/SKILL.md", "x")
        self.home.write("plug/skills/notaskill/README.md", "x")
        self.home.write("off/skills/hidden/SKILL.md", "x")
        self.home.write("user/real/SKILL.md", "x")
        user = os.path.join(self.home.root, "user")
        os.symlink(os.path.join(self.home.root, "nowhere"), os.path.join(user, "broken"))
        plugins = [{"id": "plug@m", "enabled": True, "installPath": os.path.join(self.home.root, "plug")},
                   {"id": "off@m", "enabled": False, "installPath": os.path.join(self.home.root, "off")}]
        found = config.local_skills(plugins=plugins, user_skills_dir=user)
        self.assertEqual(sorted(found), ["plug:tidy", "real"])

    def test_single_skill_plugin(self):
        self.home.write("solo/SKILL.md", "---\nname: solo\n---\n")
        plugins = [{"id": "solo@m", "enabled": True, "installPath": os.path.join(self.home.root, "solo")}]
        found = config.local_skills(plugins, user_skills_dir=os.path.join(self.home.root, "none"))
        self.assertEqual(found, {"solo:solo": os.path.join(self.home.root, "solo")})

    def test_agent_foreman_as_a_user_skill_is_left_out(self):
        user = os.path.join(self.home.root, "user-skills")
        os.makedirs(user)
        os.symlink(config.SELF_DIR, os.path.join(user, "agent-foreman"))
        os.symlink(config.SELF_DIR, os.path.join(user, "foreman-link"))
        self.home.write("user-skills/real/SKILL.md", "x")
        self.assertEqual(list(config.local_skills([], user_skills_dir=user)), ["real"])

    def test_agent_foreman_is_never_a_candidate_or_a_skill(self):
        other = os.path.dirname(os.path.dirname(self.home.write("other/.claude-plugin/plugin.json", {"name": "other"})))
        self.home.write("other/skills/tidy/SKILL.md", "x")
        copy = os.path.dirname(os.path.dirname(self.home.write("copy/.claude-plugin/plugin.json",
                                                               {"name": "agent-foreman"})))
        argv = ["claude", "--plugin-dir", other, f"--plugin-dir={config.SELF_DIR}", "--plugin-dir", copy,
                "--plugin-dir", "/no/such/dir", "--model", "x"]
        self.assertEqual(config.session_plugin_dirs(argv), [other])
        plugins = [{"id": "other@inline", "enabled": True, "installPath": other},
                   {"id": "agent-foreman@ragingwind-agent-skills", "enabled": True, "installPath": config.SELF_DIR}]
        found = config.local_skills(plugins, user_skills_dir=os.path.join(self.home.root, "none"))
        self.assertEqual(list(found), ["other:tidy"])
        p = config.validate(config.merge(config.load(), {"plugin_dirs": [config.SELF_DIR, copy]}))
        self.assertEqual(sum("is agent-foreman itself" in x for x in p), 2)

    def test_plugin_dirs_go_to_claude_plugin_list(self):
        listing = mock.Mock(stdout="[]")
        with mock.patch.object(config.subprocess, "run", return_value=listing) as fake:
            config.plugin_list(["/a", "~/b"])
        self.assertEqual(fake.call_args[0][0], ["claude", "--plugin-dir", "/a", "--plugin-dir",
                                                os.path.expanduser("~/b"), "plugin", "list", "--json"])

    def test_plugin_dirs_settings(self):
        plug = os.path.dirname(os.path.dirname(self.home.write("plug/.claude-plugin/plugin.json", {"name": "plug"})))
        cfg = config.load()
        self.assertEqual(config.validate(config.merge(cfg, {"plugin_dirs": [plug]})), [])
        p = config.validate(config.merge(cfg, {"plugin_dirs": [self.home.root, "/no/such/dir"]}))
        self.assertIn(f"plugin_dirs: {self.home.root} has no .claude-plugin/plugin.json", p)
        self.assertIn("plugin_dirs: /no/such/dir has no .claude-plugin/plugin.json", p)
        self.assertIn("plugin_dirs must be a list of directory paths",
                      config.validate(config.merge(cfg, {"plugin_dirs": "/a"})))
        self.assertEqual(config.plugin_dirs({"plugin_dirs": [plug, "/no/such/dir"]}), [plug])

    def test_whole_plugins_are_the_plugin_dirs_ones(self):
        flow = os.path.dirname(os.path.dirname(self.home.write("flow/.claude-plugin/plugin.json", {"name": "flow"})))
        other = os.path.dirname(os.path.dirname(self.home.write("other/.claude-plugin/plugin.json", {"name": "o"})))
        self.home.write("flow/skills/impl/SKILL.md", "x")
        self.home.write("other/skills/tidy/SKILL.md", "x")
        self.home.write("market/skills/ship/SKILL.md", "x")
        plugins = [{"id": "flow@inline", "scope": "session", "enabled": True, "installPath": flow},
                   {"id": "other@inline", "scope": "session", "enabled": True, "installPath": other},
                   {"id": "market@m", "scope": "user", "enabled": True,
                    "installPath": os.path.join(self.home.root, "market")}]
        cfg = config.merge(config.load(), {"plugin_dirs": [flow, other],
                                           "loop": {"work": [{"id": "build", "skills": ["tdd", "impl", "ship"]}]}})
        self.assertEqual(config.whole_plugins(cfg, plugins), {"flow": flow, "other": other})
        self.assertEqual(config.whole_plugins(cfg, plugins[2:]), {})  # an installed plugin is not loaded whole

    def test_plugins_installed_for_another_folder_are_candidates(self):
        plugins = [{"id": "flow@market", "enabled": False, "scope": "project", "installPath": "/cache/flow"},
                   {"id": "pstack@market", "enabled": True, "scope": "user", "installPath": "/cache/pstack"},
                   {"id": "pstack@old", "enabled": False, "scope": "user", "installPath": "/cache/old-pstack"},
                   {"id": "agent-foreman@x", "enabled": False, "installPath": config.SELF_DIR}]
        self.assertEqual(config.installed_elsewhere(plugins), [("flow@market", "/cache/flow")])

    def test_project_skills_order_without_repeats(self):
        cfg = {"bundle": {"skills": ["a"]}, "loop": {"work": [{"skills": ["b", "a"]}], "check": [{"skills": ["d"]}]}}
        self.assertEqual(config.project_skills(cfg, ["c", "b"]), ["a", "b", "d", "c"])

    def test_default_skill_replacements(self):
        cfg = config.load()
        self.assertEqual(config.validate(config.merge(cfg, {"skills": {"cross-check": "scenario"}})), [])
        p = config.validate(config.merge(cfg, {"skills": {"ghost": "x", "smoke": " "}}))
        self.assertIn("skills: 'ghost' is not a default skill", "\n".join(p))
        self.assertIn("skills: smoke must name the skill that replaces it", p)
        self.assertIn("skills must map", "\n".join(config.validate(config.merge(cfg, {"skills": ["x"]}))))


class Labels(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.cfg = config.load()

    def tearDown(self):
        self.home.close()

    def test_default_and_event_labels(self):
        self.assertEqual(config.label(self.cfg, "review", task="634", stage="review 2"), "634 review 2")
        self.assertEqual(config.label(self.cfg, "blocked", task="634"), "634 blocked")


class Cli(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_bad_project_name(self):
        r = run("config.py", "show", "--project", "not-a-repo")
        self.assertEqual(r.returncode, 2)

    def test_tier_refuses_an_unknown_role(self):
        r = run("config.py", "tier", "--difficulty", "mid", "--role", "red-team")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--role must be one of lead, pair, redteam, qa", r.stderr)

    def test_no_herdr_says_so(self):
        import shutil, sys
        path = os.pathsep.join([os.path.dirname(sys.executable), "/usr/bin", "/bin"])
        if shutil.which("herdr", path=path):
            self.skipTest("herdr is on the bare PATH")
        r = run("config.py", "machines", env={"PATH": path})
        self.assertEqual(r.returncode, 3)
        self.assertIn("herdr is not on PATH", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_cleanup_removes_the_clones_before_the_branch(self):
        steps = config.standard()["ops"]["after_merge"]
        remove = next(i for i, s in enumerate(steps) if "clone.py remove" in s)
        branch = next(i for i, s in enumerate(steps) if "refs/heads" in s)
        self.assertLess(remove, branch)  # clone.py remove refuses a clone whose commits are on no remote

    def test_paths_and_show(self):
        r = run("config.py", "paths", "--project", "o/r")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(json.loads(r.stdout)["ledger"].endswith("projects/o-r/ledger.md"))
        r = run("config.py", "show")
        self.assertEqual(json.loads(r.stdout)["launch"]["permission"], "bypass")

    def test_save_needs_level(self):
        self.assertEqual(run("config.py", "save", stdin="{}").returncode, 2)
        self.assertEqual(run("config.py", "save", "project", stdin="{}").returncode, 2)
        self.assertEqual(run("config.py", "save", "everyone", stdin="{}").returncode, 2)

    def fake_claude(self, plugins_from_args=True):
        """A `claude` on PATH whose `plugin list --json` reports each --plugin-dir."""
        bindir = os.path.join(self.home.root, "bin")
        os.makedirs(bindir, exist_ok=True)
        path = os.path.join(bindir, "claude")
        with open(path, "w") as f:
            f.write("#!/usr/bin/env python3\nimport json, os, sys\na = sys.argv[1:]\n"
                    "dirs = [a[i + 1] for i, x in enumerate(a) if x == '--plugin-dir']\n"
                    "print(json.dumps([{'id': os.path.basename(d) + '@inline', 'scope': 'session', 'enabled': True,"
                    " 'installPath': d} for d in dirs]))\n")
        os.chmod(path, 0o755)
        gh = os.path.join(bindir, "gh")  # the machine check looks for it on PATH
        with open(gh, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(gh, 0o755)
        return {"PATH": bindir + os.pathsep + os.environ["PATH"], "CLAUDE_CONFIG_DIR": os.path.join(self.home.root, "cc")}

    def test_check_machine_local(self):
        repo = os.path.join(self.home.root, "repo")
        subprocess.run(["git", "init", "-q", repo], check=True)
        subprocess.run(["git", "-C", repo, "remote", "add", "origin", "git@github.com:o/r.git"], check=True)
        self.home.write("config/agent-foreman/providers.json",
                        providers({"id": "tf", "base_url": "https://tf.example", "auth": "bearer",
                                   "token_env": "HF_TEST_TF_TOKEN", "models": [{"id": "m-1", "name": "tf-m",
                                                                                "context": 1000}]},
                                  tiers={"low": ["tf-m", "haiku"], "mid": ["sonnet"], "high": ["opus", "sonnet"]}))
        env = {**self.fake_claude(), "HF_TEST_TF_TOKEN": "secret-value-xyz"}
        r = run("config.py", "check-machine", "local", repo, "--project", "o/r", env=env)
        state = json.loads(r.stdout)
        self.assertEqual((r.returncode, state["ready"], state["problems"]), (0, True, []), r.stderr)
        self.assertEqual(state["tokens"], {"HF_TEST_TF_TOKEN": True})
        self.assertNotIn("secret-value-xyz", r.stdout + r.stderr)
        r = run("config.py", "check-machine", "local", repo, "--project", "o/other", env={**env, "HF_TEST_TF_TOKEN": ""})
        problems = json.loads(r.stdout)["problems"]
        self.assertEqual(r.returncode, 3)
        self.assertIn("the checkout's origin is git@github.com:o/r.git, not o/other", problems)
        self.assertIn("token variable HF_TEST_TF_TOKEN is not set in the login shell", problems)
        r = run("config.py", "check-machine", "local", os.path.join(self.home.root, "nope"), "--project", "o/r", env=env)
        self.assertEqual(json.loads(r.stdout)["problems"][0], f"no git checkout at {os.path.join(self.home.root, 'nope')}")
        self.assertEqual(run("config.py", "check-machine", "local", repo).returncode, 2)

    def test_plugin_dir_candidates_are_bare_paths(self):
        with mock.patch.object(config, "session_plugin_dirs", return_value=["/p/kit"]), \
                mock.patch.object(config, "installed_elsewhere", return_value=[("flow@m", "/cache/flow/1.0")]), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out, \
                mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(config._cli(["plugin-dir-candidates"]), 0)
        self.assertEqual(out.getvalue().splitlines(), ["/p/kit", "/cache/flow/1.0"])  # each one fits --plugin-dir
        self.assertIn("flow@m, installed but not enabled here", err.getvalue())

    def test_skills_with_an_unsaved_plugin_dir(self):
        plugin = os.path.join(self.home.root, "kit")
        self.home.write("kit/.claude-plugin/plugin.json", {"name": "kit"})
        self.home.write("kit/skills/tidy/SKILL.md", "---\nname: tidy\n---\n")
        env = self.fake_claude()
        self.assertNotIn("kit:tidy", run("config.py", "skills", env=env).stdout)
        r = run("config.py", "skills", "--plugin-dir", plugin, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("kit:tidy", r.stdout)
        self.assertFalse(os.path.exists(config.user_path()))  # nothing saved


if __name__ == "__main__":
    unittest.main()
