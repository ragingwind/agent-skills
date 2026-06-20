---
name: anatomy-project
description: Analyzes the project in the current directory and writes a shareable X (Twitter) long-form Article that captures its architecture, key modules, structure, main features, and trade-offs. Written in the same language as the user's request. Use when the user invokes "/anatomy-project [path]" or asks for a project anatomy / overview to post.
user-invocable: true
argument-hint: "[project path]"
---

Read the project in the current directory and produce a shareable write-up of the codebase — its architecture, key modules, structure, main features, and trade-offs — formatted as an X (Twitter) long-form **Article**. Write it in the same language as the user's request. The substance is still an accurate, grounded anatomy of the project; only the delivery is an article meant to be posted and scrolled, not an internal doc.

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
8. Revise (퇴고) — reread the draft once before presenting it, and smooth the prose. For Korean output specifically: merge adjacent choppy sentences that share a subject or topic into one flowing sentence using mid-sentence connectives, vary sentence length so it does not read as a staccato list, and confirm every sentence still resolves on a terminal ending (none trailing off on a connective). The goal is connected, readable 음슴체 — terse but flowing, not a wall of one-fact fragments.

## Output Structure — an X (Twitter) long-form Article

Format the result as an X **Article** (long-form post), in the user's language. It carries the same substance (what the project is, how it's built, why it stands out, where to look), but reads as a shareable article, not a checklist. Omit any section you cannot ground.

1. **Headline** — one specific, hooky title that names the project and its single most interesting idea (e.g. "eve: 디렉터리 구조 자체가 곧 AI 에이전트인 프레임워크"). Avoid generic titles like "온보딩 가이드".
2. **Lead (후킹 도입)** — 1–3 sentences right after the headline, no heading, that hook the reader: the problem it solves, or the one surprising thing about how it works.
3. **Body sections** — a handful of short `##` sections with scannable bullets. Cover, in a natural order: what it is / how it's structured / how it actually works (the core flow) / what stands out (notable features plus honest trade-offs) / where to start reading. Merge or rename freely so it flows as an article; drop anything ungrounded.
4. **Close** — one or two lines: a concrete first step (e.g. the command to run) or a takeaway, optionally a short source line (repo or path) so readers can dig in.

### Formatting for the X reader

- X Articles render prose, headings, lists, links, inline `code`, and fenced code blocks, but box-drawing ASCII diagrams (┌─┐ │ ▶) break in the X reader, especially on mobile. Do not paste a boxed architecture diagram.
- Express the architecture as a one-line arrow chain (e.g. `discover → compile → runtime → harness`) or a few prose sentences, not a drawn diagram.
- **Keep the directory structure as a fenced code block** — an annotated tree is wanted, not a bullet list. Keep it narrow and trim it to the directories that matter so it does not sprawl on a phone; plain tree glyphs (`├──`, `└──`) are fine, box-drawing is not.
- Keep other code and identifiers as short inline `code` spans (filenames, commands); avoid extra multi-line fenced blocks beyond the directory tree.
- Length: longer than a tweet is fine, but keep it tight — readable in one sitting and scannable on a phone.

## Writing Principles

- The reader is a technical person scrolling X who has never seen this project. Hook them, then leave them with an accurate mental model fast. Engaging is good; hype and ungrounded claims are not.
- Use clear section headings and bullets so architecture, structure, modules, and features can be scanned at a glance.
- Explain jargon and project-specific terms in plain language; assume the reader does not know them.
- Stay grounded. Prefer concrete file and module names you actually saw over vague description.
- Keep a precise, functional tone — information-dense and helpful, not exaggerated or chatty.
- Write the guide in the same language as the user's request or question; English request → English. These SKILL.md instructions stay in English regardless; only the generated guide follows the user's language.
- **Korean output uses 음슴체** — the terse declarative style of tech-news summaries (e.g. GeekNews / news.hada.io), not 존댓말. End sentences with terminal forms like `~함`, `~됨`, `~음`, `~임`, `~한다`, `~없음`; never `~습니다` / `~합니다` / `~에요`.
- **Vary sentence length so it reads as connected prose, not a staccato list.** Within a sentence, freely chain 2–3 closely related clauses with mid-sentence connectives (`~하고`, `~하며`, `~어서`, `~는데`, `~지만`) so related facts flow together. One fact per sentence everywhere reads choppy and is wrong; aim for a natural rhythm of short and medium sentences.
- **The constraint is only that each sentence resolves on a terminal ending — it must not stop while trailing off on a connective.** Connectives mid-sentence are good; a sentence whose final word is a connective like `~등으로`, `~하며`, `~하고`, `~으로`, `~인데` is the failure mode. Chain the clauses, then close on a terminal form.
- Aim for roughly one page — enough to onboard, short enough to read in one sitting.

## Prohibitions

- Do not present unverified guesses as fact. If something is uncertain, say so or leave it out.
- Do not invent files, modules, or features you did not actually observe.
- Omit any of the features / strengths / weaknesses categories the code and docs give you no evidence for. Do not pad.
- Do not use emoji.
- Do not use `**bold**` (asterisk emphasis) anywhere in the article — it does not render in the X reader. Use `-` bullets for structure and plain text for everything else. `##` section headings and inline `code` are still allowed; emphasis via `**` is not.

## Output

Present the onboarding guide to the user as the response. Do not save it to a file unless the user explicitly asks; if they do, write it to a sensible path such as `docs/anatomy.md`.
