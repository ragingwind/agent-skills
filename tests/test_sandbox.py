"""fixture/sandbox.py: a GitHub sandbox for a live run, made and deleted
through `gh`. A fake `gh` keeps the repositories in a state file."""
import json
import os
import re
import unittest

from helpers import ROOT, TempHome, run

FIXTURE = os.path.join(ROOT, "fixture")
DESCRIPTION = "agent-foreman sandbox, made by fixture/sandbox.py; safe to delete"

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
path = os.environ["FAKE_GH"]
with open(path) as f:
    st = json.load(f)
args = sys.argv[1:]
st["calls"].append(args)

def opt(name):
    return args[args.index(name) + 1]

def save():
    with open(path, "w") as f:
        json.dump(st, f)

if args[:2] == ["api", "user"]:
    print(st["login"])
elif args[:2] == ["repo", "create"]:
    def git(*a):
        return subprocess.run(["git", "-C", opt("--source"), *a], capture_output=True, text=True).stdout.splitlines()
    st["repos"][args[2]] = {"name": args[2].split("/")[1], "description": opt("--description"),
                            "private": "--private" in args, "files": git("ls-files"),
                            "commits": git("log", "--format=%s", "main"), "issues": []}
elif args[:2] == ["issue", "create"]:
    if st.get("fail_issue"):
        print("HTTP 502: Bad Gateway", file=sys.stderr)
        save()
        sys.exit(1)
    repo = st["repos"][opt("--repo")]
    repo["issues"].append({"title": opt("--title"), "body": opt("--body")})
    print(f"https://github.com/{opt('--repo')}/issues/{len(repo['issues'])}")
elif args[:2] == ["repo", "view"]:
    if args[2] not in st["repos"]:
        print(f"GraphQL: Could not resolve to a Repository with the name '{args[2]}'.", file=sys.stderr)
        save()
        sys.exit(1)
    r = st["repos"][args[2]]
    print(json.dumps({"name": r["name"], "description": r["description"]}))
elif args[:2] == ["repo", "delete"]:
    if st.get("no_scope"):
        print('HTTP 403: Must have admin rights to Repository. This API operation needs the "delete_repo" scope.',
              file=sys.stderr)
        save()
        sys.exit(1)
    del st["repos"][args[2]]
elif args[:2] == ["repo", "list"]:
    print(json.dumps([{"nameWithOwner": k, "name": v["name"], "description": v["description"],
                       "visibility": "PRIVATE" if v["private"] else "PUBLIC", "createdAt": "2026-11-23T00:00:00Z"}
                      for k, v in st["repos"].items() if k.split("/")[0] == args[2]]))
else:
    print("fake gh: unsupported " + " ".join(args), file=sys.stderr)
    save()
    sys.exit(2)
