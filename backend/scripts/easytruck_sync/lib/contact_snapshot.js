// Pure validation of one visibly complete account contacts page. No guessed pagination.
function contactSnapshot(view, { shop, customerId, observedAt }) {
  const result = {source_shop_id: shop, source_customer_id: String(customerId),
    observed_at: observedAt, complete: false, reason: 'schema_unsupported', phones: []};
  if (view.pathname !== `/${shop}/customers/${customerId}/contacts`) {
    result.reason = 'account_mismatch'; return result;
  }
  if (view.searchValue !== '' || view.archived !== false) {
    result.reason = 'filtered'; return result;
  }
  if (!view.headerBound || JSON.stringify(view.headers) !== JSON.stringify(['ROLE','FIRST NAME','LAST NAME','PHONE','EMAIL','NOTES'])
      || !Array.isArray(view.rows) || view.rows.some(row => row.length !== 6)) return result;
  const count = /^Showing\s+(\d+)\s+to\s+(\d+)\s+of\s+(\d+)\s+results$/.exec(view.footer.trim());
  if (!count || Number(count[3]) !== view.rows.length || Number(count[2]) !== view.rows.length
      || Number(count[1]) !== (view.rows.length ? 1 : 0) || view.rows.length > 199 || view.hasNext) {
    result.reason = 'page_incomplete'; return result;
  }
  result.complete = true; result.reason = null;
  result.phones = [...view.headerPhones, ...view.rows.map(row => row[3])].filter(value => value !== '');
  if (result.phones.length > 200) {
    result.complete = false; result.reason = 'page_incomplete'; result.phones = [];
  }
  return result;
}
module.exports = {contactSnapshot};
