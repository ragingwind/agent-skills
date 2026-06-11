#!/usr/bin/env bun
/**
 * epic.ts — Epic-specific execution engine.
 *
 * Reads an epic issue and its sub-issues from GitHub, builds a dependency DAG,
 * and dispatches headless Claude instances layer by layer.
 *
 * Usage: bun scripts/epic.ts <epic-issue-number> [--concurrency N] [--dry-run] [--epic-dir <path>]
 */

import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { execSync } from 'child_process';

// ── Types ────────────────────────────────────────────────────────────────────

interface IssueEntry {
  number: number;
  title: string;
  branch: string;          // feat/epic-{epic_num}/{N}-{slug}
  role_prompt: string;     // descriptive prompt for the Claude instance
  depends_on: number[];    // explicit dependency list
}

interface Layer {
  layer: number;
  issues: IssueEntry[];
}

interface EpicPlan {
  epic_num: number;
  epic_title: string;
  epic_branch: string;
  layers: Layer[];
  concurrency: number;
  repo: string;
}

interface IssueResult {
  schema_version: number;
  issue: number;
  layer: number;
  timestamp: string;
  status: 'success' | 'timeout' | 'error_max_turns' | 'error' | 'skipped';
  turns: number;
  cost_usd: number;
  error: string;
  _partial: boolean;
}

// ── Utilities ────────────────────────────────────────────────────────────────

function atomicWriteSync(filePath: string, data: string): void {
  const tmp = filePath + '.tmp';
  fs.writeFileSync(tmp, data, 'utf-8');
  fs.renameSync(tmp, filePath);
}

function log(msg: string): void {
  process.stderr.write(`[epic] ${msg}\n`);
}

function printUsage(): void {
  console.log(`epic.ts — Epic execution engine

Usage:
  bun scripts/epic.ts <epic-issue-number> [options]

Options:
  --concurrency N   Max parallel Claude instances (default: 3)
  --dry-run         Print execution plan without running
  --epic-dir <path> Directory for results and logs (default: /tmp/claude-epic-<epic-num>)
  --help            Show this help message

Reads the epic issue and sub-issues from GitHub, builds a dependency DAG,
and dispatches headless Claude instances layer by layer.`);
}

// ── Bun check ────────────────────────────────────────────────────────────────

function checkBun(): void {
  if (typeof Bun === 'undefined') {
    console.error('Error: Bun runtime is required.');
    console.error('Install: curl -fsSL https://bun.sh/install | bash');
    process.exit(1);
  }
}

// ── GitHub data fetching ─────────────────────────────────────────────────────

interface GitHubSubIssue {
  number: number;
  title: string;
  body: string;
  state: string;
}

function fetchSubIssues(epicNum: number, repo: string): GitHubSubIssue[] {
  try {
    const raw = execSync(
      `gh api "repos/${repo}/issues/${epicNum}/sub_issues" --jq '[.[] | {number, title, body, state}]'`,
      { encoding: 'utf-8', timeout: 30000 },
    ).trim();
    return JSON.parse(raw);
  } catch (err) {
    log(`Failed to fetch sub-issues: ${err}`);
    return [];
  }
}

function fetchEpicData(epicNum: number, repo: string): { title: string; body: string } {
  try {
    const raw = execSync(
      `gh api "repos/${repo}/issues/${epicNum}" --jq '{title: .title, body: .body}'`,
      { encoding: 'utf-8', timeout: 15000 },
    ).trim();
    return JSON.parse(raw);
  } catch (err) {
    log(`Failed to fetch epic issue: ${err}`);
    return { title: '', body: '' };
  }
}

function extractPlan(issueNum: number, repo: string): string {
  try {
    const raw = execSync(
      `gh api "repos/${repo}/issues/${issueNum}/comments" --jq '[.[] | select(.body | contains("gate:dev-plan"))] | last | .body'`,
      { encoding: 'utf-8', timeout: 15000 },
    ).trim();
    return raw === 'null' ? '' : raw;
  } catch {
    return '';
  }
}

// ── DAG construction ─────────────────────────────────────────────────────────

function parseDependencies(body: string, validNumbers: Set<number>): number[] {
  if (!body) return [];
  const deps: number[] = [];
  // Match patterns: "depends on #N", "blocked by #N", "after #N"
  const patterns = [
    /depends\s+on\s+#(\d+)/gi,
    /blocked\s+by\s+#(\d+)/gi,
    /after\s+#(\d+)/gi,
  ];
  for (const pattern of patterns) {
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(body)) !== null) {
      const num = parseInt(match[1], 10);
      if (validNumbers.has(num) && !deps.includes(num)) {
        deps.push(num);
      }
    }
  }
  return deps;
}