save()
'''


def titles():
    out = []
    for n in sorted(os.listdir(os.path.join(FIXTURE, "tasks"))):
        with open(os.path.join(FIXTURE, "tasks", n), encoding="utf-8") as f:
            out.append(f.readline()[2:].strip())
    return out


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        bin_dir = os.path.join(self.home.root, "bin")
        self.home.write("bin/gh", FAKE_GH)
        os.chmod(os.path.join(bin_dir, "gh"), 0o755)
        self.state = os.path.join(self.home.root, "gh.json")
        self.env = {"PATH": bin_dir + os.pathsep + os.environ["PATH"], "FAKE_GH": self.state,
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        self.put({"login": "me", "repos": {}, "calls": []})

    def tearDown(self):
        self.home.close()

    def put(self, st):
        with open(self.state, "w") as f:
            json.dump(st, f)

    def st(self):
        with open(self.state) as f:
            return json.load(f)

    def sandbox(self, *args):
        return run("sandbox.py", *args, env=self.env, cwd=FIXTURE)

    def repo(self, name, description=DESCRIPTION):
        return {"name": name.split("/")[1], "description": description, "private": True, "files": [], "commits": [],
                "issues": []}

    def test_create_pushes_the_fixture_project_and_opens_the_tasks(self):
        r = self.sandbox("create")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertRegex(out["repo"], r"^me/agent-foreman-sandbox-\d{8}-\d{6}$")
        self.assertEqual(out["delete"], f"python3 fixture/sandbox.py delete {out['repo']}")
        self.assertEqual(out["clone"], f"gh repo clone {out['repo']}")
        made = self.st()["repos"][out["repo"]]
        self.assertTrue(made["private"])
        self.assertEqual(made["description"], DESCRIPTION)
        self.assertEqual(made["commits"], ["Start the stock project"])
        self.assertIn(".github/workflows/ci.yml", made["files"])
        self.assertIn("CLAUDE.md", made["files"])
        self.assertIn("Makefile", made["files"])
        self.assertFalse([f for f in made["files"] if "dot-" in f or ".fixture" in f or f.endswith(".pyc")])
        self.assertEqual([i["title"] for i in made["issues"]], titles())
        self.assertTrue(made["issues"][0]["body"].startswith("## Goal"))
        self.assertEqual([(i["task"], i["number"], i["title"]) for i in out["issues"]],
                         [(str(n), n, t) for n, t in enumerate(titles(), 1)])

    def test_create_for_an_organization_asks_no_login(self):
        r = self.sandbox("create", "--owner", "some-org")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["repo"].startswith("some-org/agent-foreman-sandbox-"))
        self.assertNotIn(["api", "user", "--jq", ".login"], self.st()["calls"])

    def test_create_names_the_delete_command_when_an_issue_fails(self):
        self.put({"login": "me", "repos": {}, "calls": [], "fail_issue": True})
        r = self.sandbox("create")
        self.assertEqual(r.returncode, 1)
        repo = next(iter(self.st()["repos"]))
        self.assertIn("HTTP 502", r.stderr)
        self.assertIn(f"python3 fixture/sandbox.py delete {repo}", r.stderr)

    def test_list_shows_only_sandboxes(self):
        repos = {"me/agent-foreman-sandbox-20261123-010203": self.repo("me/agent-foreman-sandbox-20261123-010203"),
                 "me/agent-foreman-sandbox": self.repo("me/agent-foreman-sandbox", "Sandbox for tests"),
                 "me/agent-foreman-sandbox-x": self.repo("me/agent-foreman-sandbox-x", "my own"),
                 "me/tool": self.repo("me/tool")}
        self.put({"login": "me", "repos": repos, "calls": []})
        r = self.sandbox("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([x["repo"] for x in json.loads(r.stdout)], ["me/agent-foreman-sandbox-20261123-010203"])

    def test_delete_removes_a_sandbox(self):
        name = "me/agent-foreman-sandbox-20261123-010203"
        self.put({"login": "me", "repos": {name: self.repo(name)}, "calls": []})
        r = self.sandbox("delete", name)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"repo": name, "deleted": True})
        self.assertIn(["repo", "delete", name, "--yes"], self.st()["calls"])
        self.assertEqual(self.st()["repos"], {})

    def test_delete_refuses_any_other_repository(self):
        repos = {"me/agent-foreman-sandbox": self.repo("me/agent-foreman-sandbox", "Sandbox for tests"),
                 "me/agent-foreman-sandbox-x": self.repo("me/agent-foreman-sandbox-x", "my own"),
                 "me/tool": self.repo("me/tool")}
        self.put({"login": "me", "repos": repos, "calls": []})
        for name in repos:
            r = self.sandbox("delete", name)
            self.assertEqual(r.returncode, 1, name)
            self.assertIn("is not a sandbox this script made", r.stderr)
        self.assertFalse([c for c in self.st()["calls"] if c[:2] == ["repo", "delete"]])
        self.assertEqual(sorted(self.st()["repos"]), sorted(repos))
        r = self.sandbox("delete", "me/missing")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Could not resolve", r.stderr)

    def test_delete_without_the_scope_says_how_to_get_it(self):
        name = "me/agent-foreman-sandbox-20261123-010203"
        self.put({"login": "me", "repos": {name: self.repo(name)}, "calls": [], "no_scope": True})
        r = self.sandbox("delete", name)
        self.assertEqual(r.returncode, 1)
        self.assertIn("gh auth refresh -h github.com -s delete_repo", r.stderr)
        self.assertIn(name, self.st()["repos"])

    def test_bad_arguments(self):
        for args in (["delete"], ["delete", "noslash"], ["delete", "me/x y"], ["create", "me/x"], ["list", "me/x"],
                     ["delete", "me/agent-foreman-sandbox-1", "--owner", "me"], ["create", "--owner", "-bad"],
                     ["create", "--owner", "a/b"], ["remove"]):
            r = self.sandbox(*args)
            self.assertEqual(r.returncode, 2, args)
        self.assertEqual(self.st()["calls"], [])


if __name__ == "__main__":
    unittest.main()
