#!/usr/bin/env bash
# Manual installer for the user-global assets the plugin cannot deliver.
#
# Installs into ~/.claude (override with CLAUDE_USER_DIR):
#   global/CLAUDE.md                 -> CLAUDE.md          (soul document)
#   rules/*.md                       -> rules/             (always-on session rules)
#   scripts/statusline-command.sh    -> scripts/           (settings.json statusLine)
#   scripts/statusline-ext.sh        -> scripts/
#   scripts/events.sh                -> scripts/           (statusline dependency)
#
# ${CLAUDE_PLUGIN_ROOT} references are rewritten to $HOME/.claude — that
# variable is only set inside plugin hook/command context, never when these
# files run from settings.json or load as global rules.
#
# Idempotent: unchanged files are skipped; overwritten files get a
# timestamped .bak backup next to them.
#
# Usage: global/install.sh [--dry-run]
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd -P)
DEST="${CLAUDE_USER_DIR:-$HOME/.claude}"
DRY_RUN=0
case "${1:-}" in
    --dry-run) DRY_RUN=1 ;;
    "") ;;
    *) echo "usage: $0 [--dry-run]" >&2; exit 2 ;;
esac

STAMP=$(date +%Y%m%d%H%M%S)
INSTALLED=0
SKIPPED=0

# install_file <src> <dest-relative-to-DEST>
install_file() {
    local src="$1" rel="$2" dest tmp
    dest="$DEST/$rel"
    tmp=$(mktemp)
    sed 's|${CLAUDE_PLUGIN_ROOT}|$HOME/.claude|g' "$src" > "$tmp"

    if [ -f "$dest" ] && cmp -s "$tmp" "$dest"; then
        echo "  up-to-date  $rel"
        SKIPPED=$((SKIPPED + 1))
        rm -f "$tmp"
        return 0
    fi

    if [ "$DRY_RUN" = "1" ]; then
        if [ -f "$dest" ]; then echo "  would update   $rel (backup first)"
        else echo "  would install  $rel"; fi
        rm -f "$tmp"
        return 0
    fi

    mkdir -p "$(dirname "$dest")"
    if [ -f "$dest" ]; then
        cp -p "$dest" "$dest.bak.$STAMP"
        echo "  backup      $rel.bak.$STAMP"
    fi
    cp "$tmp" "$dest"
    rm -f "$tmp"
    # mktemp creates mode 600 and cp carried it over — restore normal modes.
    if [ -x "$src" ]; then chmod 755 "$dest"; else chmod 644 "$dest"; fi
    echo "  installed   $rel"
    INSTALLED=$((INSTALLED + 1))
}

echo "Installing user-global assets into $DEST"
[ "$DRY_RUN" = "1" ] && echo "(dry-run — no files will be written)"

echo "== soul document =="
install_file "$REPO_ROOT/global/CLAUDE.md" "CLAUDE.md"

echo "== rules =="
for f in "$REPO_ROOT"/rules/*.md; do
    install_file "$f" "rules/$(basename "$f")"
done

echo "== scripts =="
install_file "$REPO_ROOT/scripts/statusline-command.sh" "scripts/statusline-command.sh"
install_file "$REPO_ROOT/scripts/statusline-ext.sh"     "scripts/statusline-ext.sh"
install_file "$REPO_ROOT/scripts/events.sh"             "scripts/events.sh"

echo
echo "Done: $INSTALLED installed/updated, $SKIPPED already up-to-date."

# settings.json is user-owned — never edited here, only checked.
SETTINGS="$DEST/settings.json"
if [ -f "$SETTINGS" ] && ! grep -q 'statusline-command.sh' "$SETTINGS" 2>/dev/null; then
    cat <<'EOF'

NOTE: settings.json does not reference the statusline. To enable it, add:
  "statusLine": {
    "type": "command",
    "command": "bash ~/.claude/scripts/statusline-command.sh"
  }
EOF
fi
