#!/bin/bash
# Open a new Ghostty split pane (right) at the given directory
# Usage: ghostty-split.sh [directory]

DIR="${1:-$(pwd)}"

# Copy the cd command to clipboard (handles special chars like dots, hyphens)
printf 'cd %s' "$DIR" | pbcopy

osascript << 'HEREDOC'
tell application "Ghostty" to activate
delay 0.5
tell application "System Events"
  tell process "Ghostty"
    tell menu bar 1
      tell menu bar item "File"
        tell menu "File"
          click menu item "Split Right"
        end tell
      end tell
    end tell
  end tell
end tell
delay 0.5
tell application "System Events"
  tell process "Ghostty"
    keystroke "v" using command down
    key code 36
  end tell
end tell
HEREDOC
