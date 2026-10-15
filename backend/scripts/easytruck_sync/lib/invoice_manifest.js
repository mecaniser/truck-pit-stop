// A full, unfiltered source enumeration; a singular service.invoice is insufficient.
function mergeInvoicePages(pages, shop) {
  let expectedTotal = null;
  const seen = new Set(), services = {};
  for (let index = 0; index < pages.length; index++) {
    const props = pages[index]?.props;
    const list = props?.invoices, filters = props?.filters;
    if (pages[index]?.component !== 'invoices/index'
        || props?.user?.current_shop_public_id !== shop
        || filters?.status !== 'all' || filters?.range !== 'all' || filters?.search !== ''
        || !Array.isArray(list?.data) || list.meta.current_page !== index + 1
        || list.meta.last_page !== pages.length) throw new Error('Invoice enumeration incomplete');
    if (expectedTotal === null) expectedTotal = list.meta.total;
    if (!Number.isInteger(expectedTotal) || list.meta.total !== expectedTotal) throw new Error('Invoice enumeration changed');
    for (const invoice of list.data) {
      const invoiceId = String(invoice.id);
      if (!/^[0-9]+$/.test(invoiceId) || seen.has(invoiceId)) throw new Error('Invoice enumeration identity conflict');
      seen.add(invoiceId);
      const service = invoice.service;
      // Source component explicitly distinguishes standalone parts sales.
      // Count these in total coverage, but they are not repair invoices.
      if (invoice.type === 'SALE' && service == null) continue;
      if (invoice.type !== 'SERVICE' || !service || service.shop_id !== props.user.current_shop_id
          || String(service.int_id) !== String(invoice.service_id)
          || String(service.id) !== String(service.number)
          || !/^[0-9]+$/.test(String(service.id))) throw new Error('Invoice enumeration identity conflict');
      const group = services[String(service.id)] ||= {internal_id: String(service.int_id), invoice_ids: []};
      if (group.internal_id !== String(service.int_id)) throw new Error('Service identity conflict');
      group.invoice_ids.push(String(invoice.id));
    }
  }
  if (!pages.length || seen.size !== expectedTotal) throw new Error('Invoice enumeration incomplete');
  return Object.fromEntries(Object.entries(services).map(([id, group]) => [id, {
    complete: true, invoice_ids: group.invoice_ids.sort(),
    service_internal_id: group.internal_id, evidence_kind: 'verified_source_service_invoice_manifest',
  }]));
}

async function collectInvoiceManifest(page, base, shop) {
  const pages = [];
  let url = `${base}/${shop}/invoices?sort=number`;
  while (url) {
    if (pages.length >= 200) throw new Error('Invoice enumeration exceeds bound');
    const parsed = new URL(url, base);
    if (parsed.origin !== new URL(base).origin || parsed.pathname !== `/${shop}/invoices`) throw new Error('Invoice enumeration route mismatch');
    if (parsed.searchParams.get('sort') !== 'number') throw new Error('Invoice enumeration lost stable sort');
    await page.goto(parsed.href, {waitUntil: 'networkidle', timeout: 20000});
    if (new URL(page.url()).pathname !== parsed.pathname) throw new Error('Invoice enumeration route mismatch');
    const raw = await page.evaluate(() => document.querySelector('[data-page]')?.getAttribute('data-page'));
    const value = JSON.parse(raw);
    pages.push(value);
    url = value.props?.invoices?.links?.next;
  }
  return mergeInvoicePages(pages, shop);
}
module.exports = {mergeInvoicePages, collectInvoiceManifest};
