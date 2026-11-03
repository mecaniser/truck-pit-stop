import { expect, test, type Page } from '@playwright/test'

const root = process.env.DB151_SIGNOUT_QA_URL
const password = process.env.DB151_SIGNOUT_QA_PASSWORD
const closeout = '/dashboard?work_view=closeout'
const row = (page: Page, shop: 'A' | 'B') =>
  page.getByRole('button', { name: `Open PRIVATE-${shop}-1049 in Repair Orders` })

async function signIn(page: Page, shop: 'A' | 'B') {
  await page.getByRole('textbox', { name: 'Email Address' }).fill(`lifecycle-${shop.toLowerCase()}@example.com`)
  await page.locator('input[type=password]').fill(password!)
  await page.getByRole('button', { name: /^Sign in$/i }).click()
  await expect(page.getByRole('heading', { name: 'Shop Work', exact: true })).toBeVisible()
  await page.getByRole('button', { name: /^Closeout/ }).click()
  await expect(row(page, shop)).toBeVisible()
}

for (const width of [1440, 390]) {
  test(`sign-out clears warm Closeout before the response and isolates the next shop at ${width}px`, async ({ context, page }) => {
    test.skip(!root || !password, 'Requires two synthetic DB151 local QA shops')
    expect(new URL(root!).hostname).toMatch(/^(127\.0\.0\.1|localhost|[\w-]+\.localhost)$/)
    const previousShop = /PRIVATE-A-|Lifecycle A private/
    // Observe rendered DOM across reload and Back, so a transient old row fails
    // the test even if the final view is clean.
    await context.addInitScript(() => {
      new MutationObserver(() => {
        if (sessionStorage.getItem('qa-watch-shop-a') && /PRIVATE-A-|Lifecycle A private/.test(document.body?.innerText ?? '')) {
          sessionStorage.setItem('qa-old-shop-visible', 'yes')
        }
      }).observe(document, { subtree: true, childList: true, characterData: true })
    })
    await page.setViewportSize({ width, height: 870 })
    await page.goto(root! + '/login')
    await signIn(page, 'A')
    await row(page, 'A').click()
    await expect(page.getByRole('heading', { name: '#PRIVATE-A-1049' })).toBeVisible()
    const previousOrderUrl = page.url()
    await page.getByRole('button', { name: 'Close repair order' }).click()
    const peer = await context.newPage()
    await peer.goto(root! + closeout)
    await expect(row(peer, 'A')).toBeVisible()

    // Stay in the same document to keep the real app cache warm.
    if (width < 768) {
      await page.getByRole('button', { name: 'More', exact: true }).click()
      await page.getByRole('link', { name: 'Profile', exact: true }).click()
    } else {
      await page.getByRole('link', { name: /Open profile settings/ }).click()
    }
    const security = page.getByRole('button', { name: 'Security', exact: true }).filter({ visible: true })
    if (width < 1024) await page.locator('.db-settings-mobile-section-selector__trigger').click()
    await security.click()
    const pending = page.waitForRequest(req => req.method() === 'POST' && req.url().endsWith('/auth/logout'))
    let release!: () => void
    const held = new Promise<void>(resolve => { release = resolve })
    await page.route('**/auth/logout', async route => { await held; await route.continue() })
    try {
      await page.getByRole('button', { name: /^Sign out$/i }).click()
      await pending
      await expect(page.getByText('Signing out…')).toBeVisible()
      // The other tab never navigated away from Closeout.
      await expect(row(peer, 'A')).toHaveCount(0)
      await Promise.all([page, peer].map(tab => tab.evaluate(() => sessionStorage.setItem('qa-watch-shop-a', 'yes'))))
      const privateReads: string[] = []
      const observeRequest = (request: { url(): string }) => {
        const path = new URL(request.url()).pathname
        if (/^\/api\/v1\/(dashboard|repair-orders|communications|activity|auth\/me|auth\/workos\/me)\b/.test(path)) privateReads.push(path)
      }
      context.on('request', observeRequest)
      await peer.reload()
      await expect(peer.getByRole('button', { name: /^Sign in$/i })).toBeVisible()
      await expect(row(peer, 'A')).toHaveCount(0)
      await page.goBack()
      await expect(page.getByText('Signing out…')).toBeVisible()
      context.off('request', observeRequest)
      expect(privateReads).toEqual([])
    } finally {
      release()
    }
    await signIn(page, 'B')
    await expect(row(page, 'A')).toHaveCount(0)
    await page.reload()
    await expect(row(page, 'B')).toBeVisible()
    await page.getByRole('button', { name: 'Overview', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Needs your attention' })).toBeVisible()
    await expect(page.getByText('Lifecycle B private stock', { exact: true })).toBeVisible()
    await expect(page.locator('body')).not.toContainText(previousShop)
    await page.goBack()
    await expect(page.locator('body')).not.toContainText(previousShop)
    // Try the exact old selected repair under B's real server credentials.
    const denied = page.waitForResponse(response => response.url().includes('/repair-orders/') &&
      response.url().includes(new URL(previousOrderUrl).searchParams.get('selected')!) && [403, 404].includes(response.status()))
    await page.goto(previousOrderUrl)
    await denied
    await expect(page.locator('body')).not.toContainText(previousShop)
    await peer.goto(root! + closeout)
    await expect(row(peer, 'B')).toBeVisible()
    await expect(row(peer, 'A')).toHaveCount(0)
    for (const tab of [peer, page]) expect(await tab.evaluate(() => sessionStorage.getItem('qa-old-shop-visible'))).toBeNull()
  })
}
