#!/usr/bin/env python3
"""Build a project's skill bundle and put it on a herdr machine once.

A bundle holds agent-foreman's default skills (kit/skills), the project's
other skills (each skill directory whole, with its scripts), in the layout the
agent kind loads (its adapter's bundle_layout; for claude, a plugin named
foreman-kit), the lead's guide, launch.py with the
project's launch settings and the adapters, and transcript.py. A skill of a
plugin in the settings' plugin_dirs goes with its plugin: the bundle carries
that plugin's whole directory under `plugins/<name>/`, and launch.py loads it
with its own --plugin-dir, so its agents, scripts and hooks come along and no
machine needs the plugin installed. `bundle.json`
names the agent kind. Its name is a hash of its content: a machine that
already holds it is not sent it again, and any change makes a new one.

Usage:
  bundle.py build --project OWNER/REPO [--skills REF,...] [--agent KIND]
  bundle.py push MACHINE --project OWNER/REPO [--skills REF,...] [--agent KIND]

MACHINE is a herdr machine label, or `local`. --skills adds skills for one
task to the project's own. Prints one JSON object.

Exit codes: 1 = a machine could not be reached or written, 2 = bad
arguments, 3 = setup needed (project settings, an unknown skill).
"""
import argparse
import hashlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile

import adapters
import loop as loops
from config import (EXIT_SETUP_NEEDED, LOCAL, REPO, SKILL_DIR, cache_dir, project_path, project_skills,
                    herdr_machines, load, local_skills, plugin_list, plugin_dirs, settings_problems, whole_plugins)

HERE = os.path.dirname(os.path.abspath(__file__))
KIT_DIR = os.path.join(SKILL_DIR, "kit", "skills")
REMOTE_CACHE = "~/.cache/agent-foreman"
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}
SKIP_FILES = {".DS_Store"}
SSH = ["ssh", "-o", "BatchMode=yes"]
# The scripts an agent runs, and every module they import (config imports loop).
BUNDLED = ("config.py", "loop.py", "launch.py", "transcript.py", "score.py", "gate.py", "status.py", "heartbeat.py", "clone.py",
           "fulltest.py", "status_reader.py")


def fail(code, message):
    print(f"bundle.py: {message}", file=sys.stderr)
    sys.exit(code)


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def _tree(src):
    """Every file under a skill directory: relative path -> bytes."""
    out = {}
    for root, dirs, names in os.walk(src, followlinks=True):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            if name in SKIP_FILES or name.endswith(".pyc"):
                continue
            out[os.path.relpath(os.path.join(root, name), src)] = _read(os.path.join(root, name))
    return out


def contents(cfg, skill_dirs, kind=adapters.DEFAULT, plugins=None):
    """Every file of the bundle: relative path -> bytes. `plugins` (name ->
    directory) are carried whole under plugins/<name>/ and named in
    config.json's `plugins`."""
    adapter = adapters.get(kind)
    plugins = plugins or {}
    settings = {k: cfg[k] for k in ("gateways", "profiles", "launch", "difficulty")}
    settings["plugins"] = sorted(plugins)
    files = {
        "bundle.json": json.dumps({"agent": kind}).encode() + b"\n",
        "config.json": json.dumps(settings, indent=2, sort_keys=True).encode() + b"\n",
        "loop.md": _read(os.path.join(SKILL_DIR, "loop.md")),
        "tester.md": _read(os.path.join(SKILL_DIR, "tester.md")),
    }
    for name in BUNDLED:
        files[f"scripts/{name}"] = _read(os.path.join(HERE, name))
    for rel, data in _tree(os.path.join(HERE, "adapters")).items():
        files[f"scripts/adapters/{rel}"] = data
    files.update(adapter.bundle_layout({ref.split(":")[-1]: _tree(src) for ref, src in skill_dirs.items()}))
    for name, src in sorted(plugins.items()):
        for rel, data in _tree(src).items():
            files[f"plugins/{name}/{rel}"] = data
    return files


