---
name: e2e
description: E2E test authoring — design, structure, implement, and verify browser-based tests using Playwright.
---

# E2E Testing Skill

Guide for designing and writing E2E tests using Playwright.

## When to Use

- Designing new E2E test suites or migrating existing tests
- Reviewing E2E tests for best practices and anti-patterns
- Setting up API mocking and fixture strategies
- Debugging flaky tests
- Making E2E tests CI-ready
- Testing visual regressions and accessibility compliance
- Testing across multiple browsers

## Relationship to Other Skills

- **[playwright](../playwright/SKILL.md)** — Low-level Playwright API usage (shared browser, assertions, commands)
- **This skill** — High-level E2E methodology (architecture, patterns, strategies)
- Use both together: this skill for *what* to test and *how* to structure it; `playwright` for *how* to run it

---

## 1. Page Object Model (POM) — Decision Framework

Choose the right abstraction level based on complexity. There is no single mandatory pattern.

### Decision Framework

| Complexity | Pattern | When |
|------------|---------|------|
| 1–2 interactions | Inline in spec | Single-use helper, no reuse needed |
| 3–5 interactions or 2+ spec files share the same helpers | Factory function (Functional POM) | Most common case |
| 3+ spec files, complex state | POM class with fixture | Justified by reuse and state complexity |

### Why POM (any form)

- **Single source of truth** — Selector changes update ONE file, not every spec
- **Readability** — `sendMessage(page, 'hello')` reads like a user story
- **Maintainability** — User actions are named, not raw clicks

### Functional POM (preferred for most cases)

A helper module with typed functions — no class instantiation required.

```typescript
// tests/helpers/chat.ts
import type { Page } from '@playwright/test';

export async function sendMessage(page: Page, text: string): Promise<void> {
  await page.getByRole('textbox').fill(text);
  await page.getByRole('button', { name: 'Send' }).click();
}

export async function waitForResponse(page: Page, timeout = 30_000): Promise<void> {
  await page.locator('[data-role="assistant"]').last().waitFor({ timeout });
  await page.locator('[aria-label="AI response streaming status"]')
    .waitFor({ state: 'hidden', timeout });
}

export async function getMessageCount(page: Page, role: 'user' | 'assistant'): Promise<number> {
  return page.locator(`[data-role="${role}"]`).count();
}
```

```typescript
// tests/e2e/chat/chat-send-message.spec.ts
import { sendMessage, waitForResponse } from '../../helpers/chat';

test('User can send a message and see a response', async () => {
  await sendMessage(sharedPage, 'Hello');
  await waitForResponse(sharedPage);
  await expect(sharedPage.locator('[data-role="assistant"]')).toHaveCount(1);
});
```

### POM Class (when justified)

Use only when 3+ spec files share the same page with complex state.

```typescript
import type { Page, Locator } from '@playwright/test';

export class ChatPage {
  readonly page: Page;
  readonly chatInput: Locator;
  readonly sendButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.chatInput = page.getByRole('textbox');
    this.sendButton = page.getByRole('button', { name: 'Send' });
  }

  async sendMessage(text: string): Promise<void> {
    await this.chatInput.fill(text);
    await this.sendButton.click();
  }
}
```

### Rules

- **Methods represent user actions** — `sendMessage()`, not `clickTextbox()`
- **Assertions stay in spec files** — helpers provide data; specs assert on it
- **NEVER use raw CSS class selectors** in helpers or specs

---

## 2. Mock-First Principle — MANDATORY for CI

### Why Mock

- **Deterministic** — Same input = same output, every time
- **Fast** — No network latency, no API processing time
- **Free** — No API tokens consumed
- **CI-ready** — No external dependencies needed
- **Isolated** — Tests don't affect each other through shared state

### Mock Strategy: Route Interception

```typescript
// Mock a single API endpoint
await page.route('**/api/chat', async (route) => {
  await route.fulfill({
    status: 200,
    contentType: 'text/event-stream',
    headers: {
      'Cache-Control': 'no-cache',
      'X-Vercel-AI-UI-Message-Stream': 'v1',
    },
    body: buildSSEResponse('Hello! This is a mocked response.'),
  });
});

// Clean up after test
await page.unroute('**/api/chat');
```

### Fixture-Based Mocking

Store mock data as files, not inline strings:

```
tests/
  fixtures/
    api-responses/
      simple-text.sse        # SSE stream for simple text response
      tool-calling.sse       # SSE stream with tool use
      error-500.json         # Error response body
    uploads/
      sample.pdf
      test-image.png
```

