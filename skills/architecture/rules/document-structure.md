# Document Structure Rule

## Main Architecture File Location

- **Path:** `docs/ARCHITECTURE.md`
- **Purpose:** Table of contents and navigation hub
- **Content:** Overview, links, and brief descriptions only

## Detailed Documentation Location

- **Path:** `docs/architecture/*.md`
- **Purpose:** Comprehensive guidelines for each major topic
- **Naming:** Use lowercase with hyphens (e.g., `frontend-web.md`, `design-patterns.md`)

## Main ARCHITECTURE.md Template

````markdown
# Architecture Documentation {#architecture-documentation data-source-line="119"}

## Overview {#overview data-source-line="121"}

[Brief description of the project and documentation purpose]

**Core Principle:** Use the latest stable technologies and modern best practices across all platforms.

## Table of Contents {#table-of-contents data-source-line="126"}

### 1. [Project Structure](./architecture/project-structure.md) {#1-project-structurearchitectureproject-structuremd data-source-line="128"}

[One-line description]

### 2. Frontend Architecture {#2-frontend-architecture data-source-line="131"}

- **[Web Applications](./architecture/frontend-web.md)** - [Brief description]
- **[macOS Applications](./architecture/frontend-macos.md)** - [Brief description]
- **[iOS Applications](./architecture/frontend-ios.md)** - [Brief description]

### 3. [Backend Architecture](./architecture/backend.md) {#3-backend-architecturearchitecturebackendmd data-source-line="136"}

[One-line description]

### 4. [AI Integration](./architecture/ai-integration.md) {#4-ai-integrationarchitectureai-integrationmd data-source-line="139"}

[One-line description]

### 5. [Build and Deployment](./architecture/build-deployment.md) {#5-build-and-deploymentarchitecturebuild-deploymentmd data-source-line="142"}

[One-line description]

### 6. [Design Patterns and Principles](./architecture/design-patterns.md) {#6-design-patterns-and-principlesarchitecturedesign-patternsmd data-source-line="145"}

[One-line description]

## Quick Reference {#quick-reference data-source-line="148"}

[Technology stack summary]
[Key principles list]

---

**For detailed guidelines, refer to the linked documents above.**

```{data-source-line="154"}

## Detailed Document Template

Each `docs/architecture/*.md` file must include:

1. **Title** (H1)
2. **Technology Stack** section
3. **Core principles** with MUST/SHOULD/MAY indicators
4. **Code examples** using latest syntax
5. **Related Documents** section at the end

## File Organization Requirements
- **MUST** keep main ARCHITECTURE.md under 200 lines
- **MUST** create separate files for each major section
- **SHOULD** keep detailed docs between 300-800 lines each
- **MUST** use relative links between documents
- **MUST** include cross-references where relevant
```
````
