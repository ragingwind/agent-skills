---
name: upload-evidence
description: Upload browser test evidence (.png screenshots or .webm video) to the test-evidence GitHub Release and post as a PR comment with asset links. /dev pipeline uses screenshot mode (.png); /qa pipeline uses video mode (.webm). Called per-stage (build/verify/qa) after gate passes.
---

# Upload Evidence

Upload browser test evidence files to GitHub and post them to the PR.

**Mode by pipeline:**
- `/dev` (build + verify stages) — `.png` screenshots
- `/qa` (scenario acceptance) — `.webm` video recordings

## Usage

```
Skill(skill: "upload-evidence")
Skill(skill: "upload-evidence", args: "--pr 7")
Skill(skill: "upload-evidence", args: "--mode screenshot --section '[A] Browser Verify — Phase 1' --description 'Purpose: verify settings page rendering'")
Skill(skill: "upload-evidence", args: "--pipeline qa --mode video --section 'S1: Chat flow' --description 'Verify new-conversation creation and message send'")
```

## Parameters

| Flag | Description | Default |
|------|-------------|---------|
| `--pr NUMBER` | PR number | auto-detected from current branch |
| `--name NAME` | Task name (used in filenames) | derived from branch name |
| `--mode screenshot\|video` | Evidence format | auto-detected (png first, then webm) |
| `--pipeline dev\|qa` | Pipeline type (affects PR comment title) | `dev` |
| `--section TEXT` | PR comment section header | `Screenshots` or flow name |
| `--description TEXT` | PR comment blockquote context line | (empty) |

## What It Does

1. Collects evidence files from `$STATE_DIR/evidence/` — `.png` screenshots (/dev) or `.webm` recordings (/qa). Filenames are content-addressed (`<logical>.<hash8>.<ext>`) after Phase 6 migrate.
2. Renames to PR-scoped filename: `pr{N}-{basename}.<ext>`
3. Uploads to `test-evidence` GitHub Release
4. Verifies each upload via API (asset state + size)
5. **HEAD-checks each public download URL** (with one retry) — refuses to post the PR comment if any URL is unreachable, so the gate trail never contains 404 links
6. Posts PR comment with evidence links — `--section` and `--description` provide context inline

## Execution

```bash
bash ~/.claude/skills/upload-evidence/upload-evidence.sh
bash ~/.claude/skills/upload-evidence/upload-evidence.sh --pr 7
bash ~/.claude/skills/upload-evidence/upload-evidence.sh \
  --mode screenshot \
  --section "[A] Browser Verify — Phase 1" \
  --description "Purpose: verify settings page rendering"
```