function slugify(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40);
}

function buildDAG(subIssues: GitHubSubIssue[]): { layers: Map<number, number>; hasCycle: boolean } {
  const validNumbers = new Set(subIssues.map((i) => i.number));
  const deps = new Map<number, number[]>();
  for (const issue of subIssues) {
    deps.set(issue.number, parseDependencies(issue.body, validNumbers));
  }

  // Kahn's algorithm for topological sort
  const inDegree = new Map<number, number>();
  const adjList = new Map<number, number[]>();

  for (const num of validNumbers) {
    inDegree.set(num, 0);
    adjList.set(num, []);
  }

  for (const [num, depList] of deps) {
    inDegree.set(num, depList.length);
    for (const dep of depList) {
      adjList.get(dep)!.push(num);
    }
  }

  const layers = new Map<number, number>();
  const queue: number[] = [];

  // Layer 0: no dependencies
  for (const [num, deg] of inDegree) {
    if (deg === 0) {
      queue.push(num);
      layers.set(num, 0);
    }
  }

  let processed = 0;
  let head = 0;

  while (head < queue.length) {
    const current = queue[head++];
    processed++;
    const currentLayer = layers.get(current)!;

    for (const dependent of adjList.get(current)!) {
      const newDeg = inDegree.get(dependent)! - 1;
      inDegree.set(dependent, newDeg);
      if (newDeg === 0) {
        queue.push(dependent);
        // Layer = max layer of all dependencies + 1
        const depLayer = Math.max(currentLayer + 1, layers.get(dependent) ?? 0);
        layers.set(dependent, depLayer);
      }
    }
  }

  return {
    layers,
    hasCycle: processed !== validNumbers.size,
  };
}

function buildRolePrompt(
  issue: GitHubSubIssue,
  epicNum: number,
  epicTitle: string,
  epicBody: string,
  plan: string,
  layer: number,
  epicBranch: string,
  depsList: number[],
): string {
  const epicContext = epicBody.slice(0, 500);
  const depsNote = layer > 0 && depsList.length > 0
    ? `Issues ${depsList.map((d) => `#${d}`).join(', ')} have been completed and merged to ${epicBranch}.`
    : 'No dependencies — this is Layer 0 work.';

  return `You are implementing sub-issue #${issue.number} "${issue.title}" as part of Epic #${epicNum} "${epicTitle}".

## Epic Context
${epicContext}

## Your Implementation Plan
${plan || '(No gate:dev-plan comment found — implement based on issue description)'}

## Dependencies
${depsNote}

## Task
- Branch: feat/epic-${epicNum}/${issue.number}-${slugify(issue.title)}
- Target branch: ${epicBranch} (NOT main)

Run /dev for issue #${issue.number}.`;
}

// ── NDJSON stream parser ─────────────────────────────────────────────────────

interface StreamEvent {
  type?: string;
  subtype?: string;
  tool_name?: string;
  num_turns?: number;
  total_cost_usd?: number;
  result?: string;
  session_id?: string;
  [key: string]: unknown;
}

async function processStream(
  stream: ReadableStream<Uint8Array>,
  issueNumber: number,
  layerNum: number,
  ndjsonPath: string,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  const ndjsonFd = fs.openSync(ndjsonPath, 'w');

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        fs.writeSync(ndjsonFd, trimmed + '\n');

        try {
          const event: StreamEvent = JSON.parse(trimmed);
          onEvent(event);
        } catch {
          // Skip malformed lines
        }
      }
    }

    buffer += decoder.decode();

    if (buffer.trim()) {
      fs.writeSync(ndjsonFd, buffer.trim() + '\n');
      try {
        const event: StreamEvent = JSON.parse(buffer.trim());
        onEvent(event);
      } catch {
        // Skip malformed
      }
    }
  } finally {
    fs.closeSync(ndjsonFd);
    reader.releaseLock();
  }
}

// ── Failure reporting ────────────────────────────────────────────────────────

