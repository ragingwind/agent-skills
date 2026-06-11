---
name: playwright
description: Playwright E2E testing — API reference, shared browser pattern, authentication setup, assertions, and test commands.
---

# Playwright E2E Testing

Low-level Playwright API reference: commands, shared browser pattern, authentication, and assertions.

## When to Use

- Writing new E2E test files
- Running E2E tests locally
- Debugging test failures
- Setting up test authentication

## Local Testing Commands

```bash
# Run specific test file (REQUIRED format for local)
npx playwright test <test-file>.spec.ts --headed --project=chromium

# Run all E2E tests
npx playwright test --headed --project=chromium
```

**Flags:**

- `--headed` - MUST use for local / dev testing (see browser)
- `--project=chromium` - MUST specify single browser
- NEVER run multiple projects in parallel locally

## Required Test Pattern (Shared Browser)

All E2E test files MUST use this pattern:

```typescript
import { test, expect, type Page, type BrowserContext } from '@playwright/test';

// Use serial mode and share browser context
test.describe.configure({ mode: 'serial' });

let sharedPage: Page;
let sharedContext: BrowserContext;

test.describe('Feature Name', () => {
  test.beforeAll(async ({ browser }) => {
    sharedContext = await browser.newContext({
      storageState: 'tests/e2e/.auth/user.json',
    });
    sharedPage = await sharedContext.newPage();
  });

  test.afterAll(async () => {
    await sharedPage?.close();
    await sharedContext?.close();
  });

  test('should do something', async () => {
    await sharedPage.goto('/path');
    await sharedPage.waitForSelector('[role="textbox"]', { timeout: 15000 });
    // Use sharedPage instead of page parameter
  });
});
```

**Key rules:**

- Use `sharedPage` and `sharedContext` - NEVER use `page` fixture
- Use `test.describe.configure({ mode: 'serial' })` for sequential tests
- Load `storageState` from auth file in `beforeAll`
- Close browser ONLY in `afterAll`, never between tests

## Assertion Rules (CRITICAL)

- **NEVER** use weak assertions (e.g., `visible || fallback`)
- **MUST** verify API response status codes (check for 4xx/5xx errors)
- **MUST** verify content in correct location (use `[data-role]` attributes)
- **MUST** wait for and check actual API responses, not just UI changes
- **MUST** test exact user scenarios
- **NEVER** claim tests pass without running against live server
- If a test can pass when feature is broken, the test is useless

## Authentication Setup

Use `globalSetup` for one-time login:

```typescript
// tests/e2e/global-setup.ts
import { chromium, type FullConfig } from '@playwright/test';

const authFile = 'tests/e2e/.auth/user.json';

async function globalSetup(config: FullConfig) {
  const { baseURL } = config.projects[0].use;
  const browser = await chromium.launch();
  const page = await browser.newPage();

  await page.goto(`${baseURL}/login`);
  // Login steps...

  await page.context().storageState({ path: authFile });
  await browser.close();
}

export default globalSetup;
```

## Evidence Capture

Playwright records video and screenshots natively via config.

### Configuration (`playwright.config.ts`)

```typescript
use: {
  video: 'on',           // Record video for all tests
  screenshot: 'on',      // Capture screenshot on every test
  // OR: video: 'retain-on-failure'  // Only keep video when test fails
}
```

### Output

- Videos saved as `.webm` under `test-results/`
- Screenshots saved as `.png` under `test-results/`
- Output path is configurable via `outputDir` in `playwright.config.ts`

### Evidence Quality Requirements (CRITICAL)

A reviewer must be able to watch the recording and confirm the feature works. Short or blank recordings are **not acceptable evidence**.

**Minimum duration: 15–20 seconds per flow.**

**ALWAYS warm up before recording:**

Next.js dev server compiles RSC bundles on first request. Without warmup, the recording shows a loading screen, not the UI.

```typescript
// Step 1: Warm-up pass (NO recordVideo)
test.describe('0: Warm-up', () => {
  test.beforeAll(async ({ browser }) => {
    ctx = await browser.newContext({ storageState: 'tests/e2e/.auth/user.json' });
    page = await ctx.newPage();
  });
  test.afterAll(async () => { await page?.close(); await ctx?.close(); });

  for (const route of targetRoutes) {
    test(`warm ${route}`, async () => {
      await page.goto(BASE + route);
      await page.waitForLoadState('domcontentloaded');
      await page.waitForFunction(
        () => document.title !== '' && !document.title.includes('...'),
        { timeout: 30000 }
      );
      await page.waitForTimeout(2000); // let React hydrate
    });
  }
});

// Step 2: Recorded pass (WITH recordVideo)
test.describe('Feature flow', () => {
  test.beforeAll(async ({ browser }) => {
    ctx = await browser.newContext({
      storageState: 'tests/e2e/.auth/user.json',
      recordVideo: { dir: 'test-results/feature-flow', size: { width: 1280, height: 720 } },
    });
    page = await ctx.newPage();
  });
  // ...
});
```

**Slow-motion action pattern — use between EVERY action:**

```typescript
await page.goto(BASE + '/feature');
await page.waitForLoadState('domcontentloaded');
await page.waitForTimeout(2000);          // let content settle visually

// verify primary element
await expect(element).toBeVisible({ timeout: 15000 });
await page.waitForTimeout(1500);          // hold for viewer

// scroll to show more content
await page.evaluate(() => window.scrollBy(0, 400));
await page.waitForTimeout(1500);

// hover over key UI elements to show interactivity
await element.hover();
await page.waitForTimeout(1500);

// interact if applicable
await element.click();
await page.waitForTimeout(2000);

// final hold before context closes
await page.waitForTimeout(3000);
```

**Never test APIs with `page.request.get()` alone for evidence** — navigate to the page that *displays* the API result so the viewer can see it.

## Polling Assertions

Use `expect.poll()` or `expect().toPass()` instead of `waitForTimeout` when waiting for async state changes.

```typescript
// Wait for a value to reach a condition
await expect.poll(
  () => page.locator('[data-role="assistant"]').count(),
  { timeout: 10_000 }
).toBe(3);

// Wait for an assertion to pass
await expect(async () => {
  await expect(page.locator('.status')).toHaveText('done');
}).toPass({ timeout: 15_000 });

// Wait for an API call result
await expect.poll(
  async () => {
    const response = await page.request.get('/api/status');
    return response.json();
  },
  { intervals: [1000, 2000, 5000], timeout: 30_000 }
).toMatchObject({ state: 'ready' });
```

Use `toPass` when the assertion itself may throw (e.g., element not yet in DOM). Use `expect.poll` when you need to evaluate a value.

## Verification Checklist

- [ ] All test steps executed
- [ ] All screenshots examined carefully
- [ ] All pass criteria verified with evidence
- [ ] All fail indicators checked
- [ ] Only then mark as "verified"

## Common Selectors

```typescript
// Prefer data attributes over CSS classes
await sharedPage.locator('[data-role="user"]');
await sharedPage.locator('[data-role="assistant"]');
await sharedPage.locator('[role="textbox"]');
await sharedPage.locator('button[aria-label="Remove file"]');
```
