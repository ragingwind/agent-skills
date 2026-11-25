# Part: models

The providers and models agents run on, and the low, mid and high tiers. They
live in one file the person edits, by provider:
`~/.config/agent-foreman/providers.json` (`config.py paths` prints it as
`providers`). This part asks nothing: it makes the file, the person edits it,
and the check says what is wrong.

## How the tiers are used

- A task's difficulty (low, mid, high) gives the lead's tier; the lead
  takes the tier's first model. The pair takes the same tier, the red team
  and QA one tier above, at most high.
- An agent that checks the work never runs on the lead's model, and never
  on a lower tier: it takes its tier and the higher ones, the lead's model
  left out. So every difficulty needs a model other than its lead's at or
  above the checking roles' tier; `config.py check` names a difficulty that
  has none. High needs two models.
- A tier is an ordered list of models. The first is used; on a usage limit
  or a provider error the next one is.
- Each agent is its own process with its own model, so one task can mix
  providers and agent kinds: a lead on a token-factory model or on Codex, a
  red team on Anthropic opus.

## 1. Make the file

```bash
python3 <skill>/scripts/config.py providers --init
```

When the file is missing, it copies `providers.json.sample` from this
skill's directory: Claude's own `opus`, `sonnet` and `haiku`; low `haiku`,
mid `sonnet`, high `opus` then `sonnet`. An existing file is kept. It prints
the path and the file's problems.

## 2. The person edits it

Show the path, the file as it is, and this example of a token factory and
Codex added, then ask the person to edit the file and say when it is done. When the file
already passes the check and the person has nothing to add, go on.

```json
{
  "providers": [
    {
      "id": "anthropic",
      "models": [{"id": "opus"}, {"id": "sonnet"}, {"id": "haiku"}]
    },
    {
      "id": "tf",
      "base_url": "https://...",
      "auth": "bearer",
      "token_env": "TF_API_TOKEN",
      "models": [
        {"id": "zai-org/GLM-5.3-Flash", "name": "glm", "context": 200000}
      ]
    },
    {
      "id": "openai",
      "agent": "codex",
      "models": [{"id": "gpt-5.5", "name": "gpt"}]
    }
  ],
  "tiers": {
    "low": ["glm", "haiku"],
    "mid": ["glm", "sonnet"],
    "high": ["opus", "gpt", "sonnet"]
  }
}
```

| Where | Key | Needed | Meaning |
| --- | --- | --- | --- |
| provider | `id` | yes | The provider's name |
| | `agent` | | The agent kind its models run: `claude` (default) or `codex` |
| | `base_url` | | None: the agent's own login, Claude Code's (Anthropic) or Codex's. Set: an anthropic-compatible endpoint, for `claude` only |
| | `auth` | with `base_url` | `bearer` or `x-api-key` |
| | `token_env` | with `base_url` | The **name** of the environment variable that holds the key; never the key |
| | `models` | yes | The models it serves |
| model | `id` | yes | The model the provider knows; for Anthropic, what `claude --model` takes; for Codex, what `codex --model` takes |
| | `name` | when `id` has other characters than letters, digits, `.`, `_`, `-` | The name tiers use (default: `id`); unique across providers |
| | `context` | with `base_url` | The context size in tokens |
| | `roles` | | The models of the same provider a subagent's `opus`, `sonnet` and `haiku` map to (default: the model itself) |
| | `agent` | | The agent kind, when it is not the provider's |
| top | `tiers` | yes | `low`, `mid` and `high`, each a list of model names in order |

Offer `fable`, or a model outside the harness's own, only when the person
names it. Never ask for, read or print a key's value.

## 3. Check

```bash
python3 <skill>/scripts/config.py check
```

It names each problem in the file's terms (`provider tf: auth must be one of
bearer, x-api-key`). Show them; the person edits the file again. When it
passes, show the tier table (each tier, its models in order, each model's
provider) and one example: `python3 <skill>/scripts/config.py tier
--difficulty mid --role redteam`. Tell the person that a provider's token
variable must be set on every machine that runs its agents; the project
part's machine check shows where it is missing.

When the file has a provider with a `base_url`, check its model ids against
the provider's own list too. This uses the network and the providers' keys
from this shell; it never prints a key:

```bash
python3 <skill>/scripts/config.py check --models
```

A model `not listed` is a wrong id: the person fixes it in the file, and
the check runs again. A model `unknown` was not checked (no key in this
shell, or no list from the provider); say so, with the reason it prints.

Running agents keep the models they started with; a change applies to the
agents started after it.
