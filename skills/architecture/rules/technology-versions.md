# Technology Versions Rule

## Core Principle

**MUST** use the latest stable versions of all technologies, frameworks, and tools unless explicitly documented otherwise.

## Update Frequency

- **MUST** review and update version requirements quarterly
- **SHOULD** update when major versions release
- **MUST** document reasons for not using latest version

## Web Technologies

### JavaScript Runtime

- **Node.js:** 22+ LTS
- **Bun:** 1.2+ (if applicable)
- **Deno:** 2.0+ (if applicable)

### Language

- **TypeScript:** 5.7+
- **MUST** enable strict mode
- **MUST** use latest ESNext features

### Frameworks

- **React:** 19+
- **Next.js:** 15+
- **Vue:** 3.5+
- **Svelte:** 5+
- **Angular:** 18+

### Build Tools

- **Vite:** 6+
- **Turbopack:** Latest (with Next.js)
- **esbuild:** 0.24+

### Testing

- **Vitest:** 3+
- **Playwright:** 1.49+
- **Testing Library:** Latest

## Apple Platforms

### Language & Tools

- **Swift:** 6.0+
- **Xcode:** 16+
- **MUST** enable strict concurrency

### Minimum Deployment Targets

- **iOS:** 18.0+
- **macOS:** 15.0+
- **watchOS:** 11.0+ (if applicable)
- **tvOS:** 18.0+ (if applicable)

### Rationale

Targeting latest versions enables:

- SwiftUI latest features
- Observation framework
- Swift 6 concurrency features
- Latest SDK capabilities

## Backend

### Databases

- **PostgreSQL:** 16+
- **MongoDB:** 8+
- **Redis:** 7+

### ORMs/Query Builders

- **Drizzle:** 0.38+ (TypeScript)
- **Prisma:** 6+ (TypeScript)
- **SQLAlchemy:** 2.0+ (Python)

## AI Services

### SDKs

- **OpenAI:** ^4.75+
- **Anthropic:** ^0.32+
- **MUST** check for updates monthly

### Models

- **Claude:** claude-3-5-sonnet-20241022 or newer
- **GPT:** gpt-4-turbo or newer
- **MUST** document which model versions tested

## Version Pinning

### When to Pin Exact Versions

- **Production dependencies** in applications (not libraries)
- **Docker base images**
- **CI/CD tool versions**

### When to Use Range Versions

- **Libraries** published to package managers
- **Development dependencies**
- **Use:** ^X.Y.Z (compatible versions)

## Deprecation Policy

### When Older Versions Acceptable

- **MUST** document explicitly in architecture docs
- **MUST** provide migration timeline
- **Example reasons:**
  - Client requirement
  - Third-party dependency limitation
  - Platform constraint (e.g., older iOS deployment target)

### Example Documentation

````markdown
### Exception: React 18 {#exception-react-18 data-source-line="1831"}

**Current Version:** React 18.3
**Target Version:** React 19+
**Reason:** Waiting for third-party form library compatibility
**Migration Date:** Q2 2026
**Tracking Issue:** #123

````{data-source-line="1838"}

## Security Updates

### Requirements
- **MUST** apply security patches immediately
- **MUST** audit dependencies weekly
- **MUST** use automated tools (Dependabot, Renovate)

## Breaking Changes

### When Major Versions Release
1. **MUST** review changelog
2. **SHOULD** test in development environment
3. **MUST** document migration requirements
4. **SHOULD** update within 2 weeks if no blockers

## Compatibility Matrix

### Current Requirements (as of 2026-01)

| Platform | Language | Framework | Min Version |
|----------|----------|-----------|-------------|
| Web      | TypeScript 5.7+ | React 19+ | ✅ Latest |
| iOS      | Swift 6.0+ | SwiftUI | iOS 18.0+ |
| macOS    | Swift 6.0+ | SwiftUI | macOS 15.0+ |
| Backend  | Node.js 22+ | Hono/Fastify | ✅ Latest |

## Verification Commands

### Check Current Versions
```bash
# Node.js projects {#nodejs-projects  data-source-line="1870"}
node --version  # Should be 22+
npm ls          # Check all dependencies

# Swift projects {#swift-projects  data-source-line="1874"}
swift --version # Should be 6.0+
xcodebuild -version # Should be 16+
``` {data-source-line="1877"}

## Related Rules
- [Frontend Web](./frontend-web.md)
- [Frontend iOS](./frontend-ios.md)
- [Frontend macOS](./frontend-macos.md)
- [Backend](./backend.md)
- [Build and Deployment](./build-deployment.md)
````
````
