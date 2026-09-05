import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests against a running deployment.
 *
 * These are deliberately not part of `npm test`. They need a live stack — API, worker,
 * database, Redis and nginx — and a seeded administrator, so running them by accident
 * from a laptop with nothing up produces a confusing failure rather than a useful one.
 *
 *   docker compose up -d
 *   docker compose exec api alembic upgrade head
 *   docker compose exec api python -m app.cli load-labels
 *   docker compose exec api python -m app.cli create-admin --email ... --full-name ...
 *   npm run e2e
 *
 * Point them elsewhere with E2E_BASE_URL, and supply credentials with E2E_EMAIL and
 * E2E_PASSWORD. Nothing is hard-coded, because a password in a committed config is a
 * password in the repository.
 *
 * **Every test signs in, and the API allows ten sign-ins per minute per IP.** Sharing one
 * saved session instead was tried and does not work: the refresh cookie rotates on use, so
 * the second test to restore it presents a token the first already spent. Adding tests past
 * that ceiling means raising `LOGIN_PER_IP` for the test environment, not working around it.
 */
export default defineConfig({
  testDir: './e2e',
  // The pipeline is network- and provider-bound; a per-test cap below that is just flake.
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? [['github'], ['list']] : [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
