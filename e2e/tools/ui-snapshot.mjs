#!/usr/bin/env node
/**
 * Open a signed-in staff page in a real browser, screenshot it, and optionally
 * measure it.
 *
 * Reviewing a change to the staff workspace meant either clicking through the
 * app by hand or trusting that a unit test covering the same code proved the
 * screen was right. It does not: a rule that loses on specificity still has its
 * class applied, type that ignores the size setting still renders, and a menu
 * whose contents overflow its own panel still passes every assertion about the
 * contents. Each of those shipped. This is the loop that caught them.
 *
 * It signs in by minting a token inside the running API container and seeding
 * the store the app persists to, because the login form needs a password no
 * developer environment should be holding.
 *
 * Local development only. It refuses any target that is not loopback, and it
 * needs the dev API container from docker-compose.parallel.yml.
 *
 *   node tools/ui-snapshot.mjs /dashboard/repair-orders out.png
 *   node tools/ui-snapshot.mjs /dashboard/settings out.png --width 1400
 *   CLICK='.db-settings-nav-item:has-text("Appearance")' node tools/ui-snapshot.mjs /dashboard/settings out.png
 *   MEASURE='.db-repair-orders-new__status-select ul' node tools/ui-snapshot.mjs /dashboard/repair-orders out.png
 */
import { chromium } from 'playwright'
import { execFileSync } from 'node:child_process'

const API_CONTAINER = process.env.DIESELBRIDGE_API_CONTAINER ?? 'dieselbridge_api_claude'
const ORIGIN = process.env.DIESELBRIDGE_WEB_ORIGIN ?? 'http://127.0.0.1:5174'
const EMAIL = process.env.DIESELBRIDGE_UI_USER ?? 'truxpitstop@gmail.com'

const [route, out] = process.argv.slice(2).filter((a) => !a.startsWith('--'))
const flag = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`)
  return i === -1 ? fallback : Number(process.argv[i + 1])
}
if (!route || !out) {
  console.error('usage: ui-snapshot.mjs <route> <out.png> [--width N] [--height N]')
  process.exit(1)
}
// A signed-in session is minted here. Never point it at anything but this machine.
if (!/^http:\/\/(127\.0\.0\.1|localhost)(:|$)/.test(ORIGIN)) {
  console.error(`refusing a non-loopback target: ${ORIGIN}`)
  process.exit(1)
}

const MINT = `
import asyncio, json
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models.user import User
from app.core.security import create_access_token, create_refresh_token
async def main():
    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(User).where(User.email == ${JSON.stringify(EMAIL)}))).scalar_one()
        tv = getattr(u, 'token_version', 0) or 0
        print(json.dumps({
            'token': create_access_token({'sub': str(u.id)}, tenant_id=str(u.tenant_id), token_version=tv),
            'refresh': create_refresh_token({'sub': str(u.id)}, token_version=tv),
            'user_id': str(u.id),
        }))
asyncio.run(main())
`

function mint() {
  const raw = execFileSync('docker', ['exec', API_CONTAINER, 'python', '-c', MINT], { encoding: 'utf8' })
  return JSON.parse(raw.trim().split('\n').at(-1))
}

async function fetchUser(token) {
  const base = ORIGIN.replace(/:\d+$/, ':8001')
  const api = process.env.DIESELBRIDGE_API_ORIGIN ?? base
  const res = await fetch(`${api}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) throw new Error(`GET /auth/me -> ${res.status}`)
  return res.json()
}

const creds = mint()
const user = await fetchUser(creds.token)

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: flag('width', 1500), height: flag('height', 950) } })

// authProvider must say legacy: left unset, the app probes the WorkOS session
// endpoints, gets 401, and signs itself out. The refresh token must be real and
// unused for the same reason — it is single use, soeach run mints its own.
await page.addInitScript(
  ([token, refresh, u]) => {
    localStorage.setItem('auth-storage', JSON.stringify({
      state: { token, refreshToken: refresh, user: u, isAuthenticated: true, authProvider: 'legacy' },
      version: 0,
    }))
  },
  [creds.token, creds.refresh, user],
)

const consoleErrors = []
page.on('pageerror', (e) => consoleErrors.push(e.message.slice(0, 200)))

await page.goto(ORIGIN + route)
try {
  await page.waitForSelector('.db-staff-shell', { timeout: 15000 })
} catch {
  console.error(`!! staff shell never rendered, landed on ${page.url()}`)
}
await page.waitForTimeout(2500)

if (process.env.CLICK) {
  // The settings nav renders a desktop and a mobile copy; clicking the first
  // match hits whichever is hidden at this width.
  const all = page.locator(process.env.CLICK)
  const count = await all.count()
  let clicked = false
  for (let i = 0; i < count; i += 1) {
    const el = all.nth(i)
    if (await el.isVisible().catch(() => false)) {
      await el.click({ timeout: 5000 }).then(() => { clicked = true }).catch(() => {})
      if (clicked) break
    }
  }
  console.log(`click ${process.env.CLICK}: ${clicked ? 'ok' : 'FAILED'} (${count} matches)`)
  await page.waitForTimeout(900)
}

if (process.env.MEASURE) {
  const box = await page.evaluate((sel) => {
    const el = document.querySelector(sel)
    if (!el) return { error: `no element matches ${sel}` }
    const r = el.getBoundingClientRect()
    const cs = getComputedStyle(el)
    // Whether the box scrolls is not the question — with overflow-y:auto the
    // browser computes overflow-x to auto as well, so asking "is it scrollable"
    // silently excuses horizontal clipping. Ask whether the content fits.
    const fitsX = el.scrollWidth <= el.clientWidth + 1
    const fitsY = el.scrollHeight <= el.clientHeight + 1
    const inner = el.getBoundingClientRect()
    const past = [...el.querySelectorAll('*')]
      .filter((c) => c.getBoundingClientRect().right > inner.right - parseFloat(cs.paddingRight || 0) + 1)
      .map((c) => (c.textContent || '').trim().slice(0, 30))
      .filter(Boolean)
    return {
      width: Math.round(r.width), height: Math.round(r.height),
      fontSize: cs.fontSize,
      contentFitsHorizontally: fitsX,
      contentFitsVertically: fitsY,
      pastRightEdge: [...new Set(past)].slice(0, 6),
    }
  }, process.env.MEASURE)
  console.log(JSON.stringify(box, null, 1))
}

await page.screenshot({ path: out })
console.log(`url: ${page.url()}`)
console.log(`shell: ${await page.evaluate(() => Boolean(document.querySelector('.db-staff-shell')))}`)
if (consoleErrors.length) console.log('page errors:', consoleErrors.slice(0, 3))
await browser.close()