def digest(files):
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode() + b"\0" + files[rel] + b"\0")
    return h.hexdigest()[:16]


def write_local(bundle_hash, files):
    """Unpack the bundle into this machine's cache once. Returns (path, status)."""
    root = os.path.join(cache_dir(), "bundles")
    path = os.path.join(root, bundle_hash)
    if os.path.isfile(os.path.join(path, "bundle.json")):
        return path, "cached"
    os.makedirs(root, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=root, prefix=f".{bundle_hash}.")
    for rel, data in files.items():
        dest = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
    try:
        os.rename(tmp, path)
    except OSError:
        shutil.rmtree(tmp)  # another run put the same bundle there first
    return path, "built"


def zipped(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(files):
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, files[rel])
    return buf.getvalue()


def ssh(target, command):
    r = subprocess.run(SSH + [target, command], capture_output=True, text=True)
    if r.returncode != 0:
        fail(1, f"ssh {target} failed ({r.returncode}): {r.stderr.strip()[:300]}")
    return r.stdout


def push_remote(target, bundle_hash, files):
    """Put the bundle on a remote machine once. Returns (absolute path, status)."""
    h = shlex.quote(bundle_hash)
    probe = (f"mkdir -p {REMOTE_CACHE}/bundles && cd {REMOTE_CACHE}/bundles && pwd && "
             f"if test -f {h}/bundle.json; then echo cached; else echo missing; fi")
    lines = ssh(target, probe).split()
    if len(lines) != 2:
        fail(1, f"unexpected answer from {target}: {lines!r}")
    remote_root, state = lines
    path = f"{remote_root}/{bundle_hash}"
    if state == "cached":
        return path, "cached"
    with tempfile.NamedTemporaryFile(suffix=".zip") as tmp:
        tmp.write(zipped(files))
        tmp.flush()
        r = subprocess.run(["scp", "-q", "-o", "BatchMode=yes", tmp.name,
                            f"{target}:{remote_root}/{bundle_hash}.zip"], capture_output=True, text=True)
        if r.returncode != 0:
            fail(1, f"scp to {target} failed: {r.stderr.strip()[:300]}")
    ssh(target, f"cd {shlex.quote(remote_root)} && rm -rf {h}.tmp && python3 -m zipfile -e {h}.zip {h}.tmp && "
                f"{{ test -d {h} || mv {h}.tmp {h}; }} && rm -rf {h}.tmp {h}.zip && "
                f"test -f {h}/bundle.json")
    return path, "uploaded"


