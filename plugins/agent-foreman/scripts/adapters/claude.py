"""Claude Code adapter."""
import glob
import json
import os

from .base import NEVER_MERGE, PLUGIN, NoTranscript, TokenMissing

KIND = "claude"
HERDR_KIND = "claude"
EXECUTABLE = "claude"
GATEWAY_KINDS = ["anthropic", "anthropic-compatible"]
ROLES = ["opus", "sonnet", "haiku"]
HEARTBEAT = 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/heartbeat.py"'
NEVER = [f"Bash({NEVER_MERGE}:*)"]
EDIT_TOOLS = ["Edit", "Write", "NotebookEdit"]
TRUST_SCREEN = "Accessing workspace"
TRUST_KEYS = ["Down", "Enter"]

# Variables a gateway may set. They are cleared first, so a value inherited
# from the parent shell never leaks into another gateway's agent.
GATEWAY_VARS = [
    "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS", "CLAUDE_CODE_AUTO_COMPACT_WINDOW",
]


def gateway_env(gateway, profile, environ):
    """Return (variables to set, variable names to clear) for one profile."""
    clear = set(GATEWAY_VARS)
    if gateway.get("kind") == "anthropic":
        return {}, clear
    token = environ.get(gateway["token_env"])
    if not token:
        raise TokenMissing(gateway["token_env"])
    models = gateway["models"]
    main = models[profile["model"]]
    env = {
        "ANTHROPIC_BASE_URL": gateway["base_url"],
        "ANTHROPIC_MODEL": main["id"],
        "CLAUDE_CODE_MAX_CONTEXT_TOKENS": str(main["context"]),
        "CLAUDE_CODE_AUTO_COMPACT_WINDOW": str(main["context"]),
    }
    for role in ROLES:
        env[f"ANTHROPIC_DEFAULT_{role.upper()}_MODEL"] = models[profile["roles"][role]]["id"]
    if gateway["auth"] == "bearer":
        env["ANTHROPIC_AUTH_TOKEN"] = token
    else:
        env["ANTHROPIC_API_KEY"] = token
        clear.discard("ANTHROPIC_API_KEY")
    clear -= set(env)
    return env, clear


def command(cfg, profile_name, name=None, session_id=None, bundle=None, environ=None,
            print_mode=False, no_edit=False, resume=None, plugin_dirs=()):
    """Return (argv, variables to set, variable names to clear). In print mode
    the agent answers one prompt read from stdin and prints JSON (`claude -p`).
    Either way it runs in the folder it is started in, its own clone. `resume`
    continues an earlier session with its conversation, in the folder it ran in.
    `plugin_dirs` are loaded whole after the bundle. `no_edit` denies the edit
    tools; the tools in NEVER are always denied."""
    profile = cfg["profiles"][profile_name]
    gateway = cfg["gateways"][profile["gateway"]]
    env, clear = gateway_env(gateway, profile, os.environ if environ is None else environ)
    model = profile["model"] if gateway.get("kind") == "anthropic" else gateway["models"][profile["model"]]["id"]
    argv = [EXECUTABLE]
    if print_mode:
        argv += ["-p", "--output-format", "json"]
    if name:
        argv += ["--name", name]
    if resume:
        argv += ["--resume", resume]
    elif session_id:
        argv += ["--session-id", session_id]
    argv += ["--model", model]
    if cfg["launch"]["permission"] == "bypass":
        argv.append("--dangerously-skip-permissions")
    if bundle:
        argv += ["--plugin-dir", bundle]
    for d in plugin_dirs:
        argv += ["--plugin-dir", d]
    argv += ["--disallowedTools", ",".join([*(EDIT_TOOLS if no_edit else []), *NEVER])]
    return argv, env, clear


def prepare(workdir, bundle):
    """Claude Code finds everything through --plugin-dir; the folder needs nothing."""


def parse_print(text):
    """The parts of a `claude -p --output-format json` result the foreman uses."""
    try:
        data = json.loads(text)
    except ValueError:
        return {"ok": False, "result": text.strip()[-500:], "session_id": None, "cost": None, "denials": []}
    return {
        "ok": not data.get("is_error") and data.get("subtype") == "success",
        "result": data.get("result", ""),
        "session_id": data.get("session_id"),
        "cost": data.get("total_cost_usd"),
        "denials": data.get("permission_denials") or [],
    }


def answer_file(text):
    """`claude -p --output-format json` prints the answer file as it is."""
    return text


def skill_name(ref):
    return f"{PLUGIN}:{ref.split(':')[-1]}"


def bundle_layout(skills):
    """A Claude Code plugin at the bundle's root that holds the skills and the
    heartbeat hooks; `--plugin-dir` loads it. The hooks run the bundle's
    scripts/heartbeat.py, which writes only when launch.py --status set
    AF_STATUS_FILE."""
    files = {".claude-plugin/plugin.json": json.dumps({
        "name": PLUGIN,
        "version": "1.0.0",
        "description": "Skills and scripts agent-foreman gives its agents",
    }, indent=2).encode() + b"\n"}
    files["hooks/hooks.json"] = json.dumps({"hooks": {
        "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": HEARTBEAT + " post"}]}],
        "Stop": [{"hooks": [{"type": "command", "command": HEARTBEAT + " stop"}]}],
    }}, indent=2).encode() + b"\n"
    for short, contents in skills.items():
        for rel, data in contents.items():
            files[f"skills/{short}/{rel}"] = data
    return files


def _projects(root):
    return root or os.path.join(
        os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude"), "projects")


def _starts_turn(entry):
    message = entry.get("message")
    if entry.get("isMeta") or not isinstance(message, dict):
        return False
    content = message.get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        blocks = [b for b in content if isinstance(b, dict)]
        return any(b.get("type") == "text" for b in blocks) and not any(b.get("type") == "tool_result" for b in blocks)
    return False


def turns(lines):
    """The assistant text blocks of each turn, as a list of lists. A turn
    starts at a typed prompt; tool results, meta entries and subagent entries
    do not start one."""
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict) or entry.get("isSidechain"):
            continue
        if entry.get("type") == "user" and _starts_turn(entry):
            out.append([])
        elif entry.get("type") == "assistant":
            message = entry.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        if not out:
                            out.append([])
                        out[-1].append(text)
    return out


def last_answers(session_id, n=1, root=None):
    """The final text of each of the last n answered turns, oldest first, read
    from ~/.claude/projects/*/<session id>.jsonl. Returns (answers, total)."""
    root = _projects(root)
    hits = glob.glob(os.path.join(root, "*", f"{session_id}.jsonl"))
    if not hits:
        raise NoTranscript(f"no transcript for session {session_id} under {root}")
    with open(max(hits, key=os.path.getmtime), encoding="utf-8") as f:
        answered = [t for t in turns(f) if t]
    return [t[-1] for t in answered[-n:]], len(answered)
