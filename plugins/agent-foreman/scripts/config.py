#!/usr/bin/env python3
"""Settings of agent-foreman: standard values, user settings and project settings.

Three levels, each laid over the one before:

  standard  defaults.json in this skill's directory
  user      $XDG_CONFIG_HOME/agent-foreman/config.json   (~/.config/...)
  project   $XDG_STATE_HOME/agent-foreman/projects/<owner>-<repo>/project.json

The user and project files hold only the values that differ from the level
below; a missing key falls back. Settings hold token variable names only,
never token values.

The models are in one file the person edits, by provider:
$XDG_CONFIG_HOME/agent-foreman/providers.json. When it exists, it replaces
the standard gateways, profiles and tiers whole; `providers --init` copies
providers.json.sample, which holds the standard's models, when it is missing. A provider without `base_url` is Anthropic (Claude
Code's own login); one with it is anthropic-compatible and needs `auth`,
`token_env` (the variable's name) and each model's `context`:

  {"providers": [
     {"id": "anthropic", "models": [{"id": "opus"}, {"id": "sonnet"}, {"id": "haiku"}]},
     {"id": "tf", "base_url": "https://...", "auth": "bearer", "token_env": "TF_API_TOKEN",
      "models": [{"id": "zai-org/GLM-5.3-Flash", "name": "glm", "context": 200000}]}],
   "tiers": {"low": ["haiku"], "mid": ["glm", "sonnet"], "high": ["opus", "sonnet"]}}

A model's `name` (default: its `id`) is its profile name, the one tiers use.
`roles` maps a subagent's opus, sonnet and haiku to models of the same
provider (default: the model itself); `agent` names the agent kind (default
claude).

Usage:
  config.py paths [--project OWNER/REPO]
  config.py providers [--init]   (the models file: its path and problems; --init copies the sample when missing)
  config.py show [--project OWNER/REPO]
  config.py check [--project OWNER/REPO] [--models]
  config.py save user|project [--project OWNER/REPO] [--dry-run]   (full settings as JSON on stdin)
  config.py check-machine MACHINE PATH --project OWNER/REPO   (is the machine ready for the project's agents)
  config.py plugin-dir-candidates   (this session's --plugin-dir directories, agent-foreman left out, then
      plugins installed on this machine but not enabled here; one directory a line, what each is on stderr)
  config.py skills [--plugin-dir DIR ...]   (skills with these directories added, nothing saved)
  config.py tier --difficulty low|mid|high --role ROLE [--lead PROFILE] [--skip PROFILE,...]
      (a role other than the lead gets its tier and higher ones, never the lead's profile; ROLE is the
      lead, a role of the settings' loop, or the tester, which runs the red team and QA)
  config.py profiles | projects | machines | skills

`check --models` also asks each provider with a base_url for its model list
(`<base_url>/v1/models`, with the provider's auth and the key from its
token_env, never printed) and prints each model as listed, not listed, or
unknown. Only a model missing from a list the provider gave is a problem. A
provider without a list there, a missing key or a network error leaves its
models unknown. It uses the network; plain `check` does not.

`plugin_dirs` in the settings lists plugin directories the person loads with
`--plugin-dir` (often through a `claude` shell wrapper). Skill lookups pass
them to `claude plugin list`, so their skills count as available. A plugin
whose skill the loops use goes to the agents whole: the bundle carries its
directory. `plugin-dir-candidates` also lists plugins installed on this
machine but not enabled here, whose directory can go in plugin_dirs.
"""
import argparse
import copy
import json
import os
import re
import shutil
import string
import subprocess
import sys
import tempfile

import adapters
import gate as gates
import loop as loops

APP = "agent-foreman"
KINDS = ["anthropic", "anthropic-compatible"]
AUTHS = ["bearer", "x-api-key"]
ROLES = ["opus", "sonnet", "haiku"]
PERMISSIONS = ["bypass", "default"]
PLACEMENTS = ["least-busy", "ask"]
# Events the foreman handles. Only the ones that rename a tab take a label.
EVENTS = ["started", "stage", "done", "blocked", "stalled", "exited",
          "owner-decision", "approved", "merged", "all-approved"]
LABEL_EVENTS = ["blocked", "exited", "owner-decision"]
PLACEHOLDERS = ["task", "stage", "round", "machine", "profile", "project"]
SECTIONS = ["plugin_dirs", "gateways", "profiles", "tiers", "difficulty", "launch", "bundle", "skills", "loop", "labels",
            "report", "ops"]
PROJECT_KEYS = ["repo", "workspace", "machines", "tests", "gate", "post_answers"]
MODEL_KEYS = ["gateways", "profiles", "tiers"]  # from providers.json, never from config.json or project.json
PROVIDER_KEYS = ["id", "name", "base_url", "auth", "token_env", "models"]
MODEL_ENTRY_KEYS = ["id", "name", "context", "roles", "agent"]
# Model tiers, lowest first. The red team and QA take one tier above the lead.
TIERS = loops.LEVELS
# When the settings' loop.roles do not say. The tester runs the red team and QA, so it takes their tier.
ROLE_STEP = {"redteam": 1, "qa": 1, "tester": 1}
LOCAL = "local"
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# Exit codes shared by the scripts, so the foreman can tell the cases apart.
EXIT_SETUP_NEEDED = 3
EXIT_TOKEN_MISSING = 4
EXIT_AGENT_ERROR = 5  # a prompt-mode run failed: a usage limit, a gateway error, or no result

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
# This skill, which is also the plugin's root: the foreman's own, never bundled
# for agents, whether it is installed as a plugin or as a user skill.
SELF = "agent-foreman"
SELF_DIR = SKILL_DIR


def _xdg(var, fallback):
    return os.environ.get(var) or os.path.join(os.path.expanduser("~"), fallback)


def defaults_path():
    return os.path.join(SKILL_DIR, "defaults.json")


def user_path():
    return os.path.join(_xdg("XDG_CONFIG_HOME", ".config"), APP, "config.json")


def providers_path():
    return os.path.join(_xdg("XDG_CONFIG_HOME", ".config"), APP, "providers.json")


def providers_sample_path():
    """The models file to start from: the standard's models, by provider."""
    return os.path.join(SKILL_DIR, "providers.json.sample")