def build(repo, extra, kind=adapters.DEFAULT, project_names=()):
    """The bundle for a project: (hash, files, skills it carries, warnings).

    Every default skill is bundled. Every other skill the project's loops
    name, or the settings' `skills` map names as a replacement, is looked up
    the way an agent will find it: a project skill (in `project_names`, the
    checkout's `.claude/skills` and `.claude/commands`) is used where it is
    and not bundled; a skill of a plugin in plugin_dirs brings its whole
    plugin into the bundle; otherwise the person's skill of that name is
    bundled. A loop skill found nowhere is
    a warning; a skill named in `extra` or in bundle.skills must exist.
    """
    if not os.path.exists(project_path(repo)):
        fail(EXIT_SETUP_NEEDED, f"project {repo} has no settings yet; run /agent-foreman:agent-foreman setup")
    cfg = load(repo)
    problems = settings_problems(cfg, repo=repo, project=True)
    if problems:
        fail(EXIT_SETUP_NEEDED, f"project {repo}: {problems[0]}")
    names = project_skills(cfg, extra)
    overrides = cfg.get("skills", {})
    needs_local = [n for n in names if n not in loops.KIT] or any(overrides.get(n) for n in names)
    plugins = plugin_list(plugin_dirs(cfg)) if needs_local else []
    available = local_skills(plugins) if needs_local else {}
    whole = whole_plugins(cfg, plugins) if needs_local else {}
    required = set(extra) | set(cfg.get("bundle", {}).get("skills", []))
    refs, plugin_refs, carried, warnings = [], [], {}, []
    kit = {}
    for name in loops.KIT:
        path = os.path.join(KIT_DIR, name)
        if os.path.isfile(os.path.join(path, "SKILL.md")):
            kit[name] = path
        elif name in names:
            warnings.append(f"default skill {name} is missing from {KIT_DIR}")
    for name in names:
        source, value = loops.resolve(name, project_names, available, overrides, whole)
        if source == "kit":
            continue
        if source == "plugin" and value not in plugin_refs:
            plugin_refs.append(value)
            plugin = value.split(":")[0]
            if plugin == adapters.get(kind).PLUGIN:
                fail(EXIT_SETUP_NEEDED, f"plugin {plugin} has the name of the bundle's own plugin; it cannot go along")
            carried[plugin] = os.path.expanduser(whole[plugin])
        elif source == "bundle" and value not in refs:
            refs.append(value)
        elif source == "missing":
            if name in required:
                fail(EXIT_SETUP_NEEDED, f"skill not available on this machine: {value} (config.py skills lists the "
                                        f"ones that are; a plugin loaded with --plugin-dir goes in plugin_dirs: "
                                        f"/agent-foreman:agent-foreman setup)")
            warnings.append(value)
    shorts = [r.split(":")[-1] for r in refs] + list(kit)
    if len(set(shorts)) != len(shorts):
        fail(EXIT_SETUP_NEEDED, f"two skills share one name in the bundle: {', '.join(refs + list(kit))}")
    files = contents(cfg, {**{r: available[r] for r in refs}, **kit}, kind, carried)
    return (digest(files), files, [adapters.get(kind).skill_name(r) for r in refs + list(kit)] + plugin_refs,
            warnings)


def main(argv):
    ap = argparse.ArgumentParser(prog="bundle.py", description="agent-foreman skill bundles")
    ap.add_argument("command", choices=["build", "push"])
    ap.add_argument("machine", nargs="?")
    ap.add_argument("--project", required=True, metavar="OWNER/REPO")
    ap.add_argument("--skills", default="", metavar="REF,...")
    ap.add_argument("--agent", default=adapters.DEFAULT, choices=adapters.KINDS)
    args = ap.parse_args(argv)
    if not REPO.match(args.project):
        fail(2, f"--project must look like owner/name, not {args.project!r}")
    if args.command == "push" and not args.machine:
        fail(2, "push needs a machine label, or local")
    extra = [s.strip() for s in args.skills.split(",") if s.strip()]

    machine = LOCAL if args.command == "build" else args.machine
    hosts = load(args.project).get("machines", {})
    project_names = []
    if machine in hosts:
        try:
            project_names = loops.project_skill_names(machine, hosts[machine])
        except (ValueError, RuntimeError) as e:
            fail(1, f"cannot list the project's skills on {machine}: {e}")
    bundle_hash, files, skills, warnings = build(args.project, extra, args.agent, project_names)
    out = {"hash": bundle_hash, "agent": args.agent, "skills": skills, "project_skills": project_names,
           "missing": warnings}
    for w in warnings:
        print(f"bundle.py: missing skill: {w}", file=sys.stderr)
    if args.command == "build" or args.machine == LOCAL:
        path, status = write_local(bundle_hash, files)
        out.update(machine=LOCAL, path=path, status=status, cache=cache_dir())
    else:
        machines = herdr_machines()
        m = machines.get(args.machine)
        if m is None:
            fail(2, f"{args.machine!r} is not a saved herdr machine ({', '.join(machines) or 'none saved'})")
        if not m["enabled"]:
            fail(2, f"herdr machine {args.machine} is disabled")
        path, status = push_remote(m["target"], bundle_hash, files)
        out.update(machine=args.machine, path=path, status=status, cache=os.path.dirname(os.path.dirname(path)),
                   target=m["target"])
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
