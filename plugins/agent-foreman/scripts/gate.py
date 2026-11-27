#!/usr/bin/env python3
"""A task's pass conditions, as code: the foreman writes the gate file, the
lead runs it before it reports ready, and the foreman runs it again before
it merges.

Usage:
  gate.py template --loop LOOP.json [--pr N]
  gate.py hash GATE.json
  gate.py run GATE.json [--pr N] [--cwd CLONE] [--task-dir DIR] [--skip CHECK,...] [--before-ready] [--sha HEX]
  gate.py record --step ID --task-dir DIR [--cwd CLONE]

`record` checks one step's evidence when it ends, before the task goes on:
the evidence its `end` line gives (--done), and the record each of its
default skills must leave (a replaced one by the default its brief names
under "flow and record"):
  work-breakdown  plan.md's work breakdown, with test, status and commit
                  columns and at least one row
  cross-check     in a step with work-breakdown: scenario.md with numbered
                  steps and their Expect lines (not for a trivial task);
                  elsewhere: scenario.md's Agent blocks filled, its
                  closing verdict, and the verdict of its last addendum
                  (a later round's rerun of some steps), if any
  tdd, commit     every row done, with a commit that is in the clone (--cwd)
                  and in HEAD's history
  unit            outside the build: a "Tests near the change" entry under
                  plan.md's Checks
  smoke           a "Smoke" entry under plan.md's Checks
  handoff         handoff.md with its sections
  a role's step   the role's latest answer in reviews/, run to the end, with
                  a Verdict
The other default skills (simplify) have only the evidence line. It prints
one JSON object, and exits 0 when every record is there, 6 when one is not.

A gate file:
  {"repo": "owner/name", "pr": 12, "checks": [{"check": "<name>", ...}, ...]}

`template` builds the standard gate from the task's `loop.json` (`loop.py
render --json`), so the gate and the loop come from one place. The foreman
writes it with the brief, before the pull request exists, so "pr" may be
null; `run --pr N` names the pull request then. A file that names one and a
different --pr is refused.

The lead can write in its task folder, so the foreman records the gate
file's `hash` with the brief and passes it to every run it makes with --sha:
a changed gate file blocks. The `loop-file` check does the same for
`loop.json`, whose hash the template writes into the gate file.

Checks (each may say "severity": "warn" to report without blocking):
  pr-open         the pull request exists and is open
  loop-file       the task folder's loop.json has the "sha256" in the check
  steps           the task folder's status.jsonl has an `end` line for each
                  step in "ids" (status.py note)
  docs            the task folder's records: every row of plan.md's work
                  breakdown is done, handoff.md has its sections, and
                  scenario.md's closing verdict is pass with every Agent block
                  filled, and so is its last addendum's (not for a trivial
                  task)
  ci              every status check finished and passed
  base-fresh      the head contains the base branch's head
  verdict         an agent of "role" whose latest answer in the
                  task folder's reviews/ (launch.py --role) ends with a
                  `Verdict:` in "accept", given at the head SHA (with --cwd,
                  also at an earlier SHA whose change is the same), on a
                  profile not in "not_profiles" (the lead's). With "posted":
                  true, that answer also counts only when a comment on the
                  pull request holds it whole, as `loop.py post` writes it
  tests-weakened  no removed test file, added skip marker, edited CI file,
                  changed coverage threshold or edited agent instructions
                  (`.claude/`, `CLAUDE.md`, `AGENTS.md`), except the kinds in
                  "allow" (removed-test, skip-marker, ci-edit, coverage,
                  agent-files)
  size            added lines at most "max_lines": the pull request's
                  additions, without lockfiles (LOCKFILES) and without the
                  files that the base commit's .gitattributes mark
                  `linguist-generated` (with --cwd); its severity comes from
                  the task's loop.json ("size_severity", "warn" for a task
                  from before it)
  ready           the pull request is no longer a draft
  command         "run" exits 0 in the clone (--cwd); it gets AF_REPO, AF_PR,
                  AF_TASK, AF_TASK_DIR, AF_BASE, AF_BASE_SHA (the base
                  branch's head on GitHub) and AF_HEAD in its environment.
                  Its whole output, stdout and stderr in the order written,
                  goes to a log file: with --task-dir in the task folder's
                  gate-logs/, else in the temporary directory. The evidence
                  holds the last three lines and the log's path, so a
                  failure can be read in full and only the failing tests
                  run again.
                  With "from_base": PATH instead of "run", the gate takes the
                  script at PATH from AF_BASE_SHA itself (fetched from origin
                  when the clone lacks it) and runs that: the lead's own
                  copy, and its refs, do not count; a script it cannot get
                  blocks

A project's own checks (`gate` in its settings, carried in loop.json) are
command checks with a "name", appended by `template`; the name stands for the
check in the report and in --skip. An unnamed command check is the project's
full tests (`tests.full`), named `command`. It has "full": true and runs
through fulltest.py: one full test run at a time on the machine, and none
when the disk has less than "min_free_gb" free (exit 75, `fulltest.py: not
run`). Its "answer" holds a verdict check's terms (role, accept,
not_profiles, posted), the role whose check-loop step runs the `full` skill
(QA): when that role's latest answer passes those terms at the exact head
SHA and lists `- ran: <run> — exit 0` (also as fulltest.py runs it, the way
QA's prompt names it), the check passes without running the command again,
and its evidence names the answer file. Forging it takes
what forging that role's verdict check takes.

--before-ready skips `ready` and every check marked "at": "merge": the lead
runs the gate before the verification session. --skip names checks to leave
out; a verdict check is named with its role, `verdict:qa`, and only when the
person said so.

`run` prints one JSON object and exits 0 when nothing blocks, 6 when a check
blocks, 2 on bad arguments, 1 when gh or git fails. With --task-dir it also
appends the result's summary to the task folder's gates.jsonl, for the retro;
the lead can write there too, so nothing trusts it as proof of a pass.
"""
import argparse
import fnmatch
import glob
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time