function getLastToolFromNdjson(ndjsonPath: string): string {
  if (!fs.existsSync(ndjsonPath)) return '-';
  const lines = fs.readFileSync(ndjsonPath, 'utf-8').split('\n').filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i--) {
    try {
      const d = JSON.parse(lines[i]);
      if (d.type === 'assistant') {
        const content = d.message?.content ?? [];
        for (const c of content) {
          if (c.type === 'tool_use') return c.name ?? '-';
          if (c.type === 'text' && c.text?.length > 0) return 'thinking';
        }
      }
    } catch { /* skip */ }
  }
  return '-';
}

function getLastStageFromNdjson(ndjsonPath: string): string {
  if (!fs.existsSync(ndjsonPath)) return 'unknown';
  const lines = fs.readFileSync(ndjsonPath, 'utf-8').split('\n').filter(Boolean);
  const stageKeywords = ['setup', 'dev-plan', 'build', 'tdd', 'qa', 'review', 'finalize'];
  let lastStage = 'unknown';
  for (const line of lines) {
    try {
      const d = JSON.parse(line);
      if (d.type === 'assistant') {
        const content = d.message?.content ?? [];
        for (const c of content) {
          if (c.type === 'tool_use' && c.name === 'Skill') {
            const skillName: string = (c.input?.skill ?? '').toLowerCase();
            if (stageKeywords.some((s) => skillName.includes(s))) {
              lastStage = skillName;
            }
          }
          if (c.type === 'text') {
            const text: string = (c.text ?? '').toLowerCase();
            for (const s of stageKeywords) {
              if (text.includes(`## ${s}`) || text.includes(`stage: ${s}`) || text.includes(`running ${s}`)) {
                lastStage = s;
              }
            }
          }
        }
      }
    } catch { /* skip */ }
  }
  return lastStage;
}

async function postFailureReport(
  result: IssueResult,
  ndjsonPath: string,
  elapsedSec: number,
): Promise<void> {
  const lastTool = getLastToolFromNdjson(ndjsonPath);
  const lastStage = getLastStageFromNdjson(ndjsonPath);
  const statusLabel = result.status === 'timeout' ? 'Timeout' : result.status === 'error_max_turns' ? 'Max Turns Exceeded' : 'Error';

  const body = [
    `## Epic Dispatch ${statusLabel} — Issue #${result.issue}`,
    '',
    `| Field | Value |`,
    `|-------|-------|`,
    `| Status | \`${result.status}\` |`,
    `| Elapsed | ${elapsedSec}s |`,
    `| Turns | ${result.turns} |`,
    `| Cost | $${result.cost_usd.toFixed(3)} |`,
    `| Last Stage | \`${lastStage}\` |`,
    `| Last Tool | \`${lastTool}\` |`,
    result.error ? `| Error | ${result.error} |` : '',
    '',
    `> Posted automatically by epic.ts at ${new Date().toISOString()}`,
  ].filter((l) => l !== '').join('\n');

  try {
    const proc = Bun.spawn(['gh', 'issue', 'comment', String(result.issue), '--body', body], {
      stdout: 'pipe',
      stderr: 'pipe',
    });
    const exitCode = await proc.exited;
    if (exitCode !== 0) {
      log(`#${result.issue} warning: failed to post failure report (exit ${exitCode})`);
    } else {
      log(`#${result.issue} failure report posted to GitHub issue`);
    }
  } catch (err) {
    log(`#${result.issue} warning: could not post failure report: ${err}`);
  }
}

// ── Semaphore for concurrency control ────────────────────────────────────────

class Semaphore {
  private queue: (() => void)[] = [];
  private current = 0;

  constructor(private max: number) {}

  async acquire(): Promise<void> {
    if (this.current < this.max) {
      this.current++;
      return;
    }
    return new Promise<void>((resolve) => {
      this.queue.push(() => {
        this.current++;
        resolve();
      });
    });
  }

  release(): void {
    this.current--;
    const next = this.queue.shift();
    if (next) next();
  }
}

// ── Repo root resolution ─────────────────────────────────────────────────────

function getRepoRoot(): string {
  const gitCommonDir = execSync('git rev-parse --git-common-dir', { encoding: 'utf-8' }).trim();
  if (path.isAbsolute(gitCommonDir)) {
    return path.dirname(gitCommonDir);
  }
  return execSync('git rev-parse --show-toplevel', { encoding: 'utf-8' }).trim();
}

