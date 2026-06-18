---
name: anatomy-project
description: Analyzes the project in the current directory and produces an onboarding guide that helps a junior developer grasp the architecture, key modules, and overall structure at a glance, plus the main features and trade-offs. The guide is written in the same language as the user's request. Use when the user invokes "/anatomy-project [path]" or asks for a project anatomy / onboarding overview.
user-invocable: true
argument-hint: "[project path]"
---

Read the project in the current directory and produce an onboarding guide that lets a junior developer quickly build a mental model of the codebase: its architecture, key modules, and structure at a glance, plus the main features and trade-offs. Write the guide in the same language as the user's request.

## Input

`$ARGUMENTS` is an optional path to the project to analyze.
- If empty, analyze the project in the current working directory (`pwd`). This is the default.
- If a path is given, use it instead. Both absolute and relative paths are allowed.
- If the resolved path does not exist, ask the user to confirm and stop.

## Analysis Steps

1. Locate the project — resolve the target path (current directory by default) and confirm it exists with `ls`.
2. Map the layout — inspect the top-level tree and the main subdirectories. Identify entry points, configuration, and build files.
3. Read the key documents — `README*`, `docs/`, dependency manifests (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, …), `CHANGELOG*`, `LICENSE`.
4. Reconstruct the architecture — detect the project type and framework, the main layers/components, and how they connect (entry point → core logic → output, request/data flow). For a large repo, explore efficiently with Glob/Grep or delegate to a subagent instead of reading every file.
5. Identify the key modules — the directories and files that carry the core responsibility. Summarize what each one does in plain language.
6. Extract features and trade-offs — list the main features and the strengths/weaknesses that are actually evident in the code and docs. Omit anything you cannot ground; do not guess.
7. Write the onboarding guide following the principles below.

## Output Structure (in this order)

Produce the guide in the user's language with these sections. Omit a section only when there is genuinely nothing grounded to say.

1. **Title + overview** — one title line, then a short plain-language paragraph: what the project is and what problem it solves.
2. **Architecture at a glance** — how the main parts fit together. A small ASCII (or Mermaid) diagram is welcome when it clarifies the flow.
3. **Project structure** — an annotated directory tree in a fenced code block, noting what each important directory/file is for and where the entry points are.
4. **Key modules** — the core modules/components and each one's responsibility, in plain language.
5. **Key features** — what the project does, from a user's or caller's point of view.
6. **Strengths and weaknesses** — pros and cons a newcomer should know, including pitfalls or rough edges.
7. **Where to start** — a concrete reading path: which files/directories a junior should open first, and in what order, to understand the project.

## Writing Principles

- The reader is a junior developer seeing this codebase for the first time. Optimize for building an accurate mental model fast.
- Use clear section headings and bullets so architecture, structure, modules, and features can be scanned at a glance.
- Explain jargon and project-specific terms in plain language; assume the reader does not know them.
- Stay grounded. Prefer concrete file and module names you actually saw over vague description.
- Keep a calm, mentoring tone — helpful and precise, not exaggerated.
- Write the guide in the same language as the user's request or question (Korean request → Korean, in polite form/존댓말; English request → English). These SKILL.md instructions stay in English regardless; only the generated guide follows the user's language.
- Aim for roughly one page — enough to onboard, short enough to read in one sitting.

## Prohibitions

- Do not present unverified guesses as fact. If something is uncertain, say so or leave it out.
- Do not invent files, modules, or features you did not actually observe.
- Omit any of the features / strengths / weaknesses categories the code and docs give you no evidence for. Do not pad.
- Do not use emoji.

## Output

Present the onboarding guide to the user as the response. Do not save it to a file unless the user explicitly asks; if they do, write it to a sensible path such as `docs/anatomy.md`.
