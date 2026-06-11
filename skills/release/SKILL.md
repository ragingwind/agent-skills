---
name: release
description: Version bump, changelog, git tag, GitHub release. Supports stable and canary pre-releases.
---

# release

Version management, changelog generation, git tagging, and GitHub release creation.
Supports two release modes: **stable** (`vX.Y.Z`) and **canary** (`vX.Y.Z-canary.N`).

## Usage

```
Skill(skill: "release", args: "patch")
Skill(skill: "release", args: "minor")
Skill(skill: "release", args: "major --dry-run")
Skill(skill: "release", args: "2.0.0")
Skill(skill: "release", args: "canary")
Skill(skill: "release", args: "canary --dry-run")
```

## Input

- `$ARGUMENTS`: version, bump type, or flags
- Bump types: `major` / `minor` / `patch` → stable release
- Special type: `canary` → pre-release tag on current version
- Explicit version: `1.2.3` → stable release at that version
- No argument → `patch` bump (stable)
- `--dry-run` → show what would happen without pushing or publishing

---

## Stable Release Process (`patch` / `minor` / `major` / explicit version)

### 1. Determine Version

- Read current version from root `package.json`
- Apply bump:
  - Explicit version provided → use it
  - `major` / `minor` / `patch` → increment accordingly
  - No argument → `patch` bump

### 2. Determine Commit Range

```bash
git describe --tags --abbrev=0   # last tag (stable or canary)
```

- Use last tag as range start; fall back to first commit if no tags exist.
- Range: `<last_tag>..HEAD`

### 3. Generate Changelog

```bash
git log <last_tag>..HEAD --pretty=format:"%h - %s (%an)"
```

Group by conventional commit prefix:

| Section | Prefixes |
|---------|----------|
| Features | `feat:` |
| Bug Fixes | `fix:` |
| Breaking Changes | `BREAKING CHANGE` in body |
| Improvements | `refactor:`, `perf:` |
| Docs | `docs:` |
| Other | everything else |

### 4. Update Version Files

- Bump version in root `package.json`
- Bump version in any additional package files the project declares as tracking the same version (e.g., a monorepo app listed in the project's CLAUDE.md under release configuration)

### 5. Tag and Release

```bash
# Stage root package.json plus any project-declared version files
git add package.json <project-declared version files>
git commit -m "chore: bump version to X.Y.Z"
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin canary
git push origin vX.Y.Z
gh release create vX.Y.Z \
  --title "vX.Y.Z" \
  --notes "[changelog]"
```

---

## Canary Pre-release Process (`canary`)

Canary releases bump `package.json` to `X.Y.Z-canary.N`, commit that bump, then tag and publish.
This mirrors the Next.js canary release pattern — the version in `package.json` always reflects
exactly what is shipped, so `npm install pkg@canary` or a Docker tag resolves to the correct tree.

### 1. Determine Base Version

Read current version from root `package.json`.

- If current version is a stable `X.Y.Z` → use it as the base.
- If current version is already `X.Y.Z-canary.M` → extract `X.Y.Z` as the base.

### 2. Determine Canary Number

Find the highest existing canary tag for this base version:

```bash
git tag --list "vX.Y.Z-canary.*" | sort -V | tail -1
```

- If `vX.Y.Z-canary.2` exists → new number is `3`
- If no canary tags exist for this version → start at `1`

### 3. Determine Commit Range

Use the previous canary tag (or last stable tag if none) as range start.

### 4. Generate Changelog

Same grouping as stable, from range start to HEAD.

### 5. Bump Version, Commit, Tag, and Release

```bash
# 1. Update version in package.json files to X.Y.Z-canary.N
#    Root package.json + any additional version files declared by the project

# 2. Commit the version bump
git add package.json <project-declared version files>
git commit -m "vX.Y.Z-canary.N"

# 3. Tag the bump commit
git tag -a vX.Y.Z-canary.N -m "vX.Y.Z-canary.N"

# 4. Push branch and tag
git push origin canary
git push origin vX.Y.Z-canary.N

# 5. Create GitHub pre-release
gh release create vX.Y.Z-canary.N \
  --title "vX.Y.Z-canary.N" \
  --prerelease \
  --notes "[changelog]"
```

The `--prerelease` flag ensures GitHub marks it as a pre-release and CI's Docker metadata
action (`!contains(github.ref, '-')`) correctly excludes it from the `latest` image tag.

> **Commit message convention:** canary version bumps use the bare version string (e.g. `v0.13.0-canary.2`)
> as the commit message — no `chore:` prefix — matching the Next.js convention.

---

## Output

For both modes:

- Old version → new tag
- Commit range and count
- Categorized changelog
- GitHub release URL (if not `--dry-run`)
- Summary of what CI will do next (Docker build triggered by tag push)

---

## Rules

- MUST confirm with user before pushing tag and creating release
- MUST use `--prerelease` flag for canary releases
- MUST bump `package.json` to `X.Y.Z-canary.N` for canary releases (same as stable, different version string)
- MUST use bare version string (e.g. `v0.13.0-canary.2`) as commit message for canary bumps — no `chore:` prefix
- MUST push both the branch (`origin canary`) and the tag for all release types
- MUST follow `rules/core.md` for commit conventions and git safety
- Skip push/release if `--dry-run`
- Target branch is always `canary` (the trunk)