function ensureWorktree(branch: string, repoRoot: string, epicBranch: string): string {
  const branchSlug = branch.replace(/\//g, '-');
  const worktreePath = path.join(repoRoot, '.claude', 'worktrees', branchSlug);

  if (fs.existsSync(worktreePath)) {
    return worktreePath;
  }

  try {
    fs.mkdirSync(path.join(repoRoot, '.claude', 'worktrees'), { recursive: true });
    // Ensure the sub-issue branch exists locally, created from the epic branch.
    const branchExists = (() => {
      try {
        execSync(`GIT_CONFIG_NOSYSTEM=1 git -C ${JSON.stringify(repoRoot)} rev-parse --verify ${JSON.stringify(branch)}`, { stdio: 'pipe' });
        return true;
      } catch { return false; }
    })();
    if (!branchExists) {
      // Fetch epic branch to make sure it's up to date, then create sub-issue branch from it.
      try {
        execSync(`GIT_CONFIG_NOSYSTEM=1 git -C ${JSON.stringify(repoRoot)} fetch origin ${JSON.stringify(epicBranch)}`, { stdio: 'pipe' });
      } catch { /* non-fatal */ }
      execSync(
        `GIT_CONFIG_NOSYSTEM=1 git -C ${JSON.stringify(repoRoot)} branch ${JSON.stringify(branch)} origin/${epicBranch}`,
        { stdio: 'pipe' },
      );
    }
    execSync(
      `GIT_CONFIG_NOSYSTEM=1 git -C ${JSON.stringify(repoRoot)} worktree add ${JSON.stringify(worktreePath)} ${JSON.stringify(branch)}`,
      { stdio: 'pipe' },
    );
    return worktreePath;
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    // If the branch is already checked out in another worktree, reuse that path.
    const alreadyUsed = msg.match(/already used by worktree at '([^']+)'/);
    if (alreadyUsed) {
      const existingPath = alreadyUsed[1];
      log(`reusing existing worktree for ${branch} at ${existingPath}`);
      return existingPath;
    }
    log(`warning: could not create worktree for ${branch}: ${msg} — falling back to repo root`);
    return repoRoot;
  }
}

const REPO_ROOT = getRepoRoot();

// ── Run a single issue ───────────────────────────────────────────────────────