```typescript
// Load fixture
import { readFileSync } from 'fs';
import { resolve } from 'path';

function loadFixture(name: string): string {
  return readFileSync(resolve(__dirname, `../fixtures/api-responses/${name}`), 'utf-8');
}

await page.route('**/api/chat', async (route) => {
  await route.fulfill({
    status: 200,
    contentType: 'text/event-stream',
    body: loadFixture('simple-text.sse'),
  });
});
```

### SSE Response Builder Helper

```typescript
interface SSEEvent {
  type: string;
  [key: string]: unknown;
}

function buildSSEBody(events: SSEEvent[]): string {
  return events.map(e => `data: ${JSON.stringify(e)}`).join('\n\n') + '\n\ndata: [DONE]\n\n';
}

function buildSimpleTextSSE(text: string, messageId?: string): string {
  const id = messageId ?? `mock-${Date.now()}`;
  return buildSSEBody([
    { type: 'start', messageId: id },
    { type: 'start-step' },
    { type: 'text-start', id: '0' },
    { type: 'text-delta', id: '0', delta: text },
    { type: 'text-end', id: '0' },
    { type: 'finish-step' },
    { type: 'finish', finishReason: 'stop' },
  ]);
}
```

### Mock Scoping Rules

- **Mock at the narrowest scope** — Per-test, not per-file
- **Always `unroute` after use** — Prevent leaks between tests
- **Use `route.continue()` for passthrough** — When you only need to intercept some requests
- **Mock only external boundaries** — API calls, not internal component state

### When NOT to Mock

- **Smoke tests** — Keep 1-2 specs against live API for sanity (tagged `@smoke`)
- **Integration tests** — When testing full request/response cycle is the point
- **Auth flows** — Programmatic JWT is faster than mocking login

---

## 3. Wait Strategies — ZERO `waitForTimeout`

### BANNED

```typescript
// NEVER do this
await page.waitForTimeout(1000);
await page.waitForTimeout(3000);
await page.waitForTimeout(500);

// NEVER do this — networkidle is unreliable with streaming responses
await page.waitForLoadState('networkidle');
```

### Correct Patterns

```typescript
// Wait for element visibility
await expect(page.locator('[data-role="assistant"]')).toBeVisible({ timeout: 30_000 });

// Wait for element to disappear
await page.locator('.loading-indicator').waitFor({ state: 'hidden', timeout: 15_000 });

// Wait for specific response
const responsePromise = page.waitForResponse('**/api/chat');
await page.click('button:has-text("Send")');
const response = await responsePromise;
expect(response.status()).toBe(200);

// Wait for URL change
await page.waitForURL(/\/chat\/[a-f0-9-]+/);

// Wait for text content
await expect(page.locator('.message')).toContainText('Expected text');

// Wait for count
await expect(page.locator('[data-role="user"]')).toHaveCount(3);
```

### Streaming Wait Pattern (for SSE/AI responses)

```typescript
// Wait for streaming indicator to appear then disappear
async function waitForStreamingComplete(page: Page, timeout = 30_000): Promise<void> {
  const streamingIndicator = page.locator('[aria-label="AI response streaming status"]');

  // Streaming may start before we check — catch both cases
  await streamingIndicator
    .waitFor({ state: 'visible', timeout: 3_000 })
    .catch(() => {}); // May have already started and finished

  await streamingIndicator
    .waitFor({ state: 'hidden', timeout })
    .catch(() => {}); // May never have appeared (fast response)

  // Verify response is present
  await expect(page.locator('[data-role="assistant"]').last()).toBeVisible();
}
```

---

## 4. Test Isolation — MANDATORY

### State Cleanup Between Tests

```typescript
test.afterEach(async () => {
  // Clear application state
  await sharedPage.evaluate(() => localStorage.clear());

  // Unroute all mocked routes
  await sharedPage.unroute('**/*');
});
```

### Fresh Context for Independent Tests

```typescript
// When tests MUST be independent (not serial)
test('independent test', async ({ browser }) => {
  const context = await browser.newContext({
    storageState: 'tests/e2e/.auth/user.json',
  });
  const page = await context.newPage();

  try {
    // Test logic...
  } finally {
    await page.close();
    await context.close();
  }
});
```

### Serial Mode — Use With Caution

Serial mode (`test.describe.configure({ mode: 'serial' })`) is efficient but creates test coupling:

- **DO use** when tests build on each other (e.g., create conversation → edit message → check version)
- **DO NOT use** when tests are logically independent
- **ALWAYS** document the dependency chain in a comment:

