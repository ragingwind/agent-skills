# Project Analysis Rule

## Purpose

Analyze the current project structure rather than creating hypothetical examples.

## Analysis Steps

### 1. Scan Project Root

- Identify all top-level directories
- Detect configuration files (package.json, Cargo.toml, etc.)
- Identify platform markers (.xcodeproj, .sln, etc.)

### 2. Identify Project Type

- **Web:** Look for src/, public/, package.json, vite.config.ts, etc.
- **iOS:** Look for .xcodeproj, Info.plist, iOS target
- **macOS:** Look for .xcodeproj, Info.plist, macOS target
- **Backend:** Look for server/, api/, database configurations

### 3. Document Current Structure

````markdown
## Current Project Structure {#current-project-structure data-source-line="199"}

[Insert actual directory tree, not hypothetical]

### Directory Purposes {#directory-purposes data-source-line="203"}

- `src/` - [Actual purpose based on inspection]
- `tests/` - [Actual purpose]
- [etc.]

### Key Configuration Files {#key-configuration-files data-source-line="208"}

- `package.json` - Dependencies and scripts
- `tsconfig.json` - TypeScript configuration
- [etc.]

```{data-source-line="212"}

### 4. Identify Technologies in Use
- Parse package.json dependencies
- Check import statements in source files
- Identify frameworks and libraries actually used
- Document version numbers found

### 5. Detect Existing Patterns
- Analyze component structure
- Identify naming conventions in use
- Detect architectural patterns already applied
- Note any inconsistencies to address

## Output Format
**MUST** present findings as:
1. Current directory structure (actual tree)
2. Technology stack (versions from package.json/Podfile/etc.)
3. Existing patterns (detected from code)
4. Recommendations for standardization (if inconsistencies found)

## Don't Assume
- **DON'T** invent directories that don't exist
- **DON'T** suggest technologies not in use
- **DON'T** ignore existing patterns in favor of "best practices"
- **DO** document what exists, then suggest improvements
```
````
