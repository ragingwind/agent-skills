---
name: analyze
description: Deep code analysis and codebase exploration with severity-rated findings
---

Delegate to the appropriate agent based on input type.

## Input

`$ARGUMENTS` can be:
- **File path, directory, or glob pattern** → structural analysis mode
- **Question or search query** → exploration mode

## Process

### Mode A — Structural Analysis (file / directory / pattern input)

Use the built-in **Plan** agent (opus, read-only):
- Map all relevant files and their relationships
- Analyze architecture, data flow, and dependencies
- Identify issues: complexity, coupling, missing patterns
- Assess risks and technical debt
- Generate severity-rated findings

### Mode B — Exploration (question / search query input)

Use the built-in Explore agent (read-only):
- Map relevant directory structure
- Launch parallel searches across the codebase
- Trace dependencies and data flow
- Synthesize findings with `file:line` references

For broad questions, launch multiple Explore agents in parallel and aggregate results.

## Output

### Structural Analysis output
- Architecture overview of analyzed area
- Key findings with `file:line` references — severity rated (CRITICAL/HIGH/MEDIUM/LOW)
- Dependency map
- Recommendations with trade-off analysis
- Risk assessment

### Exploration output
- Search results with `file:line` references
- Architecture map (if applicable)
- Key findings and patterns
- Related files and dependencies

## Rules

- MUST read all relevant code — never guess
- Every finding MUST include `file:line` reference
- MUST use parallel searches for speed (Mode B)
- MUST present trade-offs for recommendations (Mode A)
- Analysis only — does NOT modify code