async function runIssue(
  issue: IssueEntry,
  layerNum: number,
  epicBranch: string,
  resultsDir: string,
  repo: string,
  timeoutSeconds: number = 3600,
): Promise<IssueResult> {
  const TIMEOUT_MS = timeoutSeconds * 1000;
  const startTime = Date.now();
  const num = issue.number;
  const ndjsonPath = path.join(resultsDir, `${num}.ndjson`);
  const resultPath = path.join(resultsDir, `${num}.json`);

  let turns = 0;
  let costUsd = 0;
  let exitReason = '';
  let firstResultCaptured = false;

  const makeResult = (
    status: IssueResult['status'],
    error: string,
    partial: boolean,
  ): IssueResult => ({
    schema_version: 1,
    issue: num,
    layer: layerNum,
    timestamp: new Date().toISOString(),
    status,
    turns,
    cost_usd: costUsd,
    error,
    _partial: partial,
  });

  // Skip if branch already has a merged PR targeting the epic branch (idempotent re-run).
  try {
    const mergedPr = execSync(
      `gh pr list -R ${JSON.stringify(repo)} --head ${JSON.stringify(issue.branch)} --base ${JSON.stringify(epicBranch)} --state merged --json number -q '.[0].number'`,
      { stdio: 'pipe' }
    ).toString().trim();
    if (mergedPr && /^\d+$/.test(mergedPr)) {
      log(`#${num} layer:${layerNum} already merged (PR #${mergedPr}), skipping dispatch`);
      const result = makeResult('success', '', false);
      atomicWriteSync(resultPath, JSON.stringify(result, null, 2));
      return result;
    }
  } catch { /* gh unavailable or no PR */ }

  atomicWriteSync(resultPath, JSON.stringify(makeResult('error', '', true), null, 2));

  const args = [
    'claude', '-p', issue.role_prompt,
    '--output-format', 'stream-json',
    '--verbose',
    '--model', 'opus',
    '--permission-mode', 'auto',
    '--max-turns', '200',
  ];

  const worktreeCwd = ensureWorktree(issue.branch, REPO_ROOT, epicBranch);
  log(`#${num} layer:${layerNum} starting (cwd: ${worktreeCwd})`);

  // HOME workaround for corrupted .claude.json
  let spawnEnv: Record<string, string> | undefined;
  const realHome = process.env.HOME || '/home/claude';
  const configPath = path.join(realHome, '.claude.json');
  let configBroken = !fs.existsSync(configPath);
  if (!configBroken) {
    try { JSON.parse(fs.readFileSync(configPath, 'utf-8')); } catch { configBroken = true; }
  }
  if (configBroken) {
    const backupDir = path.join(realHome, '.claude', 'backups');
    const backups = fs.existsSync(backupDir)
      ? fs.readdirSync(backupDir).filter((f: string) => f.startsWith('.claude.json.backup'))
      : [];
    if (backups.length > 0) {
      const tmpHome = path.join('/tmp', `epic-home-${num}`);
      fs.mkdirSync(tmpHome, { recursive: true });
      fs.copyFileSync(path.join(backupDir, backups[backups.length - 1]), path.join(tmpHome, '.claude.json'));
      try { fs.symlinkSync(path.join(realHome, '.claude'), path.join(tmpHome, '.claude')); } catch { /* exists */ }
      spawnEnv = { ...process.env as Record<string, string>, HOME: tmpHome };
      log(`#${num} using temp HOME: ${tmpHome}`);
    }
  }

  let proc: ReturnType<typeof Bun.spawn>;
  try {
    proc = Bun.spawn(args, {
      stdout: 'pipe',
      stderr: 'pipe',
      cwd: worktreeCwd,
      ...(spawnEnv ? { env: spawnEnv } : {}),
    });
  } catch (err) {
    const error = `spawn failed: ${err}`;
    log(`#${num} layer:${layerNum} ${error}`);
    const result = makeResult('error', error, false);
    atomicWriteSync(resultPath, JSON.stringify(result, null, 2));
    await postFailureReport(result, ndjsonPath, Math.round((Date.now() - startTime) / 1000));
    return result;
  }

  let timedOut = false;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    proc.kill();
    log(`#${num} layer:${layerNum} TIMEOUT after ${TIMEOUT_MS / 1000}s`);
  }, TIMEOUT_MS);

  try {
    if (proc.stdout) {
      await processStream(
        proc.stdout as ReadableStream<Uint8Array>,
        num,
        layerNum,
        ndjsonPath,
        (event) => {
          if (event.type === 'assistant' && event.subtype === 'tool_use') {
            turns++;
            const elapsed = Math.round((Date.now() - startTime) / 1000);
            const toolName = (event.tool_name as string) || '';
            log(`#${num} layer:${layerNum} turn:${turns} tool:${toolName} elapsed:${elapsed}s`);

            atomicWriteSync(resultPath, JSON.stringify(makeResult('error', '', true), null, 2));
          }

          if (event.type === 'result') {
            if (!firstResultCaptured) {
              turns = (event.num_turns as number) ?? turns;
              costUsd = (event.total_cost_usd as number) ?? 0;
              exitReason = (event.result as string) ?? '';
              firstResultCaptured = true;
              log(`#${num} layer:${layerNum} result captured: turns=${turns} cost=$${costUsd.toFixed(2)}`);

              setTimeout(() => {
                try {
                  proc.kill();
                  log(`#${num} layer:${layerNum} killed after result (cleanup)`);
                } catch { /* already exited */ }
              }, 5000);
            }
          }
        },
      );
    }

    await proc.exited;
  } finally {
    clearTimeout(timeoutId);
  }

  const exitCode = proc.exitCode ?? 1;

  let status: IssueResult['status'];
  let error = '';

  if (timedOut) {
    status = 'timeout';
    error = `Timed out after ${TIMEOUT_MS / 1000}s`;
  } else if (exitCode === 0 || (firstResultCaptured && exitCode === 143)) {
    if (exitReason === 'max_turns') {
      status = 'error_max_turns';
      error = 'Reached max turns without completing';
    } else {
      // Verify finalize via events.jsonl: sub-issue pipeline emits `finalize.pr_ready`
      // when the PR is ready. State dir mirrors events.sh (§5 state_dir resolver).
      const branchSlug = issue.branch.replace(/[/.]/g, '-');
      const hostname = execSync('hostname').toString().toLowerCase().replace(/\./g, '-').trim();
      // Use the actual worktree path (may differ from canonical slug path when reusing an existing worktree).
      let worktreeRoot: string;
      try { worktreeRoot = fs.realpathSync(worktreeCwd); } catch { worktreeRoot = worktreeCwd; }
      const projectSlug = worktreeRoot.replace(/[/.]/g, '-');
      const eventsPath = path.join(
        os.homedir(), '.local', 'state', 'agent-skills',
        hostname, projectSlug, branchSlug, 'events.jsonl'
      );
      let finalizePassed = false;
      let verifyPassed = false;
      try {
        const content = fs.readFileSync(eventsPath, 'utf-8');
        for (const line of content.split('\n')) {
          if (!line.trim()) continue;
          try {
            const e = JSON.parse(line) as { type?: string; stage?: string };
            if (e.type === 'finalize.pr_ready') finalizePassed = true;
            if (e.type === 'stage.passed' && e.stage === 'verify') verifyPassed = true;
          } catch { /* skip */ }
        }
      } catch {
        // events.jsonl missing or unreadable
      }
      // Fallback: a merged PR for this branch = pipeline delivered its work.
      // Also accept: verify.passed + any PR (open or merged) = pipeline reached finalize.
      if (!finalizePassed) {
        try {
          const mergedPr = execSync(
            `gh pr list -R ${JSON.stringify(repo)} --head ${JSON.stringify(issue.branch)} --state merged --json number -q '.[0].number'`,
            { stdio: 'pipe' }
          ).toString().trim();
          if (mergedPr && /^\d+$/.test(mergedPr)) {
            log(`#${num} layer:${layerNum} merged PR #${mergedPr} found — treating as success`);
            finalizePassed = true;
          }
        } catch { /* gh unavailable */ }
      }
      if (!finalizePassed && verifyPassed) {
        try {
          const prJson = execSync(
            `gh pr list -R ${JSON.stringify(repo)} --head ${JSON.stringify(issue.branch)} --state all --json number -q '.[0].number'`,
            { stdio: 'pipe' }
          ).toString().trim();
          if (prJson && /^\d+$/.test(prJson)) finalizePassed = true;
        } catch { /* gh unavailable */ }
      }
      if (finalizePassed) {
        status = 'success';
      } else {
        status = 'error';
        error = 'Pipeline exited before finalize (finalize.pr_ready event not found)';
        log(`#${num} layer:${layerNum} finalize event not found at ${eventsPath}`);
      }
    }
  } else {
    status = 'error';
    error = `exit code ${exitCode}`;
  }

  const result = makeResult(status, error, false);
  atomicWriteSync(resultPath, JSON.stringify(result, null, 2));

  const elapsed = Math.round((Date.now() - startTime) / 1000);
  log(`#${num} layer:${layerNum} finished: ${status} turns:${turns} cost:$${costUsd.toFixed(2)} elapsed:${elapsed}s`);

  if (status !== 'success') {
    await postFailureReport(result, ndjsonPath, elapsed);
  }

  return result;
}

