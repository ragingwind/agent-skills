# Build and Deployment Rule

## Build Tools

### Web Projects

- **MUST** use Vite 6+ or Next.js 15+
- **MUST** enable production optimizations
- **MUST** configure tree-shaking
- **SHOULD** use SWC or esbuild for transpilation

### iOS/macOS Projects

- **MUST** use Xcode 16+
- **MUST** configure build configurations (Debug, Release)
- **MUST** enable optimization level for Release builds

## Environment Management

### Requirements

- **MUST** support multiple environments (dev, staging, prod)
- **MUST** use environment variables for configuration
- **MUST NOT** commit secrets to version control
- **SHOULD** use .env files for local development

### Example (.env structure)

````bash
# .env.example {#envexample  data-source-line="1213"}
DATABASE_URL=
API_KEY=
NODE_ENV=development
``` {data-source-line="1217"}

## Dependency Management

### Web (Node.js)
- **MUST** use pnpm (recommended) or npm
- **MUST** commit lock files
- **MUST** audit dependencies regularly
- **SHOULD** use exact versions for production dependencies

### iOS/macOS
- **MUST** use Swift Package Manager (preferred)
- **MAY** use CocoaPods if necessary
- **MUST** commit Package.resolved or Podfile.lock

## Testing

### Requirements
- **MUST** run tests before deployment
- **MUST** maintain minimum coverage thresholds
- **MUST** test critical paths
- **SHOULD** implement integration tests

### Test Commands
```json
{
  "scripts": {
    "test": "vitest",
    "test:coverage": "vitest --coverage",
    "test:e2e": "playwright test"
  }
}
``` {data-source-line="1249"}

## CI/CD Pipeline

### GitHub Actions Example
```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: 'pnpm'
      - run: pnpm install --frozen-lockfile
      - run: pnpm test
      - run: pnpm build
``` {data-source-line="1272"}

## Deployment Strategies

### Web Applications
- **Vercel/Netlify:** Automatic deployments from git
- **Docker:** Multi-stage builds for optimization
- **MUST** implement health checks
- **SHOULD** use CDN for static assets

### iOS/macOS Applications
- **MUST** use Xcode Cloud or Fastlane
- **MUST** configure code signing properly
- **MUST** increment build numbers automatically
- **MUST** test on real devices before release

## Monitoring

### Requirements
- **MUST** implement error tracking (Sentry, etc.)
- **SHOULD** implement performance monitoring
- **SHOULD** set up alerts for critical errors
- **MUST** log deployment events

## Rollback Strategy
- **MUST** have rollback plan
- **SHOULD** implement feature flags
- **SHOULD** use staged rollouts

## Related Rules
- [Technology Versions](./technology-versions.md)
- [Backend](./backend.md)
- [Frontend Web](./frontend-web.md)
````
