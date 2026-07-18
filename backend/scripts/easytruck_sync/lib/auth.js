// Credentials come from ./easytruck_sync/.env (gitignored). Never hard-code them.
require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });
const { chromium } = require('playwright');

const USER = process.env.ETS_EMAIL || process.env.EASY_TRUCK_SHOP_USER;
const PASS = process.env.ETS_PASSWORD || process.env.EASY_TRUCK_SHOP_PASS;
const SHOP = process.env.ETS_SHOP || 'sh_15mw458gpRl487OF';
const BASE = process.env.ETS_BASE_URL || 'https://easytruck.shop';

async function loginSession({ headless = true } = {}) {
  if (!USER || !PASS) throw new Error('Missing ETS_EMAIL/ETS_PASSWORD env vars (copy .env.example to .env)');
  const browser = await chromium.launch({ headless });
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  await page.locator('input[placeholder*="mail" i]').first().fill(USER);
  await page.locator('input[type="password"]').first().fill(PASS);
  await page.locator('button[type="submit"]').first().click();
  await page.waitForTimeout(3000);
  if (page.url().includes('/login')) {
    throw new Error('Login appears to have failed, still on /login');
  }
  return { browser, context, page };
}

module.exports = { loginSession, SHOP, BASE };