// ── Layer execution ──────────────────────────────────────────────────────────

async function runLayer(
  layer: Layer,
  epicBranch: string,
  resultsDir: string,
  repo: string,
  semaphore: Semaphore,
  failedIssues: Set<number>,
): Promise<IssueResult[]> {
  const tasks = layer.issues.map(async (issue) => {
    await semaphore.acquire();
    try {
      return await runIssue(issue, layer.layer, epicBranch, resultsDir, repo);
    } finally {
      semaphore.release();
    }
  });

  const settled = await Promise.allSettled(tasks);
  const results: IssueResult[] = [];

  for (const s of settled) {
    if (s.status === 'fulfilled') {
      results.push(s.value);
      if (s.value.status !== 'success') {
        failedIssues.add(s.value.issue);
      }
    } else {
      log(`Unexpected rejection: ${s.reason}`);
    }
  }

  return results;
}

// ── Post layer status to epic issue ──────────────────────────────────────────

async function postLayerStatus(
  epicNum: number,
  layerNum: number,
  results: IssueResult[],
  issueMap: Map<number, IssueEntry>,
): Promise<void> {
  const rows = results.map((r) => {
    const entry = issueMap.get(r.issue);
    const title = entry?.title ?? '';
    const statusIcon = r.status === 'success' ? 'done' : r.status === 'skipped' ? 'skipped' : 'failed';
    return `| #${r.issue} | ${title} | ${statusIcon} | — |`;
  }).join('\n');

  const body = [
    `<!-- gate:epic:layer:${layerNum}:${epicNum} -->`,
    `## Layer ${layerNum} Complete`,
    '',
    '| Issue | Title | Status | PR |',
    '|-------|-------|--------|----|',
    rows,
    '',
    `> Posted by epic.ts at ${new Date().toISOString()}`,
  ].join('\n');

  try {
    const proc = Bun.spawn(['gh', 'issue', 'comment', String(epicNum), '--body', body], {
      stdout: 'pipe',
      stderr: 'pipe',
    });
    await proc.exited;
    log(`Layer ${layerNum} status posted to epic #${epicNum}`);
  } catch (err) {
    log(`Warning: could not post layer status: ${err}`);
  }
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  checkBun();

  const args = process.argv.slice(2);

  if (args.includes('--help') || args.includes('-h')) {
    printUsage();
    process.exit(0);
  }

  // Parse args
  let epicNumStr = '';
  let concurrency = 3;
  let dryRun = false;
  let epicDir = '';
  let epicBranchOverride = '';

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--concurrency' && i + 1 < args.length) {
      concurrency = parseInt(args[++i], 10);
    } else if (args[i] === '--dry-run') {
      dryRun = true;
    } else if (args[i] === '--epic-dir' && i + 1 < args.length) {
      epicDir = args[++i];
    } else if (args[i] === '--epic-branch' && i + 1 < args.length) {
      epicBranchOverride = args[++i];
    } else if (!args[i].startsWith('-')) {
      epicNumStr = args[i];
    }
  }

  if (!epicNumStr) {
    console.error('Error: epic issue number required.');
    console.error('Usage: bun scripts/epic.ts <epic-issue-number> [--concurrency N] [--dry-run] [--epic-dir <path>]');
    process.exit(1);
  }

  const epicNum = parseInt(epicNumStr, 10);
  if (isNaN(epicNum)) {
    console.error(`Error: invalid issue number: ${epicNumStr}`);
    process.exit(1);
  }

  // Resolve repo
  const repo = execSync(
    "git remote get-url origin | sed -e 's#^.*github\\.com[:/]##' -e 's#\\.git$##'",
    { encoding: 'utf-8' },
  ).trim();

  // Fetch epic data
  log(`Fetching epic #${epicNum} from ${repo}...`);
  const epicData = fetchEpicData(epicNum, repo);
  if (!epicData.title) {
    console.error(`Error: could not fetch epic issue #${epicNum}`);
    process.exit(1);
  }

  const epicSlug = slugify(epicData.title).slice(0, 40);
  const epicBranch = epicBranchOverride || `epic/${epicNum}-${epicSlug}`;

  // Fetch sub-issues
  const subIssues = fetchSubIssues(epicNum, repo);
  if (subIssues.length === 0) {
    console.error(`Error: no sub-issues found for epic #${epicNum}`);
    process.exit(1);
  }

  // Filter to open sub-issues
  const openSubIssues = subIssues.filter((i) => i.state === 'open');
  log(`Found ${subIssues.length} sub-issues (${openSubIssues.length} open)`);

  // Build DAG
  const { layers: layerAssignments, hasCycle } = buildDAG(openSubIssues);
  if (hasCycle) {
    console.error('Error: dependency cycle detected among sub-issues. Cannot proceed.');
    console.error('Sub-issues with unresolved dependencies:');
    for (const issue of openSubIssues) {
      if (!layerAssignments.has(issue.number)) {
        console.error(`  #${issue.number} ${issue.title}`);
      }
    }
    process.exit(1);
  }

  // Group into layers
  const maxLayer = Math.max(...Array.from(layerAssignments.values()));
  const layerGroups: Layer[] = [];
  const issueMap = new Map<number, IssueEntry>();
  const validNumbers = new Set(openSubIssues.map((i) => i.number));

  for (let l = 0; l <= maxLayer; l++) {
    const layerIssues: IssueEntry[] = [];
    for (const issue of openSubIssues) {
      if (layerAssignments.get(issue.number) === l) {
        const plan = extractPlan(issue.number, repo);
        const deps = parseDependencies(issue.body, validNumbers);
        const branch = `feat/epic-${epicNum}/${issue.number}-${slugify(issue.title)}`;
        const rolePrompt = buildRolePrompt(
          issue, epicNum, epicData.title, epicData.body,
          plan, l, epicBranch, deps,
        );

        const entry: IssueEntry = {
          number: issue.number,
          title: issue.title,
          branch,
          role_prompt: rolePrompt,
          depends_on: deps,
        };
        layerIssues.push(entry);
        issueMap.set(issue.number, entry);
      }
    }
    if (layerIssues.length > 0) {
      layerGroups.push({ layer: l, issues: layerIssues });
    }
  }

  // Results dir
  const resultsDir = epicDir || `/tmp/claude-epic-${epicNum}`;
  fs.mkdirSync(resultsDir, { recursive: true });

  // Summary
  const totalIssues = openSubIssues.length;
  log(`Epic: #${epicNum} "${epicData.title}"`);
  log(`Branch: ${epicBranch}`);
  log(`Layers: ${layerGroups.length} | Issues: ${totalIssues} | Concurrency: ${concurrency}`);
  log(`Results: ${resultsDir}/`);

  if (dryRun) {
    console.log('\n--- DRY RUN ---\n');
    for (const layer of layerGroups) {
      console.log(`Layer ${layer.layer}:`);
      for (const issue of layer.issues) {
        const deps = issue.depends_on.length > 0
          ? ` (depends on: ${issue.depends_on.map((d) => `#${d}`).join(', ')})`
          : '';
        console.log(`  #${issue.number} ${issue.title} → ${issue.branch}${deps}`);
      }
    }
    console.log('\nNo processes will be launched.');
    process.exit(0);
  }

  const semaphore = new Semaphore(concurrency);
  const failedIssues = new Set<number>();
  const allResults: IssueResult[] = [];
  const startTime = Date.now();

  // Execute layer by layer
  for (const layer of layerGroups) {
    log(`=== Layer ${layer.layer} (${layer.issues.length} issues) ===`);

    // Check for skips based on failed dependencies
    const toRun: IssueEntry[] = [];
    for (const issue of layer.issues) {
      const hasFailed = issue.depends_on.some((dep) => failedIssues.has(dep));
      if (hasFailed) {
        log(`#${issue.number} layer:${layer.layer} SKIPPED (dependency failed)`);
        const skipped: IssueResult = {
          schema_version: 1,
          issue: issue.number,
          layer: layer.layer,
          timestamp: new Date().toISOString(),
          status: 'skipped',
          turns: 0,
          cost_usd: 0,
          error: 'dependency failed',
          _partial: false,
        };
        const resultPath = path.join(resultsDir, `${issue.number}.json`);
        atomicWriteSync(resultPath, JSON.stringify(skipped, null, 2));
        allResults.push(skipped);
        failedIssues.add(issue.number);
      } else {
        toRun.push(issue);
      }
    }

    if (toRun.length > 0) {
      const layerToRun: Layer = { layer: layer.layer, issues: toRun };
      const results = await runLayer(layerToRun, epicBranch, resultsDir, repo, semaphore, failedIssues);
      allResults.push(...results);

      // Post layer status to epic issue
      await postLayerStatus(epicNum, layer.layer, [...results, ...allResults.filter(
        (r) => r.layer === layer.layer && r.status === 'skipped',
      )], issueMap);
    }
  }

  // Write summary
  const elapsed = Math.round((Date.now() - startTime) / 1000);
  const summary = {
    schema_version: 1,
    epic_num: epicNum,
    epic_title: epicData.title,
    epic_branch: epicBranch,
    timestamp: new Date().toISOString(),
    elapsed_seconds: elapsed,
    total_issues: totalIssues,
    results: allResults.map((r) => ({
      issue: r.issue,
      layer: r.layer,
      status: r.status,
      turns: r.turns,
      cost_usd: r.cost_usd,
      error: r.error,
    })),
    totals: {
      success: allResults.filter((r) => r.status === 'success').length,
      failed: allResults.filter((r) => ['error', 'error_max_turns', 'timeout'].includes(r.status)).length,
      skipped: allResults.filter((r) => r.status === 'skipped').length,
      total_cost_usd: allResults.reduce((sum, r) => sum + r.cost_usd, 0),
    },
  };

  const summaryPath = path.join(resultsDir, 'summary.json');
  atomicWriteSync(summaryPath, JSON.stringify(summary, null, 2));

  log(`=== COMPLETE ===`);
  log(`Success: ${summary.totals.success} | Failed: ${summary.totals.failed} | Skipped: ${summary.totals.skipped}`);
  log(`Total cost: $${summary.totals.total_cost_usd.toFixed(2)} | Elapsed: ${elapsed}s`);
  log(`Summary: ${summaryPath}`);
}

main().catch((err) => {
  console.error(`Fatal error: ${err}`);
  process.exit(1);
});
