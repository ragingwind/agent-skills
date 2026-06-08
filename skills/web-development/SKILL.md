---
name: web-development
description: Web development review guidelines covering React/Next.js, TypeScript, CSS, accessibility, browser performance, and frontend tooling. Use when reviewing or auditing web projects.
---

# Web Development Review Skill

Web-specific review criteria for frontend and fullstack web projects. Load this skill when the project uses web technologies (React, Next.js, TypeScript, CSS, HTML, browser APIs).

## Related Skills

Load these alongside for deeper coverage:
- `/vercel-react-best-practices` → Component rendering, data fetching, bundle optimization, state management, hook correctness
- `/web-frontend-design` → Design quality, visual consistency, responsive layout, CSS architecture
- `/web-design-guidelines` → Web Interface Guidelines compliance, accessibility audit (WCAG 2.1 AA), UX patterns
- `/e2e` → E2E test coverage, selector strategy (data-testid, ARIA roles — never CSS classes), Page Object Model
- `/web-quality-skill` → Core Web Vitals (LCP, CLS, INP), accessibility score, SEO, best practices

## Web-Specific Review Checklist

| Area | Key Checks |
|------|-----------|
| React Patterns | Correct hook usage, proper memoization, no unnecessary re-renders, Server/Client component boundary |
| TypeScript | Strict types, no `as any`, proper `import type`, discriminated unions for state |
| CSS & Styling | No inline styles in logic, consistent design tokens, responsive breakpoints, no !important |
| Accessibility | ARIA attributes, keyboard navigation, focus management, color contrast, semantic HTML, WCAG 2.1 AA |
| Web Performance | Core Web Vitals (LCP, CLS, INP), lazy loading, image optimization, bundle size |
| Browser Compat | No unsupported APIs, polyfill strategy, progressive enhancement |

## Web-Specific Edge Cases

These are commonly missed in web projects:
- **Hydration mismatches**: Server/client rendering differences causing React hydration errors
- **Race conditions**: Concurrent state updates, stale closures, unmounted component updates
- **Security surface**: XSS vectors, unsanitized HTML, CSRF protection, Content-Security-Policy

## Quality Summary Template

Use this when reporting on web projects:

| Area | Status | Notes |
|------|--------|-------|
| React Patterns | {OK/CONCERN} | {detail} |
| TypeScript | {OK/CONCERN} | {detail} |
| CSS & Styling | {OK/CONCERN} | {detail} |
| Accessibility | {OK/CONCERN} | {detail} |
| Web Performance | {OK/CONCERN} | {detail} |
| Browser Compat | {OK/CONCERN} | {detail} |
