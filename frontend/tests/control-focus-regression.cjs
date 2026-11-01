// Run with playwright-cli run-code --filename after opening the local catalog.
// Real browser layout/focus checks: JSDOM cannot catch fixed wrapper regressions.
async page => {
  const results = []
  await page.goto('http://db-controls.localhost:5235/tests/control-catalog.html')
  await page.getByRole('heading', { name: 'Shared controls', exact: true }).waitFor()
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const mode of ['light', 'dark', 'high_contrast']) {
      for (const fontSize of [16, 24]) {
        await page.evaluate(({ mode, fontSize }) => {
          const shell = document.querySelector('.db-staff-shell')
          shell.setAttribute('data-appearance-mode', mode)
          shell.style.setProperty('--font-size-body', `${fontSize}px`)
        }, { mode, fontSize })
        await page.keyboard.press('Tab')
        const controls = page.locator('[data-db-control]:not([data-db-control="content"]):not(:disabled)')
        let tested = 0
        for (let i = 0; i < await controls.count(); i++) {
          const control = controls.nth(i)
          if (!await control.isVisible()) continue
          await control.focus()
          const result = await control.evaluate(e => {
            const shell = e.parentElement.matches('[data-db-control-shell]') ? e.parentElement : e
            const r = e.getBoundingClientRect(), b = shell.getBoundingClientRect()
            const s = getComputedStyle(shell), inputStyle = getComputedStyle(e)
            const floor = parseFloat(s.getPropertyValue('--control-height'))
            return { name: e.getAttribute('aria-label') || e.textContent, h: r.height, box: b.height, floor,
              outline: s.outlineStyle, offset: s.outlineOffset, shadow: s.boxShadow,
              duplicate: shell !== e && inputStyle.outlineStyle !== 'none',
              excess: shell !== e && b.height - r.height > (shell.dataset.dbControlShell === 'field' ? 2.5 : .5),
              clipped: r.top < b.top - .5 || r.bottom > b.bottom + .5 }
          })
          if (result.box < result.floor - .5 || result.outline !== 'solid' || result.offset !== '-2px' || result.shadow !== 'none' || result.duplicate || result.excess || result.clipped) throw new Error(JSON.stringify({ width, mode, fontSize, ...result }))
          tested++
        }
        results.push({ width, mode, fontSize, tested })
      }
    }
  }
  await page.getByRole('heading', { name: 'Shared controls', exact: true }).click()
  await page.getByRole('button', { name: 'Overdue', exact: true }).click()
  const pointerShadow = await page.getByRole('button', { name: 'Overdue', exact: true }).evaluate(e => getComputedStyle(e).boxShadow)
  if (pointerShadow !== 'none') throw new Error('Legacy pointer focus shadow remains')
  const disabled = page.getByRole('button', { name: 'Unavailable', exact: true })
  if (!await disabled.isDisabled()) throw new Error('Disabled control became interactive')
  await page.emulateMedia({ forcedColors: 'active' })
  await page.getByRole('textbox', { name: 'Reference', exact: true }).focus()
  const forced = await page.getByRole('textbox', { name: 'Reference', exact: true }).evaluate(e => getComputedStyle(e).outlineStyle)
  if (forced !== 'solid') throw new Error('Forced-colors focus missing')
  await page.emulateMedia({ forcedColors: 'none' })
  return { results, forcedColors: 'pass' }
}