```typescript
test.describe.configure({ mode: 'serial' });
// Test flow: create chat → send message → edit → verify branching
// Each test depends on the previous test's state
```

---

## 5. Assertion Strength — No Weak Assertions

### BANNED Patterns

```typescript
// NEVER skip when precondition fails — FAIL instead
if (!result) { test.skip('Could not edit'); return; }

// NEVER use soft/tautological assertions
expect(stopVisible || true).toBeTruthy(); // Always passes!

// NEVER ignore assertion errors
const count = await el.count(); // Unchecked result
```

### Correct Patterns

```typescript
// Assert preconditions, don't skip
await expect(page.locator('[data-role="user"]')).toHaveCount(1);

// Assert exact values when possible
expect(version).toEqual({ current: 2, total: 3 });

// Assert specific text content
await expect(message).toContainText('Expected response');

// Assert visibility, not count
await expect(page.locator('.error-banner')).not.toBeVisible();

// Assert API response status
const response = await page.waitForResponse('**/api/chat');
expect(response.status()).toBe(200);
```

---

## 6. Flaky Test Prevention

### Root Causes and Fixes

| Cause | Fix |
|-------|-----|
| `waitForTimeout` | Replace with condition-based waits |
| Non-deterministic API | Mock API responses |
| Shared state between tests | Add `afterEach` cleanup |
| Race condition on click | Use `await expect().toBeVisible()` before clicking |
| Animation timing | Wait for animation end: `waitFor({ state: 'stable' })` |
| Viewport-dependent layout | Set explicit viewport in test config |
| Timezone/locale | Set `locale` and `timezoneId` in context options |

### Retry Strategy

```typescript
// playwright.config.ts
{
  retries: process.env.CI ? 2 : 0,  // Only retry in CI
  // Retries mask flakiness — fix root cause first
}
```

- **Rule**: If a test needs retries to pass, it's flaky. Fix the test, don't add retries.
- **Exception**: External service dependencies in smoke tests.

---

## 7. Test Classification

### Tags

```typescript
test('critical login flow @smoke', async () => { ... });
test('edge case branching @regression', async () => { ... });
test('new file upload feature @feature', async () => { ... });
```

### Categories

| Tag | Purpose | Mock? | CI? |
|-----|---------|-------|-----|
| `@smoke` | Critical paths, live API | No | Optional |
| `@regression` | Bug fix verification | Yes | Yes |
| `@feature` | New feature coverage | Yes | Yes |
| `@slow` | Long-running tests | Varies | Nightly |

### Running by Tag

```bash
npx playwright test --grep @smoke
npx playwright test --grep-invert @slow
```

---

## 8. CI Integration

### Mock-Based CI Pipeline

```yaml
# GitHub Actions example
e2e-tests:
  steps:
    - name: Install dependencies
      run: pnpm install
    - name: Install Playwright browsers
      run: npx playwright install --with-deps chromium
    - name: Seed test database
      run: pnpm db:seed:test-user
    - name: Run E2E tests (mocked)
      run: PORT=3456 npx playwright test --project=chromium --grep-invert @smoke
```

### Sharding for Parallel CI

```yaml
strategy:
  matrix:
    shard: [1/4, 2/4, 3/4, 4/4]
steps:
  - run: npx playwright test --shard=${{ matrix.shard }}
```

### Artifacts

```yaml
- uses: actions/upload-artifact@v4
  if: failure()
  with:
    name: playwright-report
    path: test-results/
```

---

## 9. Selector Strategy

### Priority Order (Playwright official recommendation — best to worst)

1. **`role` / `aria-label`** — `page.getByRole('button', { name: 'Send' })` — Semantic, accessible, stable
2. **Label** — `page.getByLabel('Email')` — Form inputs with associated labels
3. **Text content** — `page.getByText('Submit')` — Visible text, natural to users
4. **`data-testid`** — `page.getByTestId('send-button')` — Explicit hook when no semantic option exists
5. **CSS class / XPath** — Fragile, breaks on restyling or restructure — avoid

### Rationale

Role/label/text selectors are resilient to implementation changes and test what a user actually experiences. `data-testid` requires adding test-specific attributes to production code — use only as a last resort.

### Rules

- **NEVER use CSS class selectors** in tests (e.g., `.btn-primary`, `.chat-input`)
- **Prefer role-based selectors** — they reflect accessibility and user perception
- **Scope selectors** — `message.getByRole('button', { name: 'Edit' })` not `page.getByRole('button', { name: 'Edit' })`

---

## 10. Test File Template

