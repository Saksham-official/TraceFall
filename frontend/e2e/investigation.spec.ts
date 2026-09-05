/**
 * The investigator's journey, end to end, against a running deployment.
 *
 * Everything else in this repository tests a layer. This tests the product: a real
 * browser, real nginx, a real API, a real worker running the real pipeline, and a real
 * PDF coming back out. It is the only test that would catch a broken proxy, a container
 * that cannot write its evidence directory, or a page that renders nothing because a
 * field was renamed on one side of the wire.
 *
 * The assertions are the product's integrity rules, not its layout. Layout changes; the
 * rule that a PROBABLE inference must never read as a fact does not.
 */

import { readFileSync } from 'node:fs'

import { expect, test, type Page } from '@playwright/test'

const EMAIL = process.env.E2E_EMAIL ?? 'admin@example.gov'
const PASSWORD = process.env.E2E_PASSWORD ?? 'correct-horse-battery-staple'

// A Binance TRON wallet from their own proof-of-reserves disclosure, and the address our
// committed fixtures cover — so this runs offline against the fixture cache.
const FIXTURED_ADDRESS = 'TMuA6YqfCeX8EhbfYEg5y7S4DqzSJireY9'

async function signIn(page: Page) {
  await page.goto('/')
  await page.getByLabel(/email/i).fill(EMAIL)
  await page.getByLabel(/password/i).fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Cases' })).toBeVisible()
}

async function runAnalysis(page: Page, title: string): Promise<string> {
  await page.getByRole('link', { name: /new case/i }).first().click()
  await page.getByLabel(/^Title/).fill(title)
  await page.getByRole('button', { name: 'Continue to address' }).click()

  await page.getByLabel(/^Address/).first().fill(FIXTURED_ADDRESS)
  await page.getByRole('button', { name: 'Add address' }).click()

  await page.getByRole('button', { name: 'Start analysis' }).click()

  // The pipeline runs retrieval, normalization, tracing, graph, patterns, attribution and
  // risk. Against fixtures that is seconds, but the wait is generous: a slow assertion is
  // better than a flaky one.
  await expect(page.getByText(/analysis complete|completed/i).first()).toBeVisible({
    timeout: 120_000,
  })
  return page.url()
}

test.describe('investigation journey', () => {
  test('sign in, analyse an address, read the findings, generate a report', async ({ page }) => {
    await signIn(page)
    await runAnalysis(page, `E2E ${new Date().toISOString()}`)

    await page.getByRole('link', { name: /open findings/i }).click()
    await expect(page.getByRole('heading', { name: 'Investigation workspace' })).toBeVisible()

    // --- Overview: the question the product exists to answer ---
    await expect(page.getByText(/where the money went/i)).toBeVisible()

    // --- Attribution: the tier is always in words ---
    await page.getByRole('tab', { name: 'Attribution' }).click()
    const tiers = page.getByText(/^(Confirmed|Likely|Unattributed)/)
    await expect(tiers.first()).toBeVisible()

    // --- Risk: never a score without its breakdown and its confidence ---
    await page.getByRole('tab', { name: 'Risk' }).click()
    await expect(page.getByText(/Not a probability of fraud/i)).toBeVisible()
    await expect(page.getByRole('img', { name: /Risk \d+ of 100, band/ }).first()).toBeVisible()

    // --- Graph: the canvas, and the text list that carries the same information ---
    await page.getByRole('tab', { name: 'Graph' }).click()
    await expect(page.getByText('Addresses in this trace')).toBeVisible()
    await expect(page.getByText(/solid = confirmed/i)).toBeVisible()

    // --- Evidence: a real PDF, with the hash of the bytes on disk ---
    await page.getByRole('tab', { name: 'Evidence' }).click()
    await page.getByRole('button', { name: /generate pdf report/i }).click()
    await expect(page.getByRole('button', { name: /^PDF · / }).first()).toBeVisible({
      timeout: 60_000,
    })
    await expect(page.getByText(/sha256/i).first()).toBeVisible()
  })

  test('a report downloads as a real PDF, not a 401 error page', async ({ page }) => {
    await signIn(page)
    await runAnalysis(page, `E2E download ${Date.now()}`)
    await page.getByRole('link', { name: /open findings/i }).click()
    await page.getByRole('tab', { name: 'Evidence' }).click()
    await page.getByRole('button', { name: /generate pdf report/i }).click()

    const trigger = page.getByRole('button', { name: /^PDF · / }).first()
    await expect(trigger).toBeVisible({ timeout: 60_000 })

    // The download is fetched with the bearer token and handed to the browser as a blob:
    // a plain <a href> returned 401, because a navigation carries no Authorization header.
    const download = await Promise.all([page.waitForEvent('download'), trigger.click()]).then(
      ([event]) => event,
    )
    const path = await download.path()
    expect(path).toBeTruthy()
    const bytes = readFileSync(path as string)
    // %PDF- — an error page would otherwise satisfy a mere "a file arrived" check.
    expect(bytes.subarray(0, 5).toString()).toBe('%PDF-')
    expect(download.suggestedFilename()).toMatch(/^tracefall-.*\.pdf$/)
  })

  test('an unauthenticated visitor cannot reach a case', async ({ page }) => {
    await page.goto('/cases/00000000-0000-0000-0000-000000000000')

    await expect(page.getByRole('heading', { name: 'TraceFall' })).toBeVisible()
    await expect(page.getByLabel(/password/i)).toBeVisible()
  })

  test('the session survives a page reload', async ({ page }) => {
    // The refresh token is an httpOnly cookie; the access token is in memory only. A
    // reload must rebuild the session from the cookie rather than sign the user out.
    await signIn(page)
    await page.reload()

    await expect(page.getByRole('heading', { name: 'Cases' })).toBeVisible()
    const cookies = await page.context().cookies()
    const refresh = cookies.find((c) => c.name.includes('refresh'))
    expect(refresh?.httpOnly).toBe(true)
    // Whatever the page can read must not include the long-lived credential.
    expect(await page.evaluate(() => document.cookie)).not.toContain(refresh?.value ?? 'x')
  })

  test('the fixture-mode banner is shown, so nobody mistakes cached data for live', async ({
    page,
  }) => {
    await signIn(page)

    await expect(page.getByText(/cached snapshot/i)).toBeVisible()
  })
})
