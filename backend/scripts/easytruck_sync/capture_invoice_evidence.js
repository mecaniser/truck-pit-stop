// Targeted source read only. Never invokes an importer or financial action.
const fs = require('node:fs');
const {parseArgs} = require('node:util');
const {loginSession, SHOP, BASE} = require('./lib/auth');
const {extractSourceEvidence} = require('./lib/invoice_json');
const {collectInvoiceManifest, applyCurrentManifest} = require('./lib/invoice_manifest');

async function main() {
  const {values: a} = parseArgs({options: {
    'tenant-id': {type:'string'}, shop:{type:'string'}, 'service-number':{type:'string'},
    'service-internal-id':{type:'string'}, 'invoice-internal-id':{type:'string'},
    'invoice-number':{type:'string'}, out:{type:'string'}, capture:{type:'boolean',default:false},
  }});
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(a['tenant-id'] || '')
      || a.shop !== SHOP || new URL(BASE).origin !== 'https://easytruck.shop'
      || !['service-number','service-internal-id','invoice-internal-id','invoice-number'].every(k => /^[0-9]+$/.test(a[k] || '')))
    throw new Error('Explicit tenant, shop and source identities required');
  if (!a.capture) {
    console.log(JSON.stringify({mode:'dry-run', tenant_id:a['tenant-id'], service_number:a['service-number'], invoice_number:a['invoice-number'], financial_actions:false}));
    return;
  }
  if (!a.out || fs.existsSync(a.out)) throw new Error('New private output path required');
  let browser;
  try {
    const session = await loginSession({headless:true});
    browser = session.browser;
    const manifests = await collectInvoiceManifest(session.page, BASE, SHOP);
    const route = `${BASE}/${SHOP}/services/${a['service-number']}/invoice`;
    await session.page.goto(route, {waitUntil:'networkidle',timeout:20000});
    if (new URL(session.page.url()).pathname !== new URL(route).pathname) throw new Error('Source route mismatch');
    const raw = await session.page.evaluate(() => document.querySelector('[data-page]')?.getAttribute('data-page'));
    if (JSON.parse(raw)?.component !== 'services/show/invoice') throw new Error('Source component mismatch');
    let evidence = extractSourceEvidence(raw);
    if (!evidence || !evidence.source_customer_id || !evidence.source_customer_uuid || String(evidence.ets_shop_id)!==a.shop || String(evidence.service_id)!==a['service-number']
        || String(evidence.service_internal_id)!==a['service-internal-id'] || String(evidence.invoice_service_id)!==a['service-internal-id']
        || String(evidence.invoice_id)!==a['invoice-internal-id'] || String(evidence.invoice_number)!==a['invoice-number'])
      throw new Error('Source identity mismatch');
    evidence = applyCurrentManifest(evidence, manifests, a['service-number'], new Date().toISOString());
    if (!evidence.invoice_manifest || JSON.stringify(evidence.invoice_manifest.invoice_ids)!==JSON.stringify([a['invoice-internal-id']]))
      throw new Error('Complete singleton manifest required');
    fs.writeFileSync(a.out, JSON.stringify({schema_version:1,capture_kind:'ets_target_invoice_evidence',tenant_id:a['tenant-id'],sourceEvidence:evidence}), {flag:'wx',mode:0o600});
    console.log(JSON.stringify({mode:'captured',financial_actions:false,source_invoice_number:a['invoice-number']}));
  } finally { if (browser) await browser.close(); }
}
if (require.main === module) main().catch(() => { console.error('Target source capture held; no financial action invoked'); process.exitCode=1; });
module.exports = {main};