```typescript
import { test, expect, type Page, type BrowserContext } from '@playwright/test';
import { ChatPage } from '../pages/ChatPage';

test.describe.configure({ mode: 'serial' });

let page: Page;
let context: BrowserContext;
let chatPage: ChatPage;

test.describe('Feature Name', () => {
  test.beforeAll(async ({ browser }) => {
    context = await browser.newContext({
      storageState: 'tests/e2e/.auth/user.json',
    });
    page = await context.newPage();
    chatPage = new ChatPage(page);
  });

  test.afterAll(async () => {
    await page?.close();
    await context?.close();
  });

  test.afterEach(async () => {
    await page.unroute('**/*');
  });

  test('should do expected behavior @feature', async () => {
    // Arrange — set up mock, navigate
    await page.route('**/api/endpoint', (route) =>
      route.fulfill({ status: 200, body: '{}' })
    );
    await page.goto('/path');

    // Act — perform user action
    await chatPage.sendMessage('hello');

    // Assert — verify outcome
    await expect(chatPage.assistantMessages).toHaveCount(1);
  });
});
```

---

## 11. Fixtures for Test Data

Extend Playwright's `test` object with reusable, typed test data:

```typescript
// fixtures/test-data.ts
import { test as base } from '@playwright/test';

type TestData = {
  testUser: { email: string; password: string; name: string };
  adminUser: { email: string; password: string };
};

export const test = base.extend<TestData>({
  testUser: async ({}, use) => {
    const user = {
      email: `test-${Date.now()}@example.com`,
      password: 'Test123!@#',
      name: 'Test User',
    };
    await createTestUser(user);
    await use(user);
    await deleteTestUser(user.email);
  },

  adminUser: async ({}, use) => {
    await use({
      email: 'admin@example.com',
      password: process.env.ADMIN_PASSWORD!,
    });
  },
});

// Usage in tests
import { test } from './fixtures/test-data';

test('user can update profile', async ({ page, testUser }) => {
  await page.goto('/login');
  await page.getByLabel('Email').fill(testUser.email);
  await page.getByLabel('Password').fill(testUser.password);
  await page.getByRole('button', { name: 'Login' }).click();

  await page.goto('/profile');
  await page.getByLabel('Name').fill('Updated Name');
  await page.getByRole('button', { name: 'Save' }).click();

  await expect(page.getByText('Profile updated')).toBeVisible();
});
```

---

## 12. Visual Regression Testing

```typescript
test('homepage looks correct', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveScreenshot('homepage.png', {
    fullPage: true,
    maxDiffPixels: 100,
  });
});

test('button in all states', async ({ page }) => {
  await page.goto('/components');

  const button = page.getByRole('button', { name: 'Submit' });

  // Default state
  await expect(button).toHaveScreenshot('button-default.png');

  // Hover state
  await button.hover();
  await expect(button).toHaveScreenshot('button-hover.png');

  // Disabled state
  await button.evaluate((el) => el.setAttribute('disabled', 'true'));
  await expect(button).toHaveScreenshot('button-disabled.png');
});
```

---

## 13. Accessibility Testing

```typescript
// Install: npm install @axe-core/playwright
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('page should not have accessibility violations', async ({ page }) => {
  await page.goto('/');

  const results = await new AxeBuilder({ page })
    .exclude('#third-party-widget')
    .analyze();

  expect(results.violations).toEqual([]);
});

test('form is accessible', async ({ page }) => {
  await page.goto('/signup');

  const results = await new AxeBuilder({ page })
    .include('form')
    .analyze();

  expect(results.violations).toEqual([]);
});
```

---

## 14. Journey-Based Test Organization

Organize spec files by **user journey**, not by test type.

```
// Good — one file per user journey
tests/e2e/chat/
  chat-send-message.spec.ts
  chat-edit-message.spec.ts
  chat-branch-navigation.spec.ts

// Bad — split by test type
tests/e2e/
  chat-assertions.spec.ts
  chat-flows.spec.ts
  chat-boundaries.spec.ts
```

Each journey file contains:
- One `describe` block named after the journey
- Tests named with Actor-Based convention: `[Actor] can [action]` / `[Actor] cannot [action] when [condition]`
- `beforeAll` / `afterAll` for shared context setup
- `afterEach` to unroute mocks (LIFO cleanup order)

```typescript
test.describe('Chat — Send Message', () => {
  // ...setup

  test('User can send a message and see a response', async () => { ... });
  test('User cannot send an empty message', async () => { ... });
  test('User can send a message while a response is streaming', async () => { ... });
});
```
