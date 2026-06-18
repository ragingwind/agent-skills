#!/usr/bin/env bash
# Validate that every skill under skills/ has a well-formed SKILL.md.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
skills_dir="$root/skills"
overall=0

if [ ! -d "$skills_dir" ]; then
  echo "error: no skills/ directory at $skills_dir" >&2
  exit 1
fi

shopt -s nullglob
dirs=("$skills_dir"/*/)
if [ "${#dirs[@]}" -eq 0 ]; then
  echo "error: no skills found under skills/" >&2
  exit 1
fi

for dir in "${dirs[@]}"; do
  name="$(basename "$dir")"
  errs=()

  printf '%s' "$name" | grep -Eq '^[a-z0-9]+(-[a-z0-9]+)*$' \
    || errs+=("directory name is not kebab-case")

  skill="${dir}SKILL.md"
  if [ ! -f "$skill" ]; then
    errs+=("missing SKILL.md")
  elif [ "$(head -n 1 "$skill")" != "---" ]; then
    errs+=("SKILL.md must start with YAML frontmatter (---)")
  else
    # Extract the frontmatter block (between the first two --- lines).
    fm="$(awk 'NR==1{next} /^---[[:space:]]*$/{exit} {print}' "$skill")"
    printf '%s\n' "$fm" | grep -Eq '^name:[[:space:]]*[^[:space:]]' \
      || errs+=("frontmatter missing 'name'")
    printf '%s\n' "$fm" | grep -Eq '^description:[[:space:]]*[^[:space:]]' \
      || errs+=("frontmatter missing 'description'")
  fi

  if [ "${#errs[@]}" -eq 0 ]; then
    echo "ok: $name"
  else
    overall=1
    for e in "${errs[@]}"; do
      echo "FAIL: $name: $e" >&2
    done
  fi
done

if [ "$overall" -eq 0 ]; then
  echo "all skills valid"
else
  echo "skill validation failed" >&2
fi
exit "$overall"
