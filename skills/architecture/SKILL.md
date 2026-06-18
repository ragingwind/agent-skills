---
name: architecture
description: Generate comprehensive architecture documentation (ARCHITECTURE.md) by analyzing project structure. Covers frontend, backend, cross-cutting concerns, and deployment. Use when creating or updating architecture docs.
---

# Architecture Documentation Skill

## Overview

This skill enables AI coding agents to generate comprehensive architecture documentation that serves as the definitive reference for code generation and implementation decisions.

## Purpose

When tasked with creating or updating architecture documentation, reference the appropriate rule documents to ensure consistent, comprehensive, and modern architectural guidance.

## Core Principles

- **MUST** use the latest stable technologies and modern best practices
- **MUST** analyze the current project structure rather than creating hypothetical examples
- **MUST** maintain consistency across all documentation
- **MUST** provide clear, actionable guidelines with concrete examples

## Document Structure

- **Main architecture file:** `docs/ARCHITECTURE.md` (table of contents only)
- **Detailed documentation:** `docs/architecture/*.md` (one file per major section)

## Rules Reference

Before generating any architecture documentation, consult the relevant rule documents in `/rules`:

### Planning and Structure

- **[document-structure.md](./rules/document-structure.md)** - How to organize the main ARCHITECTURE.md and detailed docs
- **[project-analysis.md](./rules/project-analysis.md)** - How to analyze current project structure

### Platform-Specific Rules

- **[frontend-web.md](./rules/frontend-web.md)** - Web application architecture guidelines
- **[frontend-macos.md](./rules/frontend-macos.md)** - macOS application architecture guidelines
- **[frontend-ios.md](./rules/frontend-ios.md)** - iOS application architecture guidelines
- **[backend.md](./rules/backend.md)** - Backend and API architecture guidelines

### Cross-Cutting Concerns

- **[ai-integration.md](./rules/ai-integration.md)** - AI service integration patterns
- **[build-deployment.md](./rules/build-deployment.md)** - Build, test, and deployment guidelines
- **[design-patterns.md](./rules/design-patterns.md)** - Design patterns and SOLID principles

### Writing Standards

- **[writing-guidelines.md](./rules/writing-guidelines.md)** - Documentation style and formatting rules
- **[technology-versions.md](./rules/technology-versions.md)** - Latest version requirements and update policies

## When to Use Each Rule

### Creating New Architecture Documentation

1. Start with `document-structure.md` - understand the overall organization
2. Apply `project-analysis.md` - analyze the current project
3. Select platform-specific rules based on project type:
   - For web projects → `frontend-web.md`
   - For macOS apps → `frontend-macos.md`
   - For iOS apps → `frontend-ios.md`
   - For server projects → `backend.md`
4. Add cross-cutting concerns as relevant:
   - If using AI services → `ai-integration.md`
   - Always include → `build-deployment.md`
   - Always include → `design-patterns.md`
5. Apply `writing-guidelines.md` and `technology-versions.md` throughout

### Updating Existing Documentation

1. Check `project-analysis.md` - verify current state
2. Review relevant platform-specific rules for updates
3. Check `technology-versions.md` - ensure latest versions are specified
4. Apply `writing-guidelines.md` - maintain consistent style

### Answering Architecture Questions

- Reference the appropriate rule document(s) based on the question domain
- Cross-reference multiple rules when the question spans concerns

## User Input Required

### When to Use AskUserQuestionTool

**MUST** use AskUserQuestionTool when decisions cannot be determined from existing project analysis or rules:

#### Framework Selection

- **Web Framework:** React vs Vue vs Svelte vs Angular
- **iOS/macOS UI:** SwiftUI vs UIKit vs AppKit vs Hybrid
- **Backend Framework:** Node.js vs Python vs Rust vs Go
- **State Management:** Redux vs Zustand vs Jotai vs Context API
- **Styling:** Tailwind vs CSS Modules vs Styled Components

#### Library Choices

- **Data Fetching:** React Query vs SWR vs native fetch
- **Form Handling:** React Hook Form vs Formik vs native
- **Testing:** Jest vs Vitest, Playwright vs Cypress
- **Database:** PostgreSQL vs MongoDB vs other options
- **ORM/Query Builder:** Prisma vs Drizzle vs SQLAlchemy

#### Directory Structure

- **Organization Strategy:** Feature-based vs Type-based vs Domain-driven
- **Naming Conventions:** Specific preferences for file/folder names
- **Module Boundaries:** Monorepo vs multi-repo vs monolith

#### Design Patterns

- **Architecture Pattern:** MVVM vs MVC vs Clean Architecture vs TCA
- **State Management Pattern:** Unidirectional vs bidirectional
- **API Design:** REST vs GraphQL vs tRPC vs gRPC

#### Deployment & Infrastructure

- **Hosting Platform:** Vercel vs Netlify vs AWS vs self-hosted
- **CI/CD:** GitHub Actions vs GitLab CI vs other
- **Containerization:** Docker usage preferences

### How to Ask Questions

When using AskUserQuestionTool:

1. **Be Specific:** Ask about concrete choices, not open-ended preferences
2. **Provide Context:** Explain why the choice matters
3. **Offer Options:** Present 2-4 recommended options with brief trade-offs
4. **Show Current State:** If detected from project analysis, mention it

### Example Question Format

```
Cannot determine [DECISION] from current project structure.

Current Detection: [what was found or not found]

Question: Which [framework/library/pattern] should be used for [purpose]?

Recommended Options:

[Option A] - [brief pro/con]
[Option B] - [brief pro/con]
[Option C] - [brief pro/con]
This decision affects: [impact on architecture]
```

### When NOT to Ask

**DO NOT** use AskUserQuestionTool for:

- Technology versions (use latest stable per rules)
- Best practices already defined in rules
- Decisions clearly evident from existing code
- Minor implementation details
- Formatting or style preferences covered in writing-guidelines.md

## Activation Triggers

This skill activates when requests include terms like:

- "architecture documentation"
- "create ARCHITECTURE.md"
- "document the architecture"
- "architectural guidelines"
- "design principles"
- "project structure documentation"

## Output Format

- Main file: `docs/ARCHITECTURE.md` (table of contents with links)
- Detailed files: `docs/architecture/*.md` (one per major section)
- All files must follow markdown format with clear headings
- Include user-confirmed choices in documentation

## Context Optimization

- Load only relevant rule documents based on project type and scope
- For web-only projects, skip iOS/macOS rules
- For frontend-only projects, skip backend rules
- Always include document-structure, writing-guidelines, and technology-versions

## Workflow Summary

1. **Analyze** current project structure
2. **Identify** gaps requiring user decisions
3. **Ask** user questions for unresolved choices (using AskUserQuestionTool)
4. **Consult** relevant rule documents
5. **Generate** documentation with confirmed decisions
6. **Validate** consistency across all documents

---

**For specific implementation guidelines, always consult the appropriate rule documents in `/rules` before generating content.**
