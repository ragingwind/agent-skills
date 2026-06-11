---
name: review
description: Code review with severity-rated findings
---

Delegate directly to the **reviewer** agent (opus, read-only).

## Input

- `$ARGUMENTS`: PR number/URL, file path, branch name, or nothing (defaults to current diff)

## Process

1. Delegate to reviewer agent:
   - Scan: determine input type, categorize changes, detect tech stack
   - Stage 1: Spec compliance (requirements met?)
   - Stage 2: Quality and security (OWASP, type safety, error handling, performance)
   - Calculate trade-offs for each significant finding
   - Interview user to clarify intentional decisions
   - Generate final audit report
2. Record inline comments in audit report (`## Deferred Inline Comments` table)
3. Save full audit report file to `$STATE_DIR/<name>-review.md`
4. Wrapup posts inline comments, PR comment block, and study notes to GitHub

## Output

### 1. Inline Diff Comments
- Recorded in `$STATE_DIR/<name>-review.md` under `## Deferred Inline Comments`
- Each entry includes file path, line number, severity, and comment body
- Posted to the PR by the orchestrator (`commands/dev.md` POST-REVIEW step), not by the reviewer agent

### 2. PR Comment Block
- Included in `$STATE_DIR/<name>-review.md` — posted as PR comment by the orchestrator/projector (`scripts/project_events.sh`), not by the reviewer agent
- Contains verdict, executive summary, findings table, action items

### 3. Study Notes
- Included in `$STATE_DIR/<name>-review.md` under `## Study Notes`
- Wrapup posts as separate PR comment when present

### 4. Full Audit Report File
- **Always saved** to `$STATE_DIR/<name>-review.md` regardless of findings
- Contains the complete audit report:
  - Verdict: APPROVED / CHANGES_REQUIRED / NEEDS_DISCUSSION
  - Executive summary
  - What was missed (gaps, edge cases)
  - What should change (better patterns, simpler approaches)
  - Trade-off analysis table
  - Quality summary by area
  - Action items (priority order)
  - What was done well

## Formatting Rules

### Severity Icons (MUST use in all outputs — inline comments, PR comment, audit file)

| Severity | Icon | Usage |
|----------|------|-------|
| CRITICAL | 🔴 | `🔴 CRITICAL` |
| HIGH | 🟠 | `🟠 HIGH` |
| MEDIUM | 🟡 | `🟡 MEDIUM` |
| LOW | 🔵 | `🔵 LOW` |
| INFO | ⚪ | `⚪ INFO` |

### PR Comment Block formatting

- **Verdict line**: always the first line, bold, with result icon:
  - `## ✅ Review — APPROVED` or `## ❌ Review — CHANGES REQUIRED` or `## 💬 Review — NEEDS DISCUSSION`
- **Blocking findings** (CRITICAL/HIGH): use GitHub alert syntax for each:
  ```markdown
  > [!CAUTION]
  > 🔴 **CRITICAL**: SQL injection in user input — `api/chat/route.ts:42`
  > **Fix**: Use parameterized query instead of string interpolation
  ```
- **MEDIUM findings**: use warning alert:
  ```markdown
  > [!WARNING]
  > 🟡 **MEDIUM**: Missing error boundary — `components/chat.tsx:120`
  ```
- **LOW/INFO findings**: plain table (no alert box), grouped at bottom:
  ```markdown
  | # | Severity | Finding | Location |
  |---|----------|---------|----------|
  | 1 | 🔵 LOW | `initialState` type assertion | `store.ts:15` |
  | 2 | ⚪ INFO | Comprehensive test coverage | `tests/` |
  ```
- **Action items** (when CRITICAL/HIGH/MEDIUM exist): numbered checklist at the end:
  ```markdown
  ### Action Items
  - [ ] 🔴 Fix SQL injection in `api/chat/route.ts:42`
  - [ ] 🟡 Add error boundary to `components/chat.tsx:120`
  ```

### Inline diff comments formatting

Each inline comment MUST start with the severity icon:
```
🔴 **CRITICAL**: description
🟠 **HIGH**: description
🟡 **MEDIUM**: description
```

## Rules

- MUST check spec compliance BEFORE style/quality
- Every finding MUST include `file:line` reference
- Every finding MUST be severity-rated with icon (🔴/🟠/🟡/🔵/⚪)
- MUST include concrete fix suggestions
- NEVER approve code with CRITICAL or HIGH issues

---

# Review Prompts

Collects all user prompts from Claude Code sessions for a given date, then analyzes and presents them in four categories: frequently used patterns, good questions, good prompts, and command candidates.

## Process

### Step 1: Collect prompts

Run the following to extract user prompts from session JSONL files:

```bash
python3 << 'PYEOF'
import json, os, glob
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
args = "$ARGUMENTS".strip()

if args:
    target_date = args
else:
    target_date = datetime.now(KST).strftime("%Y-%m-%d")

project_dir = os.path.expanduser("~/.claude/projects")
all_files = glob.glob(f"{project_dir}/**/*.jsonl", recursive=True)
all_files = [f for f in all_files if "/subagents/" not in f]

def is_system_message(content):
    skip_prefixes = ["<task-notification>", "[Request interrupted", "<system-reminder>", "<parameter", "<result>"]
    skip_substrings = ["<task-id>", "<tool-use-id>", "<output-file>", "<status>"]
    s = content.strip()
    for p in skip_prefixes:
        if s.startswith(p): return True
    for sub in skip_substrings:
        if sub in s: return True
    return False

today_files = []
for f in all_files:
    mtime = os.path.getmtime(f)
    dt = datetime.fromtimestamp(mtime)
    if dt.strftime("%Y-%m-%d") == target_date:
        today_files.append((dt, f))

today_files.sort()

prompts = []
for _, fpath in today_files:
    last_cwd = ""
    with open(fpath) as f:
        for line in f:
            try:
                obj = json.loads(line)
                if obj.get("type") != "user": continue
                msg = obj.get("message", {})
                content = msg.get("content", "")
                if isinstance(content, list):
                    parts = [b.get("text","") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                    content = "\n".join(parts)
                content = content.strip()
                if not content or is_system_message(content): continue
                cwd = obj.get("cwd", last_cwd)
                if cwd: last_cwd = cwd
                ts = obj.get("timestamp", "")
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(KST).strftime("%H:%M")
                except:
                    dt = "??"
                prompts.append({"time": dt, "cwd": last_cwd, "text": content})
            except:
                pass

print(f"DATE: {target_date}")
print(f"TOTAL: {len(prompts)}")
print("---PROMPTS---")
for i, p in enumerate(prompts, 1):
    print(f"[{i}] ({p['time']}) {p['text']}")
PYEOF
```

### Step 2: Analyze and present

Read the collected prompts above and present them in the following four categories directly in the conversation — no file output needed.

---

## Output Format

```
## /review-prompts — <date> (<N> prompts)

### 1. Frequently Used Prompts
Prompts that appeared repeatedly or follow a similar pattern across sessions.

- ...

### 2. Good Questions
Questions with clear context that aid exploration or understanding.

- ...

### 3. Good Prompts
Prompts with specific instructions and constraints that have high reuse value.

- ...

### 4. Command Candidates
Prompts with repeating patterns worth automating as a `/command`.

- `/suggested-name` — description
```

## Rules (Review Prompts)

- No file output — results are shown directly in the conversation
- If `$ARGUMENTS` is omitted, use today's date (KST)
- Categories may overlap — the same prompt can appear in multiple categories
- Command candidates must be proposed in `/suggested-name` format
