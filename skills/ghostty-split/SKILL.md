# /ghostty-split

Open a new Ghostty split pane (right side) at the specified directory.

## Usage

```
/ghostty-split              → open split at current working directory
/ghostty-split [path]       → open split at the given path
```

## Behavior

Parse the argument:
- No argument: use the current working directory (`pwd`)
- Path argument: use the given path

Run:
```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/ghostty-split.sh [path]
```

Report the path to the user after the split opens.
