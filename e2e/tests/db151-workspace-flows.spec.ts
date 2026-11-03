import { expect, test, type Page } from '@playwright/test'

// Opt in against the populated, local DB151 Quiet QA shop. These journeys only read business records.
const root = process.env.DB151_QA_URL
const lastStart = new Map<string, number>()
async function signIn(page: Page, role: string, width: number) {
  const email = process.env[`DB151_${role}_EMAIL`]
  const password = process.env[`DB151_${role}_PASSWORD`]
  test.skip(!root || !email || !password, 'Local DB151 QA session required')
  expect(new URL(root!).hostname).toBe('127.0.0.1')
  const last = lastStart.get(role)
  if (last) await new Promise(resolve => setTimeout(resolve, Math.max(0, 65_000 - (Date.now() - last))))
  lastStart.set(role, Date.now())
  await page.setViewportSize({ width, height: 900 })
  await page.goto(`${root}/dashboard`)
  await page.locator('input[type=email]').fill(email!)
  await page.locator('input[type=password]').fill(password!)
  await page.getByRole('button', { name: /^Sign in$/i }).click()
  await expect(page.locator('.db-overview')).toBeVisible()
}

for (const width of [1440, 390]) {
  for (const role of ['OWNER', 'ADMIN']) {
    test(`DB151 ${role} workspace round trips at ${width}px`, async ({ page }) => {
      await signIn(page, role, width)

      await test.step('Customer History → repair order → same expanded history and search', async () => {
        await page.goto(`${root}/dashboard/customers`)
        const search = page.getByPlaceholder('Search by name, email, or phone...').filter({ visible: true })
        await search.fill('DB151')
        await page.getByRole('button', { name: /Open DB151 Test Freight customer workspace/ }).first().click()
        const history = page.getByRole('button', { name: 'History', exact: true })
        await history.click()
        const order = 'DB151-quiet-1048'
        await page.getByRole('button', { name: order, exact: true }).click()
        const open = page.getByRole('link', { name: `Open repair order ${order}`, exact: true })
        await expect(open).toBeVisible()
        if (role === 'OWNER' && width === 1440) {
          const [tab] = await Promise.all([page.context().waitForEvent('page'), open.click({ modifiers: ['ControlOrMeta'] })])
          await expect(tab.getByRole('heading', { name: `#${order}`, exact: true })).toBeVisible()
          await tab.close()
          await expect(open).toBeVisible()
        }
        // Test the full detour both ways before reloading the customer route.
        for (const back of [true, false]) {
          await open.click()
          await expect(page.getByRole('heading', { name: `#${order}`, exact: true })).toBeVisible()
          if (back) await page.goBack()
          else await page.getByRole('button', { name: 'Back to customer record', exact: true }).click()
          await expect(history).toHaveAttribute('aria-pressed', 'true')
          await expect(open).toBeFocused()
          await expect(page.getByPlaceholder('Search by name, email, or phone...').first()).toHaveValue('DB151')
        }
        await page.reload()
        await expect(history).toHaveAttribute('aria-pressed', 'true')
        await expect(open).toBeVisible()
        if (role === 'ADMIN') {
          await expect(page.getByRole('button', { name: 'Account', exact: true })).toHaveCount(0)
          const account = new URL(page.url())
          account.searchParams.set('tab', 'account')
          await page.goto(account.toString())
          await expect(page.getByText('Account review is not available with your permissions.')).toBeVisible()
        }
        if (role === 'OWNER' && width === 1440) await page.screenshot({ path: test.info().outputPath('customer-history.png') })
      })

      await test.step('Repair preview stays in the ledger, opening and closing restores the row', async () => {
        await page.goto(`${root}/dashboard/repair-orders?queue=ready_to_close`)
        const order = 'DB151-quiet-1049'
        const preview = page.getByRole('button', { name: `Show preview for ${order}` })
        await preview.click()
        await expect(page).not.toHaveURL(/selected=/)
        const row = page.getByRole('button', { name: `Open repair order ${order}`, exact: true })
        await row.click()
        await expect(page.getByRole('heading', { name: `#${order}` })).toBeVisible()
        await page.goBack()
        await expect(row).toBeFocused()
        await row.click()
        await expect(page.getByRole('heading', { name: `#${order}` })).toBeVisible()
        await page.getByRole('button', { name: 'Close repair order', exact: true }).click()
        await expect(row).toBeFocused()
        await expect(page).toHaveURL(/queue=ready_to_close/)
      })

      await test.step('Filtered reorder list → exact part → Purchasing → same part and tab', async () => {
        await page.goto(`${root}/dashboard/garage/inventory`)
        const reorder = page.getByRole('button', { name: /^Needs reorder/ })
        await expect(reorder).toHaveCount(1)
        await reorder.click()
        const search = page.getByRole('searchbox', { name: 'Search parts' })
        await search.fill('T30')
        await expect(page.getByRole('group', { name: 'Stock filter' })).toHaveCount(0)
        await page.locator('.db-parts-workbench__row-select').filter({ hasText: 'Brake chamber' }).click()
        const ordering = page.getByRole('tab', { name: 'Ordering' })
        await ordering.click()
        const partUrl = page.url()
        await page.reload()
        await expect(ordering).toHaveAttribute('aria-selected', 'true')
        const purchasing = page.getByRole('link', { name: 'Open Purchasing', exact: true })
        await purchasing.click()
        await expect(page.getByRole('heading', { name: 'Purchasing', exact: true })).toBeVisible()
        await page.goBack()
        await expect(page).toHaveURL(partUrl)
        await expect(purchasing).toBeFocused()
        await purchasing.click()
        await page.getByRole('link', { name: 'Back to part' }).click()
        await expect(page).toHaveURL(partUrl)
        await expect(page.locator('#selected-part-name')).toHaveText(/Brake chamber/)
        await expect(ordering).toHaveAttribute('aria-selected', 'true')
        await expect(purchasing).toBeFocused()
        if (width === 390) {
          await page.getByRole('button', { name: 'Back to parts', exact: true }).click()
          await expect(page.locator('.db-parts-workbench__row-select').filter({ hasText: 'Brake chamber' })).toBeFocused()
        }
        await expect(page.getByPlaceholder('Search part, SKU, supplier, source number, or bin')).toHaveValue('T30')
        await page.getByRole('button', { name: /^All parts/ }).click()
        await search.fill('Oil filter')
        await page.locator('.db-parts-workbench__row-select').filter({ hasText: 'Oil filter' }).click()
        await ordering.click()
        const oilUrl = page.url()
        const incoming = page.locator('.db-parts-workbench__linked-row').filter({ hasText: 'DB151-PO-208' }).first()
        await incoming.click()
        await expect(page.getByRole('heading', { name: 'DB151-PO-208', exact: true })).toBeVisible()
        await page.getByRole('link', { name: 'Back to part' }).click()
        await expect(page).toHaveURL(oilUrl)
        await expect(incoming).toBeFocused()
        if (role === 'OWNER' && width === 1440) {
          await expect(page.locator('.db-parts-workbench__row-select').filter({ hasText: 'Oil filter' })).toBeVisible()
          await page.screenshot({ path: test.info().outputPath('inventory-ordering.png') })
        }
      })

      await test.step('Draft → Receiving → Back restores draft; eligible PO survives Receiving', async () => {
        await page.goto(`${root}/dashboard/garage/purchasing?view=orders`)
        const draft = 'DB151-PO-209'
        await page.getByRole('button', { name: new RegExp(draft) }).first().click()
        await expect(page.getByRole('heading', { name: draft, exact: true })).toBeVisible()
        await expect(page.getByRole('button', { name: new RegExp(draft) }).first()).toBeFocused()
        const url = page.url()
        await page.getByRole('button', { name: 'Receiving', exact: true }).click()
        await expect(page.getByRole('heading', { name: 'DB151-PO-208', exact: true })).toBeVisible()
        await page.goBack()
        await expect(page).toHaveURL(url)
        await expect(page.getByRole('heading', { name: draft, exact: true })).toBeVisible()
        await page.getByRole('button', { name: /DB151-PO-208/ }).first().click()
        await expect(page.getByRole('heading', { name: 'DB151-PO-208', exact: true })).toBeVisible()
        const selected = new URL(page.url()).searchParams.get('purchase_order')
        await page.getByRole('button', { name: 'Receiving', exact: true }).click()
        await expect(page.getByRole('heading', { name: 'DB151-PO-208', exact: true })).toBeVisible()
        expect(new URL(page.url()).searchParams.get('purchase_order')).toBe(selected)
        await expect(page.getByRole('link', { name: 'Back to part' })).toHaveCount(0)
        const invalidReceiving = new URL(url)
        invalidReceiving.searchParams.set('view', 'receiving')
        await page.goto(invalidReceiving.toString())
        await page.getByRole('button', { name: 'View purchase order', exact: true }).click()
        await expect(page.getByRole('heading', { name: draft, exact: true })).toBeVisible()
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width)
      })
    })
  }
}