EXIT_GATE_FAILED = 6
TEST_PATHS = ["**/tests/**", "**/test/**", "**/__tests__/**", "**/*_test.*", "**/test_*.*", "**/*.test.*",
              "**/*.spec.*", "**/spec/**"]
CI_PATHS = ["**/.github/workflows/**", "**/.gitlab-ci.yml", "**/Jenkinsfile", "**/.circleci/**",
            "**/azure-pipelines.yml"]
AGENT_PATHS = ["**/.claude/**", "**/CLAUDE.md", "**/CLAUDE.local.md", "**/AGENTS.md"]
# A package manager writes these; the size budget counts the lines a person writes (loop-rules.md rule 6).
LOCKFILES = ["*.lock", "package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "go.sum", "bun.lockb",
             "packages.lock.json", "gradle.lockfile"]
RAN = re.compile(r"^-\s+ran:\s+`?(.+?)`?\s+[—–-]+\s+exit\s+0\s*$")
SKIP_MARKERS = re.compile(r"@pytest\.mark\.(skip|xfail)|\b(it|test|describe)\.skip\(|\bx(it|describe)\(|"
                          r"\bt\.Skip(Now|f)?\(|@Ignore\b|@Disabled\b|#\[ignore\]|unittest\.skip|\.only\(")
COVERAGE = re.compile(r"fail_under|fail-under|cov-fail-under|coverageThreshold|min(imum)?_coverage", re.I)
PASSED = {"SUCCESS", "NEUTRAL", "SKIPPED"}
HANDOFF_SECTIONS = ("Purpose", "Decisions", "Tests", "Not touched", "Follow-ups")
VERDICT = re.compile(r"^Verdict:\s*([A-Za-z][\w-]*)\W*$", re.I)
CHECK_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PROJECT_CHECK_KEYS = {"check", "name", "run", "from_base", "severity", "at"}
FULLTEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fulltest.py")


def matches(path, pattern):
    pat = pattern[3:] if pattern.startswith("**/") else pattern
    return fnmatch.fnmatch("/" + path, "*/" + pat) or fnmatch.fnmatch(path, pat)


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def last_verdict(text):
    """The word on the answer's last `Verdict:` line, lower case, or "". Bold,
    backticks or a period around the line do not count against it."""
    found = ""
    for line in str(text or "").splitlines():
        m = VERDICT.match(line.strip().strip("*_`> ").strip())
        if m:
            found = m.group(1).lower()
    return found


def answer_comment(role, agent, number, meta, text):
    """The pull request comment that holds a saved answer whole: `loop.py post` writes it, and a verdict check
    with "posted" looks for it."""
    head = meta.get("head") or ""
    return (f"## {role} answer by {agent} on #{number} at {head[:7]}\n\n{str(text).strip()}\n\n---\n"
            f"{agent} ran on {meta.get('profile')} ({meta.get('model')}) at {head}, and ended at "
            f"{meta.get('ended')}. The answer is saved in the task folder's reviews/, session "
            f"{meta.get('session_id')}.\n")


def same_body(a, b):
    """Two comment bodies are the same text, line endings and trailing spaces aside."""
    def norm(t):
        return "\n".join(line.rstrip() for line in str(t).replace("\r\n", "\n").strip().splitlines())
    return norm(a) == norm(b)


def gh_pages(*args):
    """Every item of a `gh api --paginate` list: gh prints one JSON array per page. RuntimeError when gh fails."""
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} failed: {out.stderr.strip()[:300]}")
    items, i, decoder, text = [], 0, json.JSONDecoder(), out.stdout
    while True:
        while i < len(text) and text[i].isspace():
            i += 1
        if i == len(text):
            return items
        page, i = decoder.raw_decode(text, i)
        items += page if isinstance(page, list) else [page]


def gh_json(*args):
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode != 0:
        print(f"gate.py: gh {' '.join(args[:3])} failed: {out.stderr.strip()[:300]}", file=sys.stderr)
        sys.exit(1)
    return json.loads(out.stdout or "null")


def fetch(repo, pr, comments=False):
    """Everything the checks read about one pull request; its comments too when a check needs them."""
    view = gh_json("pr", "view", str(pr), "--repo", repo, "--json",
                   "number,state,isDraft,baseRefName,baseRefOid,headRefOid,additions,deletions,statusCheckRollup")
    files = gh_json("api", "--paginate", f"repos/{repo}/pulls/{pr}/files?per_page=100")
    compare = gh_json("api", f"repos/{repo}/compare/{view['baseRefName']}...{view['headRefOid']}")
    view["files"] = files
    view["behind_by"] = compare.get("behind_by")
    if comments:
        try:
            view["comments"] = gh_pages("api", "--paginate", f"repos/{repo}/issues/{pr}/comments?per_page=100")
        except RuntimeError as e:
            print(f"gate.py: {e}", file=sys.stderr)
            sys.exit(1)
    return view


def same_sha(a, b):
    a, b = a.lower(), b.lower()
    return len(min(a, b, key=len)) >= 7 and (a.startswith(b) or b.startswith(a))


