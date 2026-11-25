"""Codex CLI adapter."""
import glob
import json
import os
import re
import shlex
import subprocess

from .base import PLUGIN, NoTranscript

KIND = "codex"
HERDR_KIND = "codex"
EXECUTABLE = "codex"
GATEWAY_KINDS = ["openai"]
TRUST_SCREEN = "Trust this folder?"
TRUST_KEYS = ["Enter"]
EDIT_TOOLS = ["apply_patch"]
LINKED = os.path.join(".agents", "skills")
SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALIAS = re.compile(r"^[0-9A-Za-z][0-9A-Za-z-]{7,63}$")


def _state():
    home = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(home, "agent-foreman")


def alias_path(alias):
    return os.path.join(_state(), "sessions", f"{alias}.json")


def record_session(alias, data):
    """Keep Codex's own session id under the id the foreman chose (hook.py session)."""
    if not ALIAS.match(alias):
        return
    path = alias_path(alias)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: data.get(k) for k in ("session_id", "transcript_path", "cwd")}, f)
    os.replace(tmp, path)


def _alias(session_id):
    try:
        with open(alias_path(session_id), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _sessions(root):
    return root or os.path.join(os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex"),
                                "sessions")


def _session_file(session_id, root):
    """Codex's session file for an id the foreman chose or Codex's own id, or None."""
    known = _alias(session_id) if ALIAS.match(session_id) else {}
    if known.get("transcript_path") and os.path.isfile(known["transcript_path"]):
        return known["transcript_path"]
    real = known.get("session_id") or session_id
    hits = glob.glob(os.path.join(glob.escape(root), "**", f"rollout-*-{glob.escape(real)}.jsonl"), recursive=True)
    return max(hits, key=os.path.getmtime) if hits else None


def _toml(text):
    return json.dumps(text)


def _hooks(scripts, no_edit):
    """The hooks of one run, as -c options: Codex's session id under the
    foreman's, the merge and edit guard, and heartbeats."""
    def run(script, *args):
        return shlex.join(["python3", os.path.join(scripts, script), *args])
    hooks = [("SessionStart", None, run("hook.py", "session")),
             ("PreToolUse", ".*", run("hook.py", "guard", *(["--no-edit"] if no_edit else []))),
             ("PostToolUse", ".*", run("heartbeat.py", "post")),
             ("Stop", None, run("heartbeat.py", "stop"))]
    out = []
    for event, matcher, command in hooks:
        match = f"matcher={_toml(matcher)}," if matcher else ""
        out += ["-c", f'hooks.{event}=[{{{match}hooks=[{{type="command",command={_toml(command)}}}]}}]']
    return out + ["--dangerously-bypass-hook-trust"]


def command(cfg, profile_name, name=None, session_id=None, bundle=None, environ=None,
            print_mode=False, no_edit=False, resume=None, plugin_dirs=()):
    """Return (argv, variables to set, variable names to clear). In print mode
    Codex answers one prompt read from stdin and prints JSON lines (`codex exec
    --json`). Either way it runs in the folder it is started in, its own clone.

    Codex takes no session name or id at its start. The id the foreman chose
    goes in AF_SESSION_ALIAS, and the SessionStart hook keeps Codex's own id
    under it, so last_answers and `resume` find the session by the foreman's
    id; `resume` without that record continues the folder's last session.
    `no_edit` denies the edit tool, and `gh pr merge` is always denied, both
    through the PreToolUse hook (hook.py guard). Its shell commands run in a
    plain shell with the environment launch.py gave it: a login shell would
    put the profile's PATH in front. `plugin_dirs` are not loaded
    whole: Codex reads their skills through links (prepare); their agents and
    hooks do not come along."""
    profile = cfg["profiles"][profile_name]
    scripts = os.path.join(bundle, "scripts") if bundle else SCRIPTS
    argv = [EXECUTABLE]
    if print_mode:
        argv += ["exec", "--json"]
    elif resume:
        argv.append("resume")
    argv += ["--model", profile["model"]]
    if cfg["launch"]["permission"] == "bypass":
        argv.append("--dangerously-bypass-approvals-and-sandbox")
    argv += ["-c", "allow_login_shell=false"] + _hooks(scripts, no_edit)
    if resume and not print_mode:
        found = _session_file(resume, _sessions(None))
        known = _alias(resume).get("session_id")
        argv += [known] if known else ([resume] if found else ["--last"])
    alias = None if print_mode else (resume or session_id)
    env = {"AF_SESSION_ALIAS": alias} if alias else {}
    clear = set() if alias else {"AF_SESSION_ALIAS"}
    return argv, env, clear


def _exclude(workdir, paths):
    r = subprocess.run(["git", "-C", workdir, "rev-parse", "--git-path", "info/exclude"], capture_output=True,
                       text=True)
    if r.returncode != 0:
        return
    path = os.path.join(workdir, r.stdout.strip())
    try:
        with open(path, encoding="utf-8") as f:
            have = set(f.read().splitlines())
    except OSError:
        have = set()
    new = [p for p in paths if p not in have]
    if new:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write("".join(f"{p}\n" for p in new))


def _skill_dirs(bundle, workdir):
    """(link name, target) for every skill the agent may call. The bundle is a
    Claude Code plugin named foreman-kit, and Codex names a skill under a
    plugin's `.claude-plugin/plugin.json` `<plugin>:<skill>`, as Claude Code
    does: the bundle's own skills, then each plugin it carries. The project's
    .claude/skills/ keep their bare names."""
    out = []
    if bundle:
        carried = os.path.join(bundle, "plugins")
        plugins = sorted(os.listdir(carried)) if os.path.isdir(carried) else []
        for root, prefix in [(os.path.join(bundle, "skills"), PLUGIN)] + [
                (os.path.join(carried, p, "skills"), p) for p in plugins]:
            if os.path.isdir(root):
                out += [(f"{prefix}--{d}", os.path.join(root, d)) for d in sorted(os.listdir(root))
                        if os.path.isfile(os.path.join(root, d, "SKILL.md"))]
            elif os.path.isfile(os.path.join(os.path.dirname(root), "SKILL.md")):
                out.append((f"{prefix}--{prefix}", os.path.dirname(root)))
    project = os.path.join(workdir, ".claude", "skills")
    if os.path.isdir(project):
        out += [(d, os.path.join("..", "..", ".claude", "skills", d)) for d in sorted(os.listdir(project))
                if os.path.isfile(os.path.join(project, d, "SKILL.md"))]
    return out


def prepare(workdir, bundle):
    """Link the skills into the folder's .agents/skills/, where Codex finds
    them, and keep the links out of git (_skill_dirs). A link of an earlier
    bundle is pointed at this one; any other name the folder already holds is
    left alone."""
    target = os.path.join(workdir, LINKED)
    linked = []
    for name, src in _skill_dirs(bundle, workdir):
        dest = os.path.join(target, name)
        if os.path.islink(dest) and "--" in name and os.path.isabs(os.readlink(dest)) and os.readlink(dest) != src:
            os.unlink(dest)
        if not os.path.lexists(dest):
            os.makedirs(target, exist_ok=True)
            os.symlink(src, dest)
        if os.path.islink(dest) and os.readlink(dest) == src:
            linked.append(f"/{LINKED}/{name}")
    _exclude(workdir, linked)


def _run(text):
    """The parts of a `codex exec --json` run: the session (thread.started),
    the last answer (item.completed of an agent_message), whether the turn
    ended (turn.completed, not turn.failed), its usage and its error."""
    session, result, done, failed, usage = None, "", False, "", None
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        if kind == "thread.started":
            session = event.get("thread_id")
        elif kind == "item.completed" and item.get("type") == "agent_message":
            result = item.get("text") or ""
        elif kind == "turn.completed":
            done = True
            usage = event.get("usage")
        elif kind in ("turn.failed", "error"):
            error = event.get("error") if isinstance(event.get("error"), dict) else {}
            failed = error.get("message") or event.get("message") or kind
            if kind == "turn.failed":
                done = False
    return {"ok": done, "result": result if done else (failed or result or text.strip()[-500:]),
            "session_id": session, "usage": usage}


def parse_print(text):
    """The parts of a `codex exec --json` run the foreman uses. Codex reports
    tokens, not a cost."""
    run = _run(text)
    return {"ok": run["ok"], "result": run["result"], "session_id": run["session_id"], "cost": None, "denials": []}


def answer_file(text):
    """The run's answer as one JSON object in Claude Code's names, so the
    gate and the retro read every kind's answer the same way; `usage` holds
    Codex's token counts."""
    run = _run(text)
    return json.dumps({"type": "result", "is_error": not run["ok"], "result": run["result"],
                       "session_id": run["session_id"], "total_cost_usd": None, "permission_denials": [],
                       "usage": run["usage"]}, indent=2) + "\n"


def skill_name(ref):
    return f"{PLUGIN}:{ref.split(':')[-1]}"


def bundle_layout(skills):
    """Nothing apart from Claude Code's plugin: Codex reads its skills through
    links (prepare)."""
    return {}


def last_answers(session_id, n=1, root=None):
    """The final text of each of the last n answered turns, oldest first, read
    from Codex's session file (~/.codex/sessions/.../rollout-<time>-<id>.jsonl;
    CODEX_HOME moves it): each turn's task_complete holds its last answer. The
    id is the one the foreman chose or Codex's own. Returns (answers, total)."""
    root = _sessions(root)
    path = _session_file(session_id, root)
    if path is None:
        raise NoTranscript(f"no Codex session file for session {session_id} under {root}, and no record of "
                           f"Codex's id for it in {os.path.dirname(alias_path(session_id))}")
    answers = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            payload = entry.get("payload") if isinstance(entry, dict) else None
            if (entry.get("type") == "event_msg" and isinstance(payload, dict)
                    and payload.get("type") == "task_complete"
                    and isinstance(payload.get("last_agent_message"), str)
                    and payload["last_agent_message"].strip()):
                answers.append(payload["last_agent_message"])
    return answers[-n:], len(answers)
