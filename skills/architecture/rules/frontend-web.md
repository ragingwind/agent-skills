# Frontend Web Architecture Rule

## Applicability

Use this rule when the project includes web frontend components.

## Technology Requirements

### Framework

- **MUST** use latest stable version of chosen framework
- **React:** 19+ with React Compiler
- **Vue:** 3.4+ with Composition API
- **Svelte:** 5+ with Runes
- **Angular:** 18+

### Language

- **MUST** use TypeScript 5.7+
- **MUST** enable strict mode
- **MUST** use latest ECMAScript features
- **SHOULD** configure path aliases for imports

### Build Tools

- **MUST** use Vite 6+ (preferred) or Next.js 15+
- **SHOULD** use pnpm for package management
- **MUST** configure tree-shaking for production
- **SHOULD** use SWC or esbuild for faster builds

## Architecture Pattern

### Component Design

- **MUST** follow single responsibility principle
- **MUST** keep components under 200 lines
- **SHOULD** favor composition over inheritance
- **MUST** use functional components (React) or script setup (Vue)
- **SHOULD** extract complex logic into custom hooks or composables
- **MUST** implement proper prop validation

### State Management

- **Small/Medium apps:** Built-in state (Context API, provide/inject)
- **Large apps:** Zustand, Jotai, or Pinia
- **AVOID:** Redux unless specifically required
- **MUST** keep state as close to usage as possible
- **SHOULD** use derived state instead of duplicating state

## Styling

### Options (Choose One)

1. **Tailwind CSS 4+** (recommended for utility-first)
2. **CSS Modules** (recommended for component-scoped)
3. **Styled Components 6+** (if CSS-in-JS required)

### Requirements

- **MUST** follow consistent naming convention
- **MUST** support responsive design
- **SHOULD** use CSS variables for theming
- **MUST** avoid inline styles except for dynamic values
- **SHOULD** implement dark mode if applicable

## Routing

### Modern Approaches

- **Next.js:** App Router with server components
- **React Router:** v7+ with data APIs
- **Vue Router:** v4+ with composition API
- **TanStack Router:** For type-safe routing

### Requirements

- **MUST** implement type-safe routes
- **MUST** support deep linking
- **SHOULD** implement loading states
- **SHOULD** implement error boundaries
- **MUST** handle 404 pages properly
- **SHOULD** implement route-based code splitting

## File Structure

### Project Organization

- **MUST** analyze and document the current project's directory structure
- **MUST** maintain consistency with existing organization patterns
- **MUST** respect existing naming conventions for files and folders
- **SHOULD** refer to current project implementation for structure reference

### Organization Principles

- **MUST** separate concerns (components, services, utilities, types)
- **SHOULD** organize by feature for large applications
- **SHOULD** organize by type for small to medium applications
- **MUST** keep related files together
- **SHOULD** co-locate tests with implementation files

### File Naming Conventions

- **MUST** follow consistent naming patterns across the project
- **Components:** PascalCase (e.g., UserProfile.tsx)
- **Utilities:** camelCase (e.g., formatDate.ts)
- **Hooks/Composables:** Prefix with use (e.g., useAuth.ts)
- **Types:** PascalCase with descriptive names
- **Constants:** UPPER_SNAKE_CASE or camelCase consistently

## Data Fetching

### Requirements

- **MUST** use modern data fetching patterns (React Query, SWR, or framework built-ins)
- **MUST** handle loading states
- **MUST** handle error states
- **SHOULD** implement caching strategy
- **SHOULD** implement optimistic updates where appropriate
- **MUST** avoid waterfalls in data fetching

## Form Handling

### Requirements

- **SHOULD** use form library (React Hook Form, Formik, VeeValidate)
- **MUST** implement client-side validation
- **MUST** display validation errors clearly
- **SHOULD** implement server-side validation
- **MUST** handle form submission errors
- **SHOULD** provide loading feedback during submission

## Testing Requirements

### Unit Tests

- **MUST** use Vitest or Jest for unit tests
- **SHOULD** use Testing Library for component tests
- **MUST** test critical business logic
- **SHOULD** test error handling paths

### E2E Tests

- **SHOULD** use Playwright for E2E tests
- **MUST** test critical user flows
- **SHOULD** run E2E tests in CI/CD

### Coverage

- **MUST** maintain >80% coverage for critical paths
- **SHOULD** aim for >70% overall coverage
- **MUST** test edge cases and error scenarios

## Performance Guidelines

### Code Optimization

- **MUST** implement code splitting
- **MUST** lazy load routes
- **SHOULD** lazy load heavy components
- **MUST** avoid unnecessary re-renders
- **SHOULD** use React.memo or Vue computed appropriately

### Asset Optimization

- **SHOULD** optimize images (next/image, etc.)
- **MUST** compress and optimize assets
- **SHOULD** use modern image formats (WebP, AVIF)
- **MUST** implement lazy loading for images

### Performance Monitoring

- **MUST** measure with Lighthouse and maintain >90 score
- **SHOULD** implement Core Web Vitals tracking
- **SHOULD** monitor bundle size
- **MUST** set performance budgets

### Large Data Handling

- **SHOULD** implement virtual scrolling for large lists
- **MUST** implement pagination or infinite scroll
- **SHOULD** debounce expensive operations
- **MUST** optimize search and filter operations

## Accessibility

### Requirements

- **MUST** provide semantic HTML
- **MUST** support keyboard navigation
- **MUST** provide ARIA labels where needed
- **MUST** ensure sufficient color contrast
- **SHOULD** test with screen readers
- **MUST** handle focus management properly

## Security

### Requirements

- **MUST** sanitize user input
- **MUST** implement CSRF protection
- **MUST** use Content Security Policy
- **MUST** validate data on client and server
- **MUST** never expose sensitive data in client code
- **SHOULD** implement rate limiting on API calls

## SEO (if applicable)

### Requirements

- **MUST** implement proper meta tags
- **SHOULD** use server-side rendering for public pages
- **MUST** generate sitemap
- **SHOULD** implement structured data
- **MUST** ensure proper URL structure

## Internationalization (i18n)

### Requirements (if applicable)

- **SHOULD** use i18n library (react-i18next, vue-i18n)
- **MUST** externalize all user-facing strings
- **SHOULD** support RTL languages if needed
- **MUST** handle date/time/number formatting per locale

## Error Handling

### Requirements

- **MUST** implement error boundaries (React) or error handling (Vue)
- **MUST** log errors appropriately
- **SHOULD** implement error tracking (Sentry, etc.)
- **MUST** display user-friendly error messages
- **SHOULD** implement retry mechanisms for transient errors

## Related Rules

- [Design Patterns](./design-patterns.md)
- [Build and Deployment](./build-deployment.md)
- [Writing Guidelines](./writing-guidelines.md)
- [Technology Versions](./technology-versions.md)
- [Project Analysis](./project-analysis.md)