def same_change(cwd, base, a, b):
    """Whether two commits carry the same change against the base, as after
    a clean rebase: the `git patch-id` of each one's squashed diff from its
    merge base with the base branch, or else the patch-ids of each one's own
    commits, left after dropping those the base branch holds an equal of.
    The second form covers a stack layer whose lower layer was rebased too:
    the old commit's merge base is then below the lower layer's old commits,
    so its squashed diff holds them."""
    def run(*args, stdin=None):
        return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, input=stdin)

    def patch_id(diff):
        pid = run("patch-id", "--stable", stdin=diff.stdout)
        if diff.returncode != 0 or pid.returncode != 0 or not pid.stdout.strip():
            return None
        return pid.stdout.split()[0]

    def squashed(sha):
        mb = run("merge-base", f"origin/{base}", sha)
        return patch_id(run("diff", mb.stdout.strip(), sha)) if mb.returncode == 0 else None

    def own_commits(sha):
        revs = run("rev-list", "--cherry-pick", "--right-only", "--no-merges", "--reverse", f"origin/{base}...{sha}")
        if revs.returncode != 0:
            return None
        ids = [patch_id(run("show", "--pretty=format:", "--patch", rev)) for rev in revs.stdout.split()]
        return ids if ids and None not in ids else None

    for sha in (a, b):
        if run("cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
            run("fetch", "--quiet", "origin", sha)
    first = squashed(a)
    if first is not None and first == squashed(b):
        return True
    mine = own_commits(a)
    return mine is not None and mine == own_commits(b)


def section(body, name):
    """The text under `## name` up to the next `## ` heading, or None."""
    m = re.search(rf"^##\s+{re.escape(name)}\b[^\n]*\n(.*?)(?=^##\s|\Z)", body or "", re.M | re.S | re.I)
    return m.group(1) if m else None


def read_task_file(ctx, name):
    try:
        with open(os.path.join(ctx["task_dir"], name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def check_pr_open(pr, spec, ctx):
    return pr["state"] == "OPEN", f"state {pr['state']}"


def check_loop_file(pr, spec, ctx):
    if not ctx.get("task_dir"):
        return False, "needs --task-dir"
    path = os.path.join(ctx["task_dir"], "loop.json")
    if not os.path.isfile(path):
        return False, "no loop.json in the task folder"
    found = sha256_file(path)
    return found == spec.get("sha256"), ("loop.json is the one in the brief" if found == spec.get("sha256")
                                         else "loop.json changed after the brief")


def check_steps(pr, spec, ctx):
    if not ctx.get("task_dir"):
        return False, "needs --task-dir"
    ended = set()
    for line in (read_task_file(ctx, "status.jsonl") or "").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("event") == "end":
            ended.add(row.get("step"))
    missing = [s for s in spec.get("ids", []) if s not in ended]
    return not missing, (f"no end line for: {', '.join(missing)}" if missing
                         else f"an end line for each of {', '.join(spec.get('ids', []))}")


def table(text, heading):
    """(header, rows) of the first table under `## heading`, each a list of
    cells, or None when there is no such heading."""
    body = section(text, heading)
    if body is None:
        return None
    lines = [l.strip() for l in body.splitlines() if l.strip().startswith("|")]
    cells = [[c.strip() for c in l.strip("|").split("|")] for l in lines]
    return (cells[0], cells[2:]) if len(cells) >= 2 else ([], [])


def plan_problems(plan_text):
    if plan_text is None:
        return ["no plan.md"]
    found = table(plan_text, "Work breakdown")
    if found is None:
        return ["plan.md has no work breakdown"]
    header, rows = found
    names = [h.lower() for h in header]
    if "status" not in names:
        return ["plan.md's work breakdown has no status column"]
    if not rows:
        return ["plan.md's work breakdown is empty"]
    at = names.index("status")
    open_rows, broken = [], []
    for r in rows:
        if len(r) != len(header):
            broken.append(f"{r[0] or '?'} ({len(r)} cells, not {len(header)})")
        elif r[at].lower() != "done":
            open_rows.append(r[0])
    return ([f"work items not done: {', '.join(open_rows)}"] if open_rows else []) + (
        [f"rows that do not fit the header: {', '.join(broken)}"] if broken else [])


def empty_agent_blocks(scenario):
    """How many `**Agent**` blocks hold no output: no fence after the label,
    an empty fence, or a fence that holds only `<...>` placeholders."""
    empty = 0
    for after in scenario.split("**Agent**")[1:]:
        m = re.match(r"\s*```[^\n]*\n(.*?)```", after, re.S)
        if not m or not m.group(1).strip() or re.fullmatch(r"(\s*<[^>\n]*>\s*)+", m.group(1)):
            empty += 1
    return empty


def first_verdict(text):
    """The word of the `Verdict:` line that opens `text`, lower case, or ""."""
    m = re.match(r"Verdict:\s*(\w+)\s*$", (text or "").strip().split("\n", 1)[0].strip(), re.I)
    return m.group(1).lower() if m else ""


def last_addendum(scenario):
    """The text under scenario.md's last `## Addendum` heading (a later round's rerun of some steps), or None."""
    found = re.findall(r"^##\s+Addendum\b[^\n]*\n(.*?)(?=^##\s|\Z)", scenario or "", re.M | re.S)
    return found[-1] if found else None


def check_docs(pr, spec, ctx):
    if not ctx.get("task_dir"):
        return False, "needs --task-dir"
    problems = plan_problems(read_task_file(ctx, "plan.md"))
    handoff = read_task_file(ctx, "handoff.md")
    if handoff is None:
        problems.append("no handoff.md")
    else:
        missing = [n for n in HANDOFF_SECTIONS if section(handoff, n) is None]
        if missing:
            problems.append(f"handoff.md lacks {', '.join(missing)}")
    if not spec.get("trivial"):
        scenario = read_task_file(ctx, "scenario.md")
        addendum = last_addendum(scenario)
        if scenario is None:
            problems.append("no scenario.md")
        elif first_verdict(section(scenario, "Closing")) != "pass":
            problems.append("scenario.md's closing verdict is not pass")
        elif empty_agent_blocks(scenario):
            problems.append(f"scenario.md has {empty_agent_blocks(scenario)} Agent block(s) with no output")
        elif addendum is not None and first_verdict(addendum) != "pass":
            problems.append("scenario.md's last addendum's verdict is not pass")
    return not problems, "; ".join(problems) if problems else "plan, handoff and scenario in order"


def check_ci(pr, spec, ctx):
    bad = []
    for c in pr.get("statusCheckRollup") or []:
        done = c.get("status", "COMPLETED") == "COMPLETED"
        result = c.get("conclusion") or c.get("state")
        if not done or result not in PASSED:
            bad.append(f"{c.get('name') or c.get('context')}: {result or c.get('status')}")
    total = len(pr.get("statusCheckRollup") or [])
    return not bad, "; ".join(bad) if bad else f"{total} check(s) passed"


def check_base_fresh(pr, spec, ctx):
    behind = pr.get("behind_by")
    return behind == 0, f"{behind} commit(s) behind {pr['baseRefName']}"


def latest_answers(task_dir, role):
    """(agent, meta, answer text) of each agent of a role: its latest run in the
    task folder's reviews/ (launch.py --print --role writes `<out>.meta.json`)."""
    return [(agent, meta, text) for agent, meta, _, text in latest_runs(task_dir, role)]


def latest_runs(task_dir, role):
    """latest_answers, with each answer's file after its meta."""
    by_agent = {}
    for meta_file in glob.glob(os.path.join(task_dir, "reviews", "*.meta.json")):
        try:
            with open(meta_file, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict) or meta.get("role") != role:
            continue
        agent = meta.get("agent") or meta_file
        if agent not in by_agent or str(meta.get("ended", "")) > str(by_agent[agent][0].get("ended", "")):
            by_agent[agent] = (meta, meta_file[:-len(".meta.json")] + ".json")
    out = []
    for agent, (meta, answer_file) in sorted(by_agent.items()):
        text = ""
        try:
            with open(answer_file, encoding="utf-8") as f:
                text = str(json.load(f).get("result") or "")
        except (OSError, ValueError, AttributeError):
            pass
        out.append((agent, meta, answer_file, text))
    return out


def accepted_answers(pr, spec, ctx, exact=False):
    """(each accepted answer as (agent, meta, answer file, text), what was
    seen) for a verdict check's terms: the role's latest answers that end with
    a verdict in "accept", at the head, on a profile not in "not_profiles",
    from a run that finished, and on the pull request when "posted". With
    exact, only at the head SHA itself, not at an earlier one whose change is
    the same."""
    accept = [a.lower() for a in spec.get("accept", ["approved"])]
    banned = set(spec.get("not_profiles", []))
    comments = [c.get("body") or "" for c in pr.get("comments") or [] if isinstance(c, dict)]
    good, seen = [], []
    for agent, meta, answer_file, text in latest_runs(ctx["task_dir"], spec["role"]):
        verdict = last_verdict(text)
        head = meta.get("head") or ""
        at_head = bool(head) and (same_sha(head, pr["headRefOid"]) or bool(
            not exact and ctx.get("cwd") and same_change(ctx["cwd"], pr["baseRefName"], head, pr["headRefOid"])))
        posted = not spec.get("posted") or any(
            same_body(c, answer_comment(spec["role"], agent, pr.get("number"), meta, text)) for c in comments)
        if (verdict in accept and at_head and meta.get("profile") not in banned and meta.get("ok") is True
                and posted):
            good.append((agent, meta, answer_file, text))
        seen.append(f"{agent} {meta.get('profile')} {head[:7] or '?'} {verdict or 'no verdict'}"
                    + ("" if meta.get("ok") is True else " (the run failed)")
                    + ("" if meta.get("profile") not in banned else " (the lead's profile)")
                    + ("" if posted else " (not on the pull request as saved)"))
    return good, seen


def check_verdict(pr, spec, ctx):
    if not ctx.get("task_dir"):
        return False, "needs --task-dir"
    good, seen = accepted_answers(pr, spec, ctx)
    return bool(good), (f"{len(good)} accepted {spec['role']} answer(s) at the head; "
                        f"seen: {', '.join(seen) or 'none'}")


def check_tests_weakened(pr, spec, ctx):
    allow = set(spec.get("allow", []))
    found = []
    for f in pr.get("files") or []:
        path, status, patch = f.get("filename", ""), f.get("status", ""), f.get("patch") or ""
        if status == "removed" and any(matches(path, p) for p in TEST_PATHS) and "removed-test" not in allow:
            found.append(f"removed test file {path}")
        if any(matches(path, p) for p in CI_PATHS) and "ci-edit" not in allow:
            found.append(f"edited CI file {path}")
        if any(matches(path, p) for p in AGENT_PATHS) and "agent-files" not in allow:
            found.append(f"edited agent instructions {path}")
        added = [l[1:] for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++")]
        changed = added + [l[1:] for l in patch.splitlines() if l.startswith("-") and not l.startswith("---")]
        if "skip-marker" not in allow and any(SKIP_MARKERS.search(l) for l in added):
            found.append(f"added a skip or focus marker in {path}")
        if "coverage" not in allow and any(COVERAGE.search(l) for l in changed):
            found.append(f"changed a coverage threshold in {path}")
    return not found, "; ".join(found) if found else "none found"


def generated_at_base(cwd, sha, paths):
    """The paths that the base commit's .gitattributes mark
    `linguist-generated`, or None when the clone cannot read them. Only the
    base's attributes count: a fresh git dir that borrows the clone's objects
    reads them, so a change cannot mark its own code as generated, in the
    tree or in the clone's .git/info/attributes or config."""
    if not re.fullmatch(r"[0-9a-f]{7,64}", sha or ""):
        return None
    if subprocess.run(["git", "-C", cwd, "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True).returncode:
        subprocess.run(["git", "-C", cwd, "fetch", "--quiet", "origin", sha], capture_output=True)
    objects = subprocess.run(["git", "-C", cwd, "rev-parse", "--git-path", "objects"], capture_output=True, text=True)
    if objects.returncode != 0:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_INDEX_FILE": os.path.join(tmp, "index")}

        def git(*args, stdin=None):
            return subprocess.run(["git", f"--git-dir={tmp}", *args], capture_output=True, text=True, env=env,
                                  input=stdin)
        git("init", "-q", "--bare", "--template=", tmp)
        with open(os.path.join(tmp, "objects", "info", "alternates"), "w", encoding="utf-8") as f:
            f.write(os.path.abspath(os.path.join(cwd, objects.stdout.strip())) + "\n")
        if git("read-tree", sha).returncode != 0:
            return None
        out = git("check-attr", "--cached", "-z", "--stdin", "linguist-generated", stdin="".join(p + "\0" for p in paths))
    if out.returncode != 0:
        return None
    fields = out.stdout.split("\0")
    return {fields[i] for i in range(0, len(fields) - 2, 3) if fields[i + 2] in ("set", "true")}


def check_size(pr, spec, ctx):
    files = [f for f in pr.get("files") or [] if isinstance(f, dict) and f.get("filename")]
    generated = set()
    if files:
        generated = generated_at_base(ctx["cwd"], pr.get("baseRefOid"), [f["filename"] for f in files]) \
            if ctx.get("cwd") else None
    left_out = [f for f in files if any(matches(f["filename"], p) for p in LOCKFILES)
                or f["filename"] in (generated or ())]
    lines = pr.get("additions", 0) - sum(f.get("additions") or 0 for f in left_out)
    limit = spec.get("max_lines", 400)
    return lines <= limit, (f"{lines} added lines (limit {limit}), without {len(left_out)} lockfile(s) and "
                            f"generated file(s)" + ("" if generated is not None else
                                                    "; the base's linguist-generated files unknown (no --cwd or "
                                                    "no base commit), so all of them counted"))


def check_ready(pr, spec, ctx):
    return not pr.get("isDraft"), "draft" if pr.get("isDraft") else "ready"


def base_script(cwd, sha, path):
    """(script text, None), or (None, why not): PATH as commit SHA has it,
    fetched from origin when the clone lacks the commit."""
    def git(*args):
        return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    if not re.fullmatch(r"[0-9a-f]{7,64}", sha or ""):
        return None, "no base commit from GitHub"
    if git("cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
        git("fetch", "--quiet", "origin", sha)
    shown = git("show", f"{sha}:{path}")
    if shown.returncode != 0:
        return None, f"no {path} at the base {sha[:7]}: {shown.stderr.strip()[:200]}"
    return shown.stdout, None


def record_checks(task_loop, step_id, task_dir, cwd=None):
    """What one step left behind: its `end` line's evidence and the record of
    each of its default skills. Returns the report; "ok" is False when a
    record is missing or wrong."""
    import loop as loops
    steps = [s for w in ("work", "check") for s in task_loop.get(w, [])]
    step = next((s for s in steps if s["id"] == step_id), None)
    if step is None:
        raise ValueError(f"step {step_id!r} is not in this task's loop; its steps are "
                         f"{', '.join(s['id'] for s in steps)}")
    defaults = loops.recorded_defaults(step.get("skills", []))
    ctx = {"task_dir": task_dir, "cwd": cwd}
    ended = [r for r in _jsonl_rows(os.path.join(task_dir, "status.jsonl"))
             if r.get("event") == "end" and r.get("step") == step_id]
    evidence = str(ended[-1].get("done") or "") if ended else ""
    checks = [{"check": "evidence", "ok": bool(evidence.strip()),
               "evidence": evidence or f"no end line with evidence for {step_id}"}]
    roles = task_loop.get("roles", {})
    unchecked = []
    if step["actor"] in roles:
        answers = latest_answers(task_dir, step["actor"])
        good = [(agent, meta) for agent, meta, text in answers if meta.get("ok") is True and last_verdict(text)]
        checks.append({"check": f"answer:{step['actor']}", "ok": bool(good),
                       "evidence": ", ".join(
                           f"{agent} {str(meta.get('head') or '?')[:7]} {meta.get('verdict') or ''}".strip()
                           for agent, meta in good) or f"no finished answer of {step['actor']} with a verdict"})
        return {"step": step_id, "skills": defaults, "checks": checks, "unchecked": [],
                "ok": all(c["ok"] for c in checks)}
    plan_text = read_task_file(ctx, "plan.md")
    in_build = bool({"tdd", "commit"} & set(defaults))
    for skill in defaults:
        problems = None
        if skill == "work-breakdown":
            problems = _breakdown_problems(plan_text)
        elif skill == "cross-check" and "work-breakdown" in defaults:
            scenario = read_task_file(ctx, "scenario.md")
            problems = [] if task_loop.get("trivial") else _scenario_plan_problems(scenario)
        elif skill == "cross-check":
            problems = [] if task_loop.get("trivial") else _scenario_run_problems(read_task_file(ctx, "scenario.md"))
        elif skill in ("tdd", "commit"):
            problems = _commit_problems(plan_text, cwd)
        elif skill == "unit" and not in_build:
            problems = _checks_entry_problems(plan_text, "Tests near the change")
        elif skill == "smoke":
            problems = _checks_entry_problems(plan_text, "Smoke")
        elif skill == "handoff":
            problems = _handoff_problems(read_task_file(ctx, "handoff.md"))
        if problems is None:
            if skill != "unit":
                unchecked.append(skill)
            continue
        checks.append({"check": f"record:{skill}", "ok": not problems,
                       "evidence": "; ".join(problems) or "in order"})
    return {"step": step_id, "skills": defaults, "checks": checks, "unchecked": unchecked,
            "ok": all(c["ok"] for c in checks)}


def _jsonl_rows(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        pass
    return rows


def _commit_problems(plan_text, cwd):
    header, rows = table(plan_text or "", "Work breakdown") or ([], [])
    if not rows:
        return ["plan.md has no work breakdown rows"]
    header = [h.lower() for h in header]
    if "status" not in header or "commit" not in header:
        return ["the work breakdown has no status or commit column"]
    if not cwd:
        return ["needs --cwd, the lead's clone, to find the commits"]
    problems = []
    for row in rows:
        if len(row) != len(header):
            problems.append(f"{row[0] or '?'}: {len(row)} cells, not {len(header)}")
            continue
        status, sha = row[header.index("status")].lower(), row[header.index("commit")].strip("` ")
        if status != "done":
            problems.append(f"{row[0]} is {status or 'empty'}, not done")
        elif not re.fullmatch(r"[0-9a-f]{7,40}", sha):
            problems.append(f"{row[0]} is done with no commit")
        elif subprocess.run(["git", "-C", cwd, "merge-base", "--is-ancestor", sha, "HEAD"],
                            capture_output=True).returncode != 0:
            problems.append(f"{row[0]}'s commit {sha} is not in the clone's history")
    return problems


def _breakdown_problems(plan_text):
    if plan_text is None:
        return ["no plan.md"]
    found = table(plan_text, "Work breakdown")
    if found is None:
        return ["plan.md has no work breakdown"]
    header, rows = found
    header = [h.lower() for h in header]
    problems = [f"the work breakdown has no {c} column" for c in ("test", "status", "commit") if c not in header]
    if not rows:
        problems.append("the work breakdown has no rows")
    return problems


def _scenario_plan_problems(scenario):
    if scenario is None:
        return ["no scenario.md"]
    problems = []
    if not re.search(r"^###\s+\d+", scenario, re.M):
        problems.append("scenario.md has no numbered step (### 1 · ...)")
    if "**Expect**" not in scenario:
        problems.append("scenario.md has no Expect line")
    return problems


def _scenario_run_problems(scenario):
    if scenario is None:
        return ["no scenario.md"]
    problems = []
    if not re.match(r"Verdict:\s*\w+", (section(scenario, "Closing") or "").strip(), re.I):
        problems.append("scenario.md has no closing verdict")
    addendum = last_addendum(scenario)
    if addendum is not None and not first_verdict(addendum):
        problems.append("scenario.md's last addendum has no verdict")
    empty = empty_agent_blocks(scenario)
    if empty:
        problems.append(f"scenario.md has {empty} Agent block(s) with no output")
    return problems


def _checks_entry_problems(plan_text, entry):
    if re.search(rf"^###\s+{entry}", section(plan_text or "", "Checks") or "", re.M | re.I):
        return []
    return [f"plan.md's Checks has no \"{entry}\" entry"]


def _handoff_problems(handoff):
    if handoff is None:
        return ["no handoff.md"]
    return [f"handoff.md lacks {n}" for n in HANDOFF_SECTIONS if section(handoff, n) is None]


def ran_commands(text):
    """The commands an answer lists as `- ran: <command> — exit 0`. QA's
    prompt names the full tests through fulltest.py (`python3 .../fulltest.py
    --min-free-gb N -- '<run>'`), and QA writes them as named, so a command
    run that way also counts as the command after its `--`."""
    out = set()
    for m in (RAN.match(line.strip()) for line in str(text).splitlines()):
        if not m:
            continue
        out.add(m.group(1).strip())
        try:
            words = shlex.split(m.group(1))
        except ValueError:
            continue
        wrapped = (len(words) > 2 and os.path.basename(words[0]).startswith("python")
                   and os.path.basename(words[1]) == "fulltest.py" and "--" in words[2:])
        if wrapped:
            out.add(" ".join(words[words.index("--") + 1:]))
    return out


def ran_in_answer(pr, spec, ctx):
    """Why a full command check needs no run, or None: an answer that its
    "answer" terms accept at the exact head lists `- ran: <run> — exit 0`."""
    terms = spec.get("answer")
    if not (spec.get("full") and isinstance(terms, dict) and ctx.get("task_dir")):
        return None
    for agent, meta, answer_file, text in accepted_answers(pr, terms, ctx, exact=True)[0]:
        if spec["run"].strip() in ran_commands(text):
            return (f"not run again: {agent} ran it at {pr['headRefOid'][:7]} with exit 0, on "
                    f"{meta.get('profile')}, and its answer {os.path.relpath(answer_file, ctx['task_dir'])} "
                    f"says Verdict: {last_verdict(text)}")
    return None


def check_command(pr, spec, ctx):
    passed = ran_in_answer(pr, spec, ctx)
    if passed:
        return True, passed
    if not ctx.get("cwd"):
        return False, "needs --cwd"
    env = {**os.environ, "AF_REPO": ctx.get("repo") or "", "AF_PR": str(pr.get("number") or ""),
           "AF_TASK": str(ctx.get("task") or ""), "AF_TASK_DIR": ctx.get("task_dir") or "",
           "AF_BASE": pr.get("baseRefName") or "", "AF_BASE_SHA": pr.get("baseRefOid") or "",
           "AF_HEAD": pr.get("headRefOid") or ""}
    script_file = None
    if spec.get("from_base"):
        script, why = base_script(ctx["cwd"], pr.get("baseRefOid"), spec["from_base"])
        if script is None:
            return False, why
        with tempfile.NamedTemporaryFile("w", suffix=".script", delete=False) as f:
            f.write(script)
        os.chmod(f.name, 0o700)
        script_file = f.name
        argv, shell = ([f.name] if script.startswith("#!") else ["sh", f.name]), False
    elif spec.get("full"):
        argv, shell = [sys.executable, FULLTEST, "--min-free-gb", str(spec.get("min_free_gb", 0)), "--",
                       spec["run"]], False
    else:
        argv, shell = spec["run"], True
    log_path = command_log_path(pr, spec, ctx)
    try:
        # One file for both streams keeps the order a failure was written in.
        with open(log_path, "w", encoding="utf-8") as log:
            code = subprocess.run(argv, shell=shell, cwd=ctx["cwd"], stdout=log, stderr=subprocess.STDOUT,
                                  env=env).returncode
    finally:
        if script_file:
            os.unlink(script_file)
    with open(log_path, encoding="utf-8", errors="replace") as log:
        tail = log.read().strip().splitlines()[-3:]
    return code == 0, f"exit {code}: {' | '.join(tail)} (log: {log_path})"


def command_log_path(pr, spec, ctx):
    """Where a command check's whole output goes: the task folder's
    gate-logs/ (made when missing) when the folder exists, else the
    temporary directory; one new
    file per run, named after the check, the head and the time."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", check_name(spec))
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    head = (pr.get("headRefOid") or "nohead")[:8]
    if ctx.get("task_dir") and os.path.isdir(ctx["task_dir"]):
        folder = os.path.join(ctx["task_dir"], "gate-logs")
        os.makedirs(folder, exist_ok=True)
    else:
        folder = tempfile.gettempdir()
    fd, path = tempfile.mkstemp(prefix=f"{name}-{head}-{stamp}-", suffix=".log", dir=folder)
    os.close(fd)
    return path


CHECKS = {"pr-open": check_pr_open, "loop-file": check_loop_file, "steps": check_steps, "docs": check_docs,
          "ci": check_ci, "base-fresh": check_base_fresh, "verdict": check_verdict,
          "tests-weakened": check_tests_weakened, "size": check_size, "ready": check_ready, "command": check_command}


def check_name(spec):
    """How a check is named in --skip and in the report."""
    if spec["check"] == "verdict":
        return f"verdict:{spec['role']}"
    return spec.get("name") or spec["check"]


def evaluate(pr, gate, cwd=None, skip=(), task_dir=None, before_ready=False):
    results = []
    ctx = {"cwd": cwd, "task_dir": task_dir, "repo": gate["repo"], "task": gate.get("task")}
    for spec in gate["checks"]:
        name = check_name(spec)
        if name in skip or (before_ready and (spec.get("at") == "merge" or name == "ready")):
            continue
        ok, evidence = CHECKS[spec["check"]](pr, spec, ctx)
        results.append({"check": name, "ok": ok, "severity": spec.get("severity", "block"), "evidence": evidence})
    blocked = [r for r in results if not r["ok"] and r["severity"] == "block"]
    return {"repo": gate["repo"], "pr": gate["pr"], "head": pr["headRefOid"], "pass": not blocked,
            "blocked": [r["check"] for r in blocked], "checks": results}


def validate_gate(gate):
    problems = []
    if not isinstance(gate, dict) or not re.match(r"^[\w.-]+/[\w.-]+$", str(gate.get("repo", ""))):
        return ["gate: repo must look like owner/name"]
    if gate.get("pr") is not None and (not isinstance(gate["pr"], int) or isinstance(gate["pr"], bool)):
        problems.append("gate: pr must be a number, or null until the pull request exists")
    for i, spec in enumerate(gate.get("checks", [])):
        name = spec.get("check") if isinstance(spec, dict) else None
        if name not in CHECKS:
            problems.append(f"gate: check {i + 1} is {name!r}; known: {', '.join(CHECKS)}")
        elif name == "verdict" and not spec.get("role"):
            problems.append(f"gate: verdict check {i + 1} needs a role")
        elif name == "command" and bool(spec.get("run")) == bool(spec.get("from_base")):
            problems.append(f"gate: command check {i + 1} needs run or from_base, not both")
        elif name == "command" and "answer" in spec and not (
                spec.get("full") and isinstance(spec["answer"], dict) and spec["answer"].get("role")):
            problems.append(f"gate: command check {i + 1} takes an answer only with full, and it needs a role")
        elif name == "loop-file" and not spec.get("sha256"):
            problems.append(f"gate: loop-file check {i + 1} needs sha256")
        if isinstance(spec, dict):
            problems += _severity_at_problems(spec, i)
    problems += _name_problems([s for s in gate.get("checks", []) if isinstance(s, dict) and "name" in s])
    if not gate.get("checks"):
        problems.append("gate: no checks")
    return problems


def _severity_at_problems(spec, i):
    problems = []
    if spec.get("severity", "block") not in ("block", "warn"):
        problems.append(f"gate: check {i + 1} severity must be block or warn")
    if spec.get("at", "merge") != "merge":
        problems.append(f"gate: check {i + 1} at must be merge, or left out")
    return problems


def _name_problems(specs):
    problems, seen = [], set()
    for spec in specs:
        name = spec.get("name")
        if not isinstance(name, str):
            problems.append(f"gate: check name {name!r} must be lower-case letters, digits and '-'")
            continue
        if spec.get("check") != "command":
            problems.append(f"gate: only a command check takes a name, not {spec.get('check')!r}")
        elif not CHECK_NAME.match(name):
            problems.append(f"gate: check name {name!r} must be lower-case letters, digits and '-'")
        elif name in CHECKS or name == "gate-file" or name.startswith("verdict"):
            problems.append(f"gate: check name {name!r} is taken by a standard check")
        elif name in seen:
            problems.append(f"gate: check name {name!r} is used twice")
        seen.add(name)
    return problems


def project_check_problems(checks):
    """Problems in a project's own gate checks (`gate` in project.json): a
    list of command checks, each with a name and either `run` (a command) or
    `from_base` (a script path in the repository), and optionally a severity
    and "at": "merge"."""
    if not isinstance(checks, list):
        return ["gate: must be a list of checks"]
    problems = []
    for i, spec in enumerate(checks):
        if not isinstance(spec, dict):
            problems.append(f"gate: check {i + 1} must be an object")
            continue
        extra = sorted(set(spec) - PROJECT_CHECK_KEYS)
        if extra:
            problems.append(f"gate: check {i + 1} has unknown key(s) {', '.join(extra)}")
        if spec.get("check") != "command":
            problems.append(f"gate: check {i + 1} must be a command check (\"check\": \"command\")")
        if "name" not in spec:
            problems.append(f"gate: check {i + 1} needs a name")
        has_run = isinstance(spec.get("run"), str) and bool(spec["run"].strip())
        from_base = spec.get("from_base")
        inside_repo = (isinstance(from_base, str) and bool(from_base.strip()) and not from_base.startswith("/")
                       and ".." not in from_base.split("/"))
        if from_base is not None and not inside_repo:
            problems.append(f"gate: check {i + 1} from_base must be a path inside the repository")
        elif has_run == (from_base is not None):
            problems.append(f"gate: check {i + 1} needs run (a command) or from_base (a script on the base), "
                            f"one of them")
        problems += _severity_at_problems(spec, i)
    named = [s for s in checks if isinstance(s, dict) and s.get("check") == "command" and "name" in s]
    return problems + _name_problems(named)


def template(task_loop, loop_sha=None, pr=None):
    """The standard gate for a task, from its loop.json: the loop file itself,
    the steps the lead must end before finalize, the task folder's records,
    one verdict check per judging role that runs (the build session's before
    ready, the verification session's at merge), each refusing the lead's
    profile, the full tests, the project's own checks, and the standing
    checks."""
    import loop as loops
    lead = task_loop.get("lead_profile")
    roles = task_loop.get("roles", {})
    verdicts = {}
    work = task_loop["work"]
    last_stage = work[-1]["stage"]
    checks = [{"check": "pr-open"}]
    if loop_sha:
        checks.append({"check": "loop-file", "sha256": loop_sha})
    checks += [{"check": "steps", "ids": [s["id"] for s in work if s["stage"] != last_stage]},
               {"check": "docs", "trivial": task_loop["trivial"]}, {"check": "ci"}, {"check": "base-fresh"}]
    for which, at in (("work", None), ("check", "merge")):
        for role in dict.fromkeys(s["actor"] for s in task_loop[which] if s["actor"] in roles):
            spec = {"check": "verdict", "role": role, "accept": roles[role].get("accept", ["approved"]),
                    "not_profiles": [lead] if lead else []}
            if at:
                spec["at"] = at
                if task_loop.get("post_answers"):
                    spec["posted"] = True
            checks.append(spec)
            verdicts[role] = spec
    if task_loop.get("tests_full"):
        full = {"check": "command", "run": task_loop["tests_full"], "full": True,
                "min_free_gb": task_loop.get("disk_min_free_gb", 0)}
        tester = next((s["actor"] for s in task_loop["check"] if s["actor"] in verdicts
                       and "full" in loops.recorded_defaults(s.get("skills", []))), None)
        if tester:
            full["answer"] = {k: v for k, v in verdicts[tester].items() if k not in ("check", "at")}
        checks.append(full)
    checks += [dict(spec) for spec in task_loop.get("gate") or []]
    checks += [{"check": "tests-weakened", "allow": []},
               {"check": "size", "max_lines": task_loop.get("max_lines", 400),
                "severity": task_loop.get("size_severity", "warn")},
               {"check": "ready"}]
    return {"repo": task_loop["repo"], "pr": pr, "task": task_loop["task"], "difficulty": task_loop["difficulty"],
            "trivial": task_loop["trivial"], "checks": checks}


def append_gate_run(task_dir, report, before_ready, skip=(), sha_checked=False):
    import datetime
    row = {"time": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "head": report["head"], "before_ready": before_ready, "pass": report["pass"],
           "blocked": report["blocked"],
           "warned": [r["check"] for r in report["checks"] if not r["ok"] and r["severity"] == "warn"],
           "skipped": sorted(skip), "sha_checked": sha_checked}
    try:
        with open(os.path.join(task_dir, "gates.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except OSError as e:
        print(f"gate.py: could not record the run in {task_dir}/gates.jsonl: {e}", file=sys.stderr)


def main(argv):
    ap = argparse.ArgumentParser(prog="gate.py", description="agent-foreman pass conditions")
    ap.add_argument("command", choices=["template", "hash", "run", "record"])
    ap.add_argument("--step", help="record: the step that ended")
    ap.add_argument("gate", nargs="?")
    ap.add_argument("--loop", metavar="LOOP.json", help="template: the task's loop.json")
    ap.add_argument("--pr", type=int)
    ap.add_argument("--cwd")
    ap.add_argument("--task-dir", help="the task folder (status.py dir): reviews/ and the records")
    ap.add_argument("--skip", default="")
    ap.add_argument("--before-ready", action="store_true")
    ap.add_argument("--sha", metavar="HEX", help="run: the gate file's hash the foreman recorded with the brief")
    args = ap.parse_args(argv)

    if args.command == "template":
        if not args.loop:
            print("gate.py: template needs --loop <the task's loop.json>", file=sys.stderr)
            return 2
        path = os.path.expanduser(args.loop)
        try:
            with open(path, encoding="utf-8") as f:
                task_loop = json.load(f)
            gate = template(task_loop, sha256_file(path), args.pr)
        except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
            print(f"gate.py: {args.loop} is not a task's loop.json (loop.py render --json): {e}", file=sys.stderr)
            return 2
        print(json.dumps(gate, indent=2))
        return 0

    if args.command == "record":
        if not (args.step and args.task_dir):
            print("gate.py: record needs --step and --task-dir", file=sys.stderr)
            return 2
        task_dir = os.path.abspath(os.path.expanduser(args.task_dir))
        try:
            with open(os.path.join(task_dir, "loop.json"), encoding="utf-8") as f:
                report = record_checks(json.load(f), args.step, task_dir,
                                       os.path.expanduser(args.cwd) if args.cwd else None)
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f"gate.py: {e}", file=sys.stderr)
            return 2
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["ok"] else EXIT_GATE_FAILED

    if not args.gate:
        print(f"gate.py: {args.command} needs a gate file", file=sys.stderr)
        return 2
    path = os.path.expanduser(args.gate)
    if args.command == "hash":
        print(sha256_file(path))
        return 0
    with open(path, encoding="utf-8") as f:
        gate = json.load(f)
    problems = validate_gate(gate)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2
    if gate.get("pr") is not None and args.pr is not None and gate["pr"] != args.pr:
        print(f"gate.py: the gate file is for #{gate['pr']}, not #{args.pr}", file=sys.stderr)
        return 2
    gate["pr"] = gate.get("pr") if gate.get("pr") is not None else args.pr
    if gate["pr"] is None:
        print("gate.py: the gate file names no pull request yet; add --pr N", file=sys.stderr)
        return 2
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    if "verdict" in skip:
        print("gate.py: --skip names a verdict check with its role, such as verdict:qa", file=sys.stderr)
        return 2
    task_dir = os.path.abspath(os.path.expanduser(args.task_dir)) if args.task_dir else None
    if args.sha and sha256_file(path) != args.sha.strip().lower():
        report = {"repo": gate["repo"], "pr": gate["pr"], "head": None, "pass": False, "blocked": ["gate-file"],
                  "checks": [{"check": "gate-file", "ok": False, "severity": "block",
                              "evidence": "the gate file changed after the brief"}]}
        print(json.dumps(report, indent=2))
        if task_dir:
            append_gate_run(task_dir, report, args.before_ready, skip, sha_checked=True)
        return EXIT_GATE_FAILED
    cwd = os.path.expanduser(args.cwd) if args.cwd else None
    comments = any(s.get("posted") or (isinstance(s.get("answer"), dict) and s["answer"].get("posted"))
                   for s in gate["checks"] if isinstance(s, dict))
    report = evaluate(fetch(gate["repo"], gate["pr"], comments), gate, cwd, skip, task_dir, args.before_ready)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if task_dir:
        append_gate_run(task_dir, report, args.before_ready, skip, sha_checked=bool(args.sha))
    return 0 if report["pass"] else EXIT_GATE_FAILED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