for (const [role, width] of [['OWNER', 1440], ['ADMIN', 390]] as const) {
  test(`DB151 ${role} secondary lists at ${width}px`, async ({ page }) => {
    await signIn(page, role, width)
    await page.goto(`${root}/dashboard/customers`)
    await page.getByRole('button', { name: /Open DB151 Test Freight customer workspace/ }).first().click()
    await page.locator('.db-customer-trucks__row').filter({ hasText: '604' }).first().click()
    const visit = page.getByRole('link', { name: 'Open repair order DB151-quiet-1048' })
    await visit.click()
    await page.getByRole('button', { name: 'Back to customer record' }).click()
    await expect(visit).toBeFocused()
    await expect(page.getByRole('region', { name: 'Vehicle repair history' })).toBeVisible()

    await page.goto(`${root}/dashboard/garage/inventory`)
    await page.getByRole('button', { name: 'Activity', exact: true }).click()
    const activity = page.getByRole('searchbox', { name: 'Search Activity' })
    await activity.fill('Brake chamber')
    await page.getByRole('button', { name: 'Apply', exact: true }).click()
    await page.reload()
    await expect(activity).toHaveValue('Brake chamber')
    await page.getByRole('link', { name: 'Purchasing', exact: true }).click()
    await page.goBack()
    await expect(activity).toHaveValue('Brake chamber')

    await page.goto(`${root}/dashboard/garage/purchasing?view=suppliers`)
    const suppliers = page.getByPlaceholder('Search suppliers by name, contact, phone, or address...')
    await suppliers.fill('No matching QA supplier')
    await expect(page.getByText('No suppliers match your search.', { exact: true })).toBeVisible()
    await page.reload()
    await expect(suppliers).toHaveValue('No matching QA supplier')
    await page.getByRole('button', { name: 'Returns & cores', exact: true }).click()
    await page.getByRole('tab', { name: 'Cores', exact: true }).click()
    await page.getByRole('button', { name: /Brake chamber/ }).click()
    const core = new URL(page.url()).searchParams.get('core')
    expect(core).toBeTruthy()
    await page.getByRole('tab', { name: 'Returns', exact: true }).click()
    await page.goBack()
    await expect(page.getByRole('tab', { name: 'Cores', exact: true })).toHaveAttribute('aria-selected', 'true')
    expect(new URL(page.url()).searchParams.get('core')).toBe(core)
  })
}