def state_dir():
    return os.path.join(_xdg("XDG_STATE_HOME", os.path.join(".local", "state")), APP)


def cache_dir():
    return os.path.join(_xdg("XDG_CACHE_HOME", ".cache"), APP)


def project_dir(repo):
    return os.path.join(state_dir(), "projects", repo.replace("/", "-"))


def project_path(repo):
    return os.path.join(project_dir(repo), "project.json")


def ledger_path(repo):
    return os.path.join(project_dir(repo), "ledger.md")


def log_path(repo):
    return os.path.join(project_dir(repo), "log.jsonl")


def memory_path(repo):
    """What only this project has (tag format, docs steps, disk floor); the foreman keeps it."""
    return os.path.join(project_dir(repo), "memory.md")


def read_json(path, default=None):
    if not os.path.exists(path):
        return copy.deepcopy(default) if default is not None else {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_settings(path):
    """A settings file the person may edit by hand (config.json, providers.json,
    project.json); {} when missing. A file that is not valid JSON stops the
    script with where the error is, as a setup problem."""
    try:
        return read_json(path)
    except json.JSONDecodeError as e:
        print(f"{path}: not valid JSON at line {e.lineno}, column {e.colno}: {e.msg}. Fix the file and run again.",
              file=sys.stderr)
        raise SystemExit(EXIT_SETUP_NEEDED)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp.", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def _id_list(value):
    return isinstance(value, list) and bool(value) and all(isinstance(x, dict) and "id" in x for x in value)


def _merge_ids(base, over):
    """Lists of {"id": ...} items merge item by item: a matching id is laid
    over, {"id", "remove": true} drops one, and a new id goes after its
    "after" id (or first, when "after" is null, or last, without it)."""
    items = [copy.deepcopy(b) for b in base]
    for o in over:
        ids = [x["id"] for x in items]
        if o.get("remove"):
            items = [x for x in items if x["id"] != o["id"]]
        elif o["id"] in ids:
            i = ids.index(o["id"])
            items[i] = merge(items[i], {k: v for k, v in o.items() if k != "after"})
        else:
            new = {k: copy.deepcopy(v) for k, v in o.items() if k != "after"}
            if "after" not in o:
                items.append(new)
            elif o["after"] is None:
                items.insert(0, new)
            else:
                items.insert(ids.index(o["after"]) + 1 if o["after"] in ids else len(items), new)
    return items


def merge(base, over):
    """`over` laid on `base`: dicts merge key by key, lists of {"id": ...}
    items merge by id, anything else replaces."""
    out = copy.deepcopy(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        elif isinstance(value, list) and _id_list(out.get(key)) and all(isinstance(x, dict) and "id" in x for x in value):
            out[key] = _merge_ids(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _diff_ids(base, full):
    """The id-list form of the change from `base` to `full`; None when they
    are the same. A changed order of existing items is not kept."""
    out = []
    full_ids = [x["id"] for x in full]
    by_id = {x["id"]: x for x in base}
    for b in base:
        if b["id"] not in full_ids:
            out.append({"id": b["id"], "remove": True})
    for i, item in enumerate(full):
        if item["id"] in by_id:
            sub = diff(by_id[item["id"]], item)
            if sub:
                out.append({"id": item["id"], **sub})
        else:
            out.append({**copy.deepcopy(item), "after": full_ids[i - 1] if i else None})
    return out or None


def diff(base, full):
    """The part of `full` that differs from `base`, so that merge(base, diff) == full
    for every key `full` has."""
    out = {}
    for key, value in full.items():
        if key not in base:
            out[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(base[key], dict):
            sub = diff(base[key], value)
            if sub:
                out[key] = sub
        elif _id_list(value) and _id_list(base[key]):
            sub = _diff_ids(base[key], value)
            if sub:
                out[key] = sub
        elif value != base[key]:
            out[key] = copy.deepcopy(value)
    return out


def standard():
    return read_json(defaults_path())


def _entries(value):
    """The dict items of a list, so a broken entry is skipped here and named
    by providers_problems()."""
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def url_ok(url):
    """An http(s) URL with a host name, not a placeholder such as https://..."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(str(url))
        host = parsed.hostname or ""
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(re.search(r"[A-Za-z0-9]", host)) and ".." not in host


def from_providers(data):
    """providers.json as the gateways, profiles and tiers the scripts use."""
    gateways, profiles = {}, {}
    for p in _entries(data.get("providers")):
        if not isinstance(p.get("id"), str):
            continue
        models = [m for m in _entries(p.get("models")) if isinstance(m.get("id"), str)]
        names = {m["id"]: m.get("name") or m["id"] for m in models}
        if not p.get("base_url"):
            gateways[p["id"]] = {"kind": "anthropic"}
        else:
            gateways[p["id"]] = {"kind": "anthropic-compatible", "base_url": p["base_url"], "auth": p.get("auth"),
                                 "token_env": p.get("token_env"),
                                 "models": {names[m["id"]]: {"id": m["id"], "context": m.get("context")}
                                            for m in models}}
        for m in models:
            name = names[m["id"]]
            profile = {"gateway": p["id"], "model": m["id"] if not p.get("base_url") else name}
            if p.get("base_url"):
                roles = m.get("roles") if isinstance(m.get("roles"), dict) else {}
                profile["roles"] = {r: roles.get(r, name) for r in ROLES}
            if "agent" in m:
                profile["agent"] = m["agent"]
            profiles[name] = profile
    tiers = data.get("tiers") if isinstance(data.get("tiers"), dict) else {}
    return {"gateways": gateways, "profiles": profiles, "tiers": copy.deepcopy(tiers)}


def providers_problems(data):
    """Problems in providers.json, in its own terms."""
    if not isinstance(data, dict):
        return ["providers.json must be an object with providers and tiers"]
    problems = [f"providers.json: unknown key {k!r}; it holds providers and tiers" for k in data
                if k not in ("providers", "tiers")]
    providers = data.get("providers")
    if not isinstance(providers, list) or not providers:
        problems.append("providers.json: providers must list at least one provider")
        providers = []
    ids, names = set(), set()
    for i, p in enumerate(providers, 1):
        if not isinstance(p, dict) or not isinstance(p.get("id"), str) or not NAME.match(p["id"]):
            problems.append(f"provider {i}: needs an id of letters, digits, '.', '_' and '-'")
            continue
        where = f"provider {p['id']}"
        if p["id"] in ids:
            problems.append(f"{where}: another provider has the same id")
        ids.add(p["id"])
        problems += [f"{where}: unknown key {k!r}" for k in p if k not in PROVIDER_KEYS]
        compatible = bool(p.get("base_url"))
        if compatible:
            if not url_ok(p["base_url"]):
                problems.append(f"{where}: base_url must be the provider's http:// or https:// address, "
                                f"not {p['base_url']!r}")
            if p.get("auth") not in AUTHS:
                problems.append(f"{where}: auth must be one of {', '.join(AUTHS)}")
            if not ENV_NAME.match(str(p.get("token_env", ""))):
                problems.append(f"{where}: token_env must name the environment variable that holds the key "
                                f"(the name only, never the key)")
        else:
            problems += [f"{where}: {k} applies only to a provider with base_url" for k in ("auth", "token_env")
                         if k in p]
        models = p.get("models")
        if not isinstance(models, list) or not models:
            problems.append(f"{where}: models must list at least one model")
            continue
        own = {m.get("name") or m.get("id") for m in models if isinstance(m, dict)}
        for j, m in enumerate(models, 1):
            if not isinstance(m, dict) or not isinstance(m.get("id"), str) or not m["id"].strip():
                problems.append(f"{where}: model {j} needs an id, the model the provider knows")
                continue
            name = m.get("name") or m["id"]
            mwhere = f"{where}: model {m['id']}"
            problems += [f"{mwhere}: unknown key {k!r}" for k in m if k not in MODEL_ENTRY_KEYS]
            if not NAME.match(str(name)):
                problems.append(f"{mwhere}: needs a name of letters, digits, '.', '_' and '-'; tiers use it")
            elif name in names:
                problems.append(f"{mwhere}: the name {name} is taken by another model")
            names.add(name)
            if compatible:
                if not isinstance(m.get("context"), int) or isinstance(m["context"], bool) or m["context"] <= 0:
                    problems.append(f"{mwhere}: context must be the model's context size in tokens")
            elif "context" in m or "roles" in m:
                problems.append(f"{mwhere}: context and roles apply only to a provider with base_url")
            roles = m.get("roles", {})
            if not isinstance(roles, dict):
                problems.append(f"{mwhere}: roles must map opus, sonnet and haiku to models of {p['id']}")
                continue
            for role, target in roles.items():
                if role not in ROLES:
                    problems.append(f"{mwhere}: roles: {role!r} is not one of {', '.join(ROLES)}")
                elif target not in own:
                    problems.append(f"{mwhere}: roles: {role} names {target!r}, which is not a model of {p['id']}")
    tiers = data.get("tiers")
    if not isinstance(tiers, dict):
        problems.append(f"providers.json: tiers must map {', '.join(TIERS)} to lists of model names")
        tiers = {}
    for tier in TIERS:
        if tier not in tiers:
            problems.append(f"providers.json: tiers: {tier} is missing")
    for tier, listed in tiers.items():
        if tier not in TIERS:
            problems.append(f"providers.json: tiers: unknown tier {tier!r}; use {', '.join(TIERS)}")
        elif not isinstance(listed, list) or not listed:
            problems.append(f"providers.json: tiers: {tier} must list at least one model")
        else:
            problems += [f"providers.json: tiers: {tier} names {n!r}, which no provider has" for n in listed
                         if n not in names]
    return problems


def _model_ids(url, headers, opener):
    """Every model id the provider lists at url, following Anthropic's pages (has_more, last_id)."""
    import urllib.parse
    import urllib.request
    ids, after = [], None
    for _ in range(20):
        query = {"limit": 1000, **({"after_id": after} if after else {})}
        request = urllib.request.Request(f"{url}?{urllib.parse.urlencode(query)}", headers=headers)
        with opener(request, timeout=15) as response:
            page = json.loads(response.read().decode("utf-8"))
        data = page.get("data") if isinstance(page, dict) else None
        if not isinstance(data, list):
            raise ValueError("the answer has no data list")
        ids += [m["id"] for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)]
        if not (page.get("has_more") and page.get("last_id")):
            return ids
        after = page["last_id"]
    return ids


def model_lists(cfg, env=None, opener=None):
    """For each anthropic-compatible gateway's model: (gateway, profile name, model id, state, why). state is
    listed, not listed or unknown. The key is read from the gateway's token_env and only sent to its base_url."""
    import urllib.error
    import urllib.request
    env = os.environ if env is None else env
    opener = opener or urllib.request.urlopen
    out = []
    for gw_name, gw in sorted(cfg.get("gateways", {}).items()):
        if gw.get("kind") != "anthropic-compatible":
            continue
        models = sorted((name, m.get("id", name)) for name, m in (gw.get("models") or {}).items())
        url = gw["base_url"].rstrip("/") + "/v1/models"
        token = env.get(gw.get("token_env") or "")
        ids, why = None, ""
        if not token:
            why = f"token variable {gw.get('token_env')} is not set"
        else:
            headers = {"anthropic-version": "2023-06-01", "Accept": "application/json"}
            if gw.get("auth") == "x-api-key":
                headers["x-api-key"] = token
            else:
                headers["Authorization"] = f"Bearer {token}"
            try:
                ids = set(_model_ids(url, headers, opener))
            except urllib.error.HTTPError as e:
                why = f"{url} answered HTTP {e.code}"
            except (urllib.error.URLError, OSError, ValueError) as e:
                why = f"no model list from {url}: {getattr(e, 'reason', e)}"
        for name, model_id in models:
            if ids is None:
                out.append((gw_name, name, model_id, "unknown", why))
            else:
                out.append((gw_name, name, model_id, "listed" if model_id in ids else "not listed",
                            "" if model_id in ids else f"{url} lists {len(ids)} models, not this one"))
    return out


def with_providers(cfg):
    """`cfg` with the models of providers.json, when the file exists."""
    if not os.path.exists(providers_path()):
        return cfg
    return {**cfg, **from_providers(read_settings(providers_path()))}


def models_file_problems(repo=None):
    """Problems in providers.json, and model settings left in config.json or
    the project's file, where they would never be read."""
    problems = []
    if os.path.exists(providers_path()):
        problems += providers_problems(read_settings(providers_path()))
    for path in [user_path()] + ([project_path(repo)] if repo else []):
        held = [k for k in MODEL_KEYS if k in read_settings(path)]
        if held:
            problems.append(f"{path}: {', '.join(held)} belong in {providers_path()}; remove them here")
    return problems


def settings_problems(cfg, repo=None, saved=None, skills=None, project=False):
    """validate(), with the models file's own problems first. While that file
    has problems, the rest is checked against the standard models, so each
    model problem is named once, in the file's terms."""
    file_problems = models_file_problems(repo)
    if file_problems:
        std = standard()
        cfg = {**cfg, **{k: std[k] for k in MODEL_KEYS}}
    return file_problems + validate(cfg, saved=saved, skills=skills, project=project)


def _without_models(settings):
    """A user or project file without model settings, which only providers.json holds."""
    return {k: v for k, v in settings.items() if k not in MODEL_KEYS}


def load(repo=None):
    """Settings in effect: standard, then user, then the project's when `repo`
    is given; the models from providers.json."""
    cfg = with_providers(merge(standard(), _without_models(read_settings(user_path()))))
    if repo:
        cfg = merge(cfg, _without_models(read_settings(project_path(repo))))
        cfg.setdefault("repo", repo)
        cfg.setdefault("workspace", repo.split("/", 1)[1])
    return cfg


def _placeholders(fmt):
    return [field for _, field, _, _ in string.Formatter().parse(fmt) if field is not None]


def validate_launch(cfg):
    """Problems in the settings launch.py needs: gateways, profiles, launch."""
    problems = []
    gateways = cfg.get("gateways", {})
    profiles = cfg.get("profiles", {})
    for name, g in gateways.items():
        if g.get("kind") not in KINDS:
            problems.append(f"gateway {name}: unknown kind {g.get('kind')!r}")
            continue
        if g["kind"] == "anthropic":
            continue
        if not url_ok(g.get("base_url", "")):
            problems.append(f"gateway {name}: base_url must be an http:// or https:// address")
        if not ENV_NAME.match(str(g.get("token_env", ""))):
            problems.append(f"gateway {name}: token_env must be an environment variable name")
        if g.get("auth") not in AUTHS:
            problems.append(f"gateway {name}: auth must be one of {', '.join(AUTHS)}")
        for alias, m in g.get("models", {}).items():
            if not m.get("id"):
                problems.append(f"gateway {name}: model {alias} has no id")
            if not isinstance(m.get("context"), int) or m["context"] <= 0:
                problems.append(f"gateway {name}: model {alias} needs a positive context size")
    for name, p in profiles.items():
        if adapters.kind_of(p) not in adapters.KINDS:
            problems.append(f"profile {name}: agent {adapters.kind_of(p)!r} is not supported; "
                            f"supported: {', '.join(adapters.KINDS)}")
        g = gateways.get(p.get("gateway"))
        if g is None:
            problems.append(f"profile {name}: gateway {p.get('gateway')!r} does not exist")
            continue
        if g.get("kind") == "anthropic":
            if not p.get("model"):
                problems.append(f"profile {name}: model is empty")
            continue
        models = g.get("models", {})
        if p.get("model") not in models:
            problems.append(f"profile {name}: model {p.get('model')!r} is not on gateway {p['gateway']}")
        for role in ROLES:
            if p.get("roles", {}).get(role) not in models:
                problems.append(f"profile {name}: role {role} has no model of gateway {p['gateway']}")

    tiers = cfg.get("tiers", {})
    if not isinstance(tiers, dict):
        problems.append("tiers must map low, mid and high to lists of profiles")
        tiers = {}
    for tier, names in tiers.items():
        if tier not in TIERS:
            problems.append(f"tiers: unknown tier {tier!r}; use {', '.join(TIERS)}")
            continue
        if not isinstance(names, list) or not names:
            problems.append(f"tiers: {tier} must list at least one profile")
            continue
        for name in names:
            if name not in profiles:
                problems.append(f"tiers: {tier} names profile {name!r}, which does not exist")

    launch = cfg.get("launch", {})
    problems += [f"launch: unknown key {k!r}" + ("; name the profile when an agent starts" if k == "profile" else "")
                 for k in launch if k != "permission"]
    if launch.get("permission") not in PERMISSIONS:
        problems.append(f"launch: permission must be one of {', '.join(PERMISSIONS)}")
    return problems


def validate(cfg, saved=None, skills=None, project=False):
    """Problems in merged settings, as lines. `machines` (label -> info) and
    `skills` (ref -> path) are checked against when given."""
    problems = []
    allowed = SECTIONS + (PROJECT_KEYS if project else [])
    for key in cfg:
        if key not in allowed:
            problems.append(f"unknown setting {key!r}")
    problems += validate_launch(cfg)
    profiles = cfg.get("profiles", {})

    dirs = cfg.get("plugin_dirs", [])
    if not isinstance(dirs, list) or not all(isinstance(d, str) for d in dirs):
        problems.append("plugin_dirs must be a list of directory paths")
    else:
        for d in dirs:
            if not os.path.isfile(os.path.join(os.path.expanduser(d), ".claude-plugin", "plugin.json")):
                problems.append(f"plugin_dirs: {d} has no .claude-plugin/plugin.json")
            elif is_self(d):
                problems.append(f"plugin_dirs: {d} is agent-foreman itself; its skills are the foreman's, "
                                f"not the agents'")

    problems += loops.validate_loop(cfg.get("loop", {}))

    overrides = cfg.get("skills", {})
    if not isinstance(overrides, dict):
        problems.append("skills must map a default skill's name to the skill that replaces it")
    else:
        for name, ref in overrides.items():
            if name not in loops.KIT:
                problems.append(f"skills: {name!r} is not a default skill ({', '.join(loops.KIT)})")
            elif not (isinstance(ref, str) and ref.strip()):
                problems.append(f"skills: {name} must name the skill that replaces it")
    if isinstance(cfg.get("loop"), dict) and isinstance(cfg.get("tiers"), dict) and not loops.validate_loop(cfg["loop"]):
        problems += candidate_problems(cfg)

    diff = cfg.get("difficulty", {})
    for key in ("lines", "files", "top_dirs", "fix_days"):
        if not isinstance(diff.get(key), int) or isinstance(diff.get(key), bool) or diff[key] <= 0:
            problems.append(f"difficulty: {key} must be a positive whole number")
    for key in ("fix_words", "critical", "public", "docs_tests", "docs"):
        value = diff.get(key)
        if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
            problems.append(f"difficulty: {key} must be a list of patterns or words")
    stage_names = loops.stage_ids(cfg.get("loop", {})) if isinstance(cfg.get("loop"), dict) else []

    refs = list(cfg.get("bundle", {}).get("skills", []))
    if not isinstance(cfg.get("bundle", {}).get("skills", []), list):
        problems.append("bundle: skills must be a list")
        refs = []
    seen = {}
    for ref in refs:
        short = str(ref).split(":")[-1]
        if seen.get(short, ref) != ref:
            problems.append(f"skills {seen[short]} and {ref} would share the name {short} in the bundle")
        seen[short] = ref
        if skills is not None and ref not in skills:
            problems.append(f"skill {ref!r} is not available on this machine")

    labels = cfg.get("labels", {})
    formats = {"default": labels.get("default", "")}
    for event, fmt in labels.get("events", {}).items():
        if event not in stage_names and event not in LABEL_EVENTS:  # a tab follows the stages, not the steps
            problems.append(f"labels: {event!r} is neither a stage nor one of {', '.join(LABEL_EVENTS)}")
        formats[event] = fmt
    for event, fmt in formats.items():
        if not str(fmt).strip():
            problems.append(f"labels: {event} is empty")
            continue
        try:
            fields = _placeholders(str(fmt))
        except ValueError as e:
            problems.append(f"labels: {event}: {e}")
            continue
        for field in fields:
            if field not in PLACEHOLDERS:
                problems.append(f"labels: {event} uses {{{field}}}; use only "
                                + ", ".join("{" + p + "}" for p in PLACEHOLDERS))

    report = cfg.get("report", {})
    if not str(report.get("template", "")).strip():
        problems.append("report: template is empty")
    for key in ("language", "address"):
        if not isinstance(report.get(key, ""), str):
            problems.append(f"report: {key} must be text")

    ops = cfg.get("ops", {})
    for key in ("check_minutes", "report_minutes", "stall_minutes"):
        if not isinstance(ops.get(key), int) or isinstance(ops[key], bool) or ops[key] <= 0:
            problems.append(f"ops: {key} must be a positive whole number")
    if (isinstance(ops.get("report_minutes"), int) and isinstance(ops.get("stall_minutes"), int)
            and ops["stall_minutes"] <= ops["report_minutes"]):
        problems.append("ops: stall_minutes must be more than report_minutes, or every report interval is a stall")
    backoff = ops.get("backoff", {})
    if not isinstance(backoff.get("first_hours"), (int, float)) or backoff["first_hours"] <= 0:
        problems.append("ops: backoff.first_hours must be a positive number")
    if not isinstance(backoff.get("factor"), (int, float)) or backoff["factor"] < 1:
        problems.append("ops: backoff.factor must be 1 or more")
    batch = ops.get("batch")
    if batch is not None and (not isinstance(batch, int) or isinstance(batch, bool) or batch <= 0):
        problems.append("ops: batch must be a positive whole number or null")
    if ops.get("placement") not in PLACEMENTS:
        problems.append(f"ops: placement must be one of {', '.join(PLACEMENTS)}")
    if not isinstance(ops.get("disk_check"), bool):
        problems.append("ops: disk_check must be true or false")
    floor = ops.get("disk_min_free_gb")
    if not isinstance(floor, (int, float)) or isinstance(floor, bool) or floor < 0:
        problems.append("ops: disk_min_free_gb must be a number of gigabytes, 0 or more")
    if not isinstance(ops.get("after_merge", []), list):
        problems.append("ops: after_merge must be a list of steps")

    if project:
        tests = cfg.get("tests", {})
        if not isinstance(tests, dict) or any(k != "full" for k in tests):
            problems.append("project: tests may only name full, the project's full test command")
        elif "full" in tests and not (isinstance(tests["full"], str) and tests["full"].strip()):
            problems.append("project: tests.full must be a command")
        problems += [f"project: {p}" for p in gates.project_check_problems(cfg.get("gate", []))]
        if not isinstance(cfg.get("post_answers", False), bool):
            problems.append("project: post_answers must be true or false")
        if not REPO.match(str(cfg.get("repo", ""))):
            problems.append("project: repo must look like owner/name")
        if not str(cfg.get("workspace", "")).strip():
            problems.append("project: workspace label is empty")
        hosts = cfg.get("machines")
        if not isinstance(hosts, dict) or not hosts:
            problems.append("project: machines must name at least one machine and the project path there")
            hosts = {}
        for label, path in hosts.items():
            if not str(path).startswith(("/", "~")):
                problems.append(f"project: machine {label}: project path must start with / or ~")
            if label == LOCAL or saved is None:
                continue
            if label not in saved:
                problems.append(f"project: machine {label} is not a saved herdr machine (herdr machine list)")
            elif not saved[label]["enabled"]:
                problems.append(f"project: machine {label} is disabled in herdr")
    return problems


def herdr_machines():
    """Saved herdr machines: label -> {"target": ssh target, "enabled": bool}."""
    if shutil.which("herdr") is None:
        print("herdr is not on PATH: install it (https://herdr.dev) and run again.", file=sys.stderr)
        raise SystemExit(EXIT_SETUP_NEEDED)
    out = subprocess.run(["herdr", "machine", "list"], capture_output=True, text=True, check=True)
    machines = {}
    for line in out.stdout.splitlines():
        cols = line.split("\t")
        if len(cols) >= 5:
            machines[cols[1]] = {"target": cols[2], "enabled": cols[4].strip() == "enabled"}
    return machines


# Runs on the machine, in its login shell: argv = path, owner/repo, agent
# executable, token variable names. Prints what a project machine needs.
MACHINE_PROBE = """
import json, os, re, shutil, subprocess, sys
path, repo, exe, names = os.path.expanduser(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4:]
out = {"checkout": os.path.isdir(os.path.join(path, ".git")), "origin": "", "origin_matches": False}
if out["checkout"]:
    r = subprocess.run(["git", "-C", path, "remote", "get-url", "origin"], capture_output=True, text=True)
    out["origin"] = r.stdout.strip()
    url = re.sub(r"\\.git$", "", out["origin"].rstrip("/"))
    out["origin_matches"] = bool(re.search(r"[:/]" + re.escape(repo) + "$", url, re.I))
out["tools"] = {t: bool(shutil.which(t)) for t in exe.split(",") + ["git", "gh", "python3"]}
out["tokens"] = {n: bool(os.environ.get(n)) for n in names}
print(json.dumps(out))
"""


def token_names(cfg):
    """The token variables the tiers' profiles need, by name."""
    names = []
    for tier in cfg.get("tiers", {}).values():
        for profile in tier:
            gateway = cfg["gateways"].get(cfg["profiles"].get(profile, {}).get("gateway"), {})
            if gateway.get("token_env") and gateway["token_env"] not in names:
                names.append(gateway["token_env"])
    return names


def machine_state(label, path, repo, cfg, machines=None):
    """Whether a machine is ready for the project's agents: the checkout at
    `path` is there and its origin is `repo`; the agent program, git, gh and
    python3 are on PATH; the tiers' token variables are set (names only).
    A remote machine is checked inside its login shell, as agents start
    there. Returns the probe's answer with "ready" and "problems"."""
    from remote import remote_argv
    tiered = {p for tier in cfg.get("tiers", {}).values() for p in tier if p in cfg.get("profiles", {})}
    exes = sorted({adapters.get(adapters.kind_of(cfg["profiles"][p])).EXECUTABLE for p in tiered}
                  or {adapters.get(adapters.DEFAULT).EXECUTABLE})
    args = [path, repo, ",".join(exes), *token_names(cfg)]
    if label == LOCAL:
        argv = [sys.executable, "-c", MACHINE_PROBE, *args]
    else:
        machines = herdr_machines() if machines is None else machines
        if label not in machines:
            raise ValueError(f"{label} is not a saved herdr machine")
        argv = remote_argv(machines[label]["target"], ["python3", "-c", MACHINE_PROBE, *args])
    out = subprocess.run(argv, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"{label}: {out.stderr.strip()[-300:]}")
    state = json.loads(out.stdout.strip().splitlines()[-1])  # a login shell may print lines first
    problems = []
    if not state["checkout"]:
        problems.append(f"no git checkout at {path}")
    elif not state["origin_matches"]:
        problems.append(f"the checkout's origin is {state['origin'] or 'not set'}, not {repo}")
    problems += [f"{tool} is not on PATH in the login shell" for tool, ok in state["tools"].items() if not ok]
    problems += [f"token variable {name} is not set in the login shell" for name, ok in state["tokens"].items()
                 if not ok]
    return {**state, "ready": not problems, "problems": problems}


def is_self(plugin_dir):
    """Whether a plugin directory is this plugin (by path or by manifest name)."""
    path = os.path.realpath(os.path.expanduser(plugin_dir))
    if path == os.path.realpath(SELF_DIR):
        return True
    manifest = read_json(os.path.join(path, ".claude-plugin", "plugin.json"))
    return manifest.get("name") == SELF


def session_plugin_dirs(cmdline=None):
    """The --plugin-dir directories the Claude Code session running this script
    was started with (a `claude` shell wrapper's flags show up here too), kept
    to real plugin directories, agent-foreman left out."""
    if cmdline is None:
        pid = os.environ.get("CLAUDE_PID", "")
        if not pid.isdigit():
            return []
        proc = f"/proc/{pid}/cmdline"
        if os.path.exists(proc):
            with open(proc, "rb") as f:
                args = [a.decode() for a in f.read().split(b"\0") if a]
        else:
            out = subprocess.run(["ps", "-o", "command=", "-p", pid], capture_output=True, text=True)
            args = out.stdout.split()
    else:
        args = list(cmdline)
    found = []
    for i, a in enumerate(args):
        if a == "--plugin-dir" and i + 1 < len(args):
            d = args[i + 1]
        elif a.startswith("--plugin-dir="):
            d = a.split("=", 1)[1]
        else:
            continue
        if os.path.isfile(os.path.join(os.path.expanduser(d), ".claude-plugin", "plugin.json")) \
                and not is_self(d) and d not in found:
            found.append(d)
    return found


def plugin_list(plugin_dirs=()):
    """Claude Code's plugin list, with the settings' `plugin_dirs` loaded the
    way `claude --plugin-dir` loads them for a session."""
    argv = ["claude"]
    for d in plugin_dirs:
        argv += ["--plugin-dir", os.path.expanduser(d)]
    out = subprocess.run(argv + ["plugin", "list", "--json"], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def local_skills(plugins=None, user_skills_dir=None):
    """Skills this machine's Claude Code can load: ref -> skill directory.

    A plugin skill is `plugin:skill`; a plugin with `SKILL.md` at its root and
    no `skills/` is one skill, `plugin:plugin`. A user skill in
    ~/.claude/skills is `skill`. A link that points nowhere is left out, and
    so is this skill, however it is installed.
    """
    plugins = plugin_list() if plugins is None else plugins
    user_skills_dir = user_skills_dir or os.path.join(
        os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude"), "skills")
    found = {}
    for p in plugins:
        if not p.get("enabled") or not p.get("installPath"):
            continue
        name = p["id"].split("@", 1)[0]
        if name == SELF or is_self(p["installPath"]):
            continue
        root = os.path.join(p["installPath"], "skills")
        if not os.path.isdir(root):
            if os.path.isfile(os.path.join(p["installPath"], "SKILL.md")):
                found[f"{name}:{name}"] = p["installPath"]
            continue
        for entry in sorted(os.listdir(root)):
            if os.path.isfile(os.path.join(root, entry, "SKILL.md")):
                found[f"{name}:{entry}"] = os.path.join(root, entry)
    if os.path.isdir(user_skills_dir):
        for entry in sorted(os.listdir(user_skills_dir)):
            path = os.path.realpath(os.path.join(user_skills_dir, entry))
            if os.path.isfile(os.path.join(path, "SKILL.md")) and entry != SELF and path != os.path.realpath(SELF_DIR):
                found[entry] = path
    return found


def whole_plugins(cfg, plugins=None):
    """Plugin name -> its entry in the settings' plugin_dirs, for each plugin
    loaded from there."""
    entries = {os.path.realpath(os.path.expanduser(d)): d for d in plugin_dirs(cfg)}
    plugins = plugin_list(plugin_dirs(cfg)) if plugins is None else plugins
    out = {}
    for p in plugins:
        entry = entries.get(os.path.realpath(p.get("installPath") or ""))
        if p.get("scope") == "session" and p.get("enabled") and entry:
            out[p["id"].split("@", 1)[0]] = entry
    return out


def installed_elsewhere(plugins=None):
    """(plugin id, directory) of each plugin installed on this machine but not
    enabled for this folder, such as one installed for another project."""
    plugins = plugin_list() if plugins is None else plugins
    enabled_names = {p["id"].split("@", 1)[0] for p in plugins if p.get("enabled")}
    return [(p["id"], p["installPath"]) for p in plugins
            if not p.get("enabled") and p.get("installPath") and p["id"].split("@", 1)[0] not in enabled_names
            and not is_self(p["installPath"])]


def project_skills(cfg, extra=()):
    """Every skill name the project's agents may need: bundle.skills, each
    loop stage's skills, then `extra`, without repeats, in that order."""
    refs = list(cfg.get("bundle", {}).get("skills", []))
    for which in loops.LOOPS:
        for st in cfg.get("loop", {}).get(which, []):
            refs += st.get("skills", [])
    refs += list(extra)
    seen = []
    for ref in refs:
        if ref not in seen:
            seen.append(ref)
    return seen


def role_tier(difficulty, role="lead", cfg=None):
    """The model tier a role takes for a task of that difficulty: the
    difficulty's tier raised by the role's `step` (loop.roles), capped at high.
    Standard: the red team and QA one above, every other role the same."""
    if difficulty not in TIERS:
        raise ValueError(f"difficulty must be one of {', '.join(TIERS)}")
    roles = (cfg or {}).get("loop", {}).get("roles", {})
    step = roles[role].get("step", 0) if role in roles else ROLE_STEP.get(role, 0)
    return TIERS[min(len(TIERS) - 1, TIERS.index(difficulty) + step)]


def lead_profile(cfg, difficulty):
    """The profile a lead starts with: the first of the difficulty's tier."""
    profiles = tier_profiles(cfg, difficulty)
    return profiles[0] if profiles else None


def role_candidates(cfg, difficulty, role, skip=(), lead=None):
    """The profiles a role may run on, in order: its tier and then each higher
    one, never a lower one, and never the lead's profile (`lead`: the one the
    lead really runs on; by default the first of the difficulty's tier), so
    the agents that check the work always run on another model than the one
    that built it."""
    lead = lead or lead_profile(cfg, difficulty)
    top = TIERS.index(role_tier(difficulty, role, cfg))
    out = []
    for tier in TIERS[top:]:
        out += [p for p in tier_profiles(cfg, tier, skip) if p not in out and p != lead]
    return out


def candidate_problems(cfg):
    """A difficulty whose lead has no profile, or whose checking role has no
    profile other than the lead's."""
    problems = []
    loop = cfg.get("loop", {})
    roles = sorted({s["actor"] for w in ("work", "check") for s in loop.get(w, [])
                    if isinstance(s, dict) and s.get("actor") in loop.get("roles", {})})
    for difficulty in TIERS:
        if not tier_profiles(cfg, difficulty):
            problems.append(f"tiers: {difficulty} has no profile for the lead")
            continue
        for role in roles:
            if not role_candidates(cfg, difficulty, role):
                problems.append(f"tiers: at {difficulty} difficulty, role {role} has no profile other than the lead's "
                                f"({lead_profile(cfg, difficulty)}); add one to tier {role_tier(difficulty, role, cfg)} "
                                f"or above")
    return problems


def tier_profiles(cfg, tier, skip=()):
    """The tier's profiles in order, without the skipped ones (a usage limit or
    a gateway error moves on to the next)."""
    return [p for p in cfg.get("tiers", {}).get(tier, []) if p not in skip]


def label(cfg, event, **values):
    """Tab label for an event or a stage, from the project's label formats."""
    fmt = cfg["labels"].get("events", {}).get(event) or cfg["labels"]["default"]
    fields = {p: "" for p in PLACEHOLDERS}
    fields.update({k: str(v) for k, v in values.items()})
    return " ".join(fmt.format(**fields).split())


def save(level, full, repo=None, saved=None, skills=None, dry_run=False):
    """Write the part of `full` (settings as they should be in effect at that
    level) that differs from the level below. Returns (path, written, problems).
    The models are never written here: they live in providers.json."""
    base = standard()
    if level == "project":
        base = merge(base, _without_models(read_settings(user_path())))
        path = project_path(repo)
    else:
        path = user_path()
    base = with_providers(base)
    written = diff(base, full)
    effective = merge(base, written)  # what loading the saved file gives, so the check sees what is stored
    if level == "project":
        effective.setdefault("repo", repo)
        effective.setdefault("workspace", repo.split("/", 1)[1])
    problems = settings_problems(effective, repo=repo if level == "project" else None, saved=saved, skills=skills,
                                 project=level == "project")
    held = [k for k in MODEL_KEYS if k in written]
    if held:
        problems.append(f"{', '.join(held)}: models are set in {providers_path()}, not saved here")
    if level == "project":
        written["repo"] = repo
    if not problems and not dry_run:
        write_json(path, written)
    return path, written, problems


def plugin_dirs(cfg):
    """The settings' plugin directories that exist; a wrong entry is reported by
    validate(), and left out here so the rest of the lookup still works."""
    dirs = cfg.get("plugin_dirs", [])
    if not isinstance(dirs, list):
        return []
    return [d for d in dirs if isinstance(d, str) and os.path.isdir(os.path.expanduser(d))]


def _cli(argv):
    ap = argparse.ArgumentParser(prog="config.py", description="agent-foreman settings")
    ap.add_argument("command", choices=["paths", "providers", "show", "check", "save", "check-machine", "profiles",
                                        "projects", "machines", "skills", "plugin-dir-candidates", "tier"])
    ap.add_argument("--init", action="store_true", help="providers: write the file from the standard when missing")
    ap.add_argument("rest", nargs="*", help="save: user or project; check-machine: MACHINE PATH")
    ap.add_argument("--plugin-dir", action="append", default=[], help="skills: a plugin directory to add")
    ap.add_argument("--project", metavar="OWNER/REPO")
    ap.add_argument("--difficulty", choices=TIERS)
    ap.add_argument("--role", default="lead")
    ap.add_argument("--lead", metavar="PROFILE", help="tier: the profile the task's lead runs on")
    ap.add_argument("--skip", default="", metavar="PROFILE,...")
    ap.add_argument("--task", default="<task>")
    ap.add_argument("--agent", default=adapters.DEFAULT, choices=adapters.KINDS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--models", action="store_true", help="check: ask each provider for its model list")
    args = ap.parse_args(argv)
    if args.project and not REPO.match(args.project):
        print(f"config.py: --project must look like owner/name, not {args.project!r}", file=sys.stderr)
        return 2

    if args.command == "paths":
        info = {"standard": defaults_path(), "user": user_path(), "providers": providers_path(), "state": state_dir(),
                "cache": cache_dir()}
        if args.project:
            info.update(project=project_path(args.project), ledger=ledger_path(args.project),
                        log=log_path(args.project), memory=memory_path(args.project))
        print(json.dumps(info, indent=2))
    elif args.command == "providers":
        path, created = providers_path(), False
        if args.init and not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            shutil.copyfile(providers_sample_path(), path)
            created = True
        problems = providers_problems(read_settings(path)) if os.path.exists(path) else []
        print(json.dumps({"path": path, "exists": os.path.exists(path), "created": created, "problems": problems},
                         indent=2, ensure_ascii=False))
        if problems:
            return EXIT_SETUP_NEEDED
    elif args.command == "show":
        print(json.dumps(load(args.project), indent=2, ensure_ascii=False))
    elif args.command == "check":
        cfg = load(args.project)
        problems = settings_problems(cfg, repo=args.project, saved=herdr_machines(), project=bool(args.project),
                                     skills=local_skills(plugin_list(plugin_dirs(cfg))))
        if args.project and not os.path.exists(project_path(args.project)):
            problems.insert(0, f"project {args.project} has no settings yet ({project_path(args.project)})")
        if args.models:
            for gw, name, model_id, state, why in model_lists(cfg):
                line = f"model {name} ({model_id}) at {gw}: {state}" + (f": {why}" if why else "")
                (problems.append(line) if state == "not listed" else print(line))
        for p in problems:
            print(p)
        if problems:
            return EXIT_SETUP_NEEDED
        print("ok")
    elif args.command == "save":
        level = args.rest[0] if len(args.rest) == 1 else None
        if level not in ("user", "project") or (level == "project" and not args.project):
            print("config.py: save needs user, or project with --project OWNER/REPO", file=sys.stderr)
            return 2
        full = json.load(sys.stdin)
        dirs = plugin_dirs(full) if "plugin_dirs" in full else plugin_dirs(load(args.project))
        path, written, problems = save(level, full, repo=args.project, saved=herdr_machines(),
                                       skills=local_skills(plugin_list(dirs)), dry_run=args.dry_run)
        for p in problems:
            print(p)
        if problems:
            return EXIT_SETUP_NEEDED
        print(json.dumps({"path": path, "written": written, "dry_run": args.dry_run}, indent=2,
                         ensure_ascii=False))
    elif args.command == "check-machine":
        if len(args.rest) != 2 or not args.project:
            print("config.py: check-machine needs MACHINE PATH and --project OWNER/REPO", file=sys.stderr)
            return 2
        try:
            state = machine_state(*args.rest, args.project, load(args.project))
        except (ValueError, RuntimeError) as e:
            print(f"config.py: {e}", file=sys.stderr)
            return 1
        print(json.dumps(state, indent=2))
        return 0 if state["ready"] else EXIT_SETUP_NEEDED
    elif args.command == "profiles":
        cfg = load(args.project)
        for name, p in cfg["profiles"].items():
            roles = p.get("roles")
            role_text = "  roles " + "/".join(roles[r] for r in ROLES) if roles else ""
            print(f"{name:12} {p['gateway']:24} {p['model']}{role_text}")
    elif args.command == "projects":
        root = os.path.join(state_dir(), "projects")
        for entry in sorted(os.listdir(root)) if os.path.isdir(root) else []:
            p = read_settings(os.path.join(root, entry, "project.json"))
            if p.get("repo"):
                print(f"{p['repo']:40} {' '.join(p.get('machines', {}))}")
    elif args.command == "tier":
        if not args.difficulty:
            print("config.py: tier needs --difficulty low|mid|high", file=sys.stderr)
            return 2
        cfg = load(args.project)
        roles = list(dict.fromkeys(["lead", *cfg.get("loop", {}).get("roles", {}), *ROLE_STEP]))
        if args.role not in roles:
            print(f"config.py: --role must be one of {', '.join(roles)}, not {args.role!r}", file=sys.stderr)
            return 2
        tier = role_tier(args.difficulty, args.role, cfg)
        skip = [x for x in args.skip.split(",") if x]
        profiles = (tier_profiles(cfg, tier, skip) if args.role == "lead"
                    else role_candidates(cfg, args.difficulty, args.role, skip, lead=args.lead))
        print(json.dumps({"tier": tier, "profiles": profiles, "pick": profiles[0] if profiles else None}))
        if not profiles:
            return EXIT_SETUP_NEEDED
    elif args.command == "machines":
        for name, m in herdr_machines().items():
            print(f"{name:24} {m['target']:32} {'enabled' if m['enabled'] else 'disabled'}")
    elif args.command == "plugin-dir-candidates":
        for d in session_plugin_dirs():
            print(d)
        for plugin_id, d in installed_elsewhere():
            print(d)
            print(f"config.py: {d} is {plugin_id}, installed but not enabled here; a cache path like it changes "
                  f"when the plugin updates", file=sys.stderr)
    elif args.command == "skills":
        dirs = plugin_dirs(load(args.project)) + [os.path.abspath(os.path.expanduser(d)) for d in args.plugin_dir]
        for ref, path in local_skills(plugin_list(dirs)).items():
            print(f"{ref:44} {path}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
