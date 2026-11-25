"""What every agent adapter shares."""


class TokenMissing(Exception):
    """The gateway's token variable is not set where the agent starts."""

    def __init__(self, variable):
        super().__init__(variable)
        self.variable = variable


class NoTranscript(Exception):
    """No transcript for the session on this machine."""


# Names an adapter module defines. tests/test_adapters.py checks every adapter.
REQUIRED = [
    "KIND",            # the name profiles use in `agent`
    "HERDR_KIND",      # the kind `herdr agent start --kind` and herdr's detection use
    "EXECUTABLE",      # the program launch.py replaces itself with
    "GATEWAY_KINDS",   # the gateway kinds its profiles may use; the first is the agent's own login
    "PLUGIN",          # the prefix of the default skills' names (`<PLUGIN>:<skill>`)
    "command",         # (cfg, profile name, ...) -> (argv, variables to set, variable names to clear)
    "prepare",         # (folder the agent runs in, bundle) -> None: what the agent needs there before it starts
    "parse_print",     # prompt-mode stdout -> {"ok", "result", "session_id", "cost", "denials"}
    "answer_file",     # prompt-mode stdout -> the JSON kept as the run's answer: result, session_id,
                       #   total_cost_usd and permission_denials, as Claude Code names them
    "bundle_layout",   # {skill name: {relative path: bytes}} -> {bundle path: bytes}, apart from other kinds'
    "skill_name",      # skill ref -> the name the agent calls it by
    "last_answers",    # (session id, n) -> the final text of the last n turns
    "TRUST_SCREEN",    # text on the screen while the agent asks whether to trust its folder
    "TRUST_KEYS",      # herdr keys that answer Yes to that question, sent one at a time
]

# The prefix of every default skill's name, the same for every kind: `foreman-kit:commit`.
PLUGIN = "foreman-kit"
# The command every agent is denied: the foreman merges.
NEVER_MERGE = "gh pr merge"
