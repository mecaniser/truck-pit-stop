// Reads the invoice page's embedded Inertia payload (the <div data-page="...">
// attribute every route on this Laravel/Inertia app carries) for the one field
// that is not present anywhere in the rendered text: labor hours.
//
// DieselBridge's "Invoiced Hours" report reads Labor.hours, and the only source
// the scraper had was the service-history row's clock duration, which is
// "0:00 Minutes" on literally every row (this shop does not use time-clocking —
// ETS's own "Clocked Hours" tile is 0.0). That produced a hardcoded 1.00h
// fallback per repair order — 117h against ETS's 683.2h for the same month.
//
// ETS's own dashboard sources "Invoiced Hours" from a dedicated endpoint,
// /reports/dashboard/charts/invoiced-hours, whose weekly buckets summed to
// 683.2h exactly. Reverse-engineered by comparing several invoices' rendered
// quantities against their embedded JSON:
//
//   - invoice.lines is an array of GROUPS (one per service item/operation);
//     each group's own .lines holds the real Labor/Part rows.
//   - A labor line's quantity.unit is 101 (minutes) when billed by time, or
//     120 (a count) when billed flat/per-unit — "8" tires, not 8 hours.
//   - service_item.charged (always unit 101, i.e. minutes) is present on
//     EVERY labor line regardless of billing method, and is that line's
//     dollar total converted at the shop's standard labor rate — verified
//     across a dozen lines at exactly $100/hour here, both time- and
//     count-billed. This is what "Invoiced Hours" sums.
//
// Verified: summing service_item.charged across every labor line on every
// invoice dated in August 2026 gave 683.10h against ETS's reported 683.2h
// (a 0.1h rounding difference, i.e. matches to 0.01%).
function extractLaborHours(rawDataPage) {
  if (!rawDataPage) return null;
  let data;
  try {
    data = JSON.parse(rawDataPage);
  } catch {
    return null;
  }
  const groups = data?.props?.service?.invoice?.lines;
  if (!Array.isArray(groups)) return null;

  let minutes = 0;
  let sawAny = false;
  for (const group of groups) {
    for (const line of group?.lines || []) {
      if (line.sales_type !== "Labor") continue;
      const charged = line.service_item?.charged;
      if (!charged || typeof charged.amount !== "number") continue;
      sawAny = true;
      // Every sample so far is unit 101 (minutes). Guard rather than
      // silently mis-convert if ETS ever uses a different unit.
      if (charged.unit !== 101) continue;
      minutes += charged.amount;
    }
  }
  if (!sawAny) return null;
  return Math.round((minutes / 60) * 100) / 100;
}

// Retain only an unambiguous receipt marker; never persist free-form Notes.
function receiptReference(payment) {
  const values = [payment.notes, payment.note].filter(v => typeof v === 'string' && v.length <= 4096);
  const refs = new Set();
  for (const value of values) {
    for (const match of value.matchAll(/\bDBN-RECEIPT:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?![A-Za-z0-9_-])/g)) {
      refs.add(`DBN-RECEIPT:${match[1].toLowerCase()}`);
    }
  }
  return refs.size === 1 ? [...refs][0] : null;
}

function paymentDateSemantics(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)$/.test(value)) return 'source_datetime_unverified';
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value.slice(0, 10)
    ? 'source_datetime_utc' : 'source_datetime_unverified';
}

// This is source evidence only, never a settlement assertion. Do not retain
// arbitrary Inertia fields: they include contacts, notes and session data.
function extractSourceEvidence(rawDataPage) {
  let service, user;
  try { const props = JSON.parse(rawDataPage)?.props; service = props?.service; user = props?.user; } catch { return null; }
  if (!service || !service.invoice || typeof service.invoice !== 'object') return null;
  const scalar = value => (typeof value === 'string' && value.length <= 160)
    || (typeof value === 'number' && Number.isFinite(value))
    || typeof value === 'boolean' ? value : null;
  const money = value => value && typeof value === 'object' ? {
    amount: scalar(value.amount), currency: scalar(value.currency),
  } : null;
  const invoice = service.invoice;
  if (service.int_id == null || invoice.service_id == null
      || String(service.int_id) !== String(invoice.service_id)
      || service.id == null || String(service.id) !== String(service.number)) return null;
  const lines = Array.isArray(invoice.payment_lines) ? invoice.payment_lines : [];
  return {
    schema_version: 1,
    source: 'easy_truck_shop',
    ets_shop_id: user?.current_shop_public_id && service.shop_id === user.current_shop_id ? scalar(user.current_shop_public_id) : null,
    settlement_semantics: 'unverified',
    service_id: scalar(service.id),
    service_internal_id: scalar(service.int_id),
    invoice_service_id: scalar(invoice.service_id),
    completed_at_source: scalar(service.completed_at),
    completed: typeof service.completed === 'boolean' ? service.completed : null,
    service_status: Number.isInteger(service.status) ? service.status : null,
    invoice_id: scalar(invoice.id),
    invoice_number: scalar(invoice.number),
    invoice_status: scalar(invoice.status),
    currency: scalar(invoice.currency),
    total: money(invoice.total),
    balance: money(invoice.balance),
    payment_lines_truncated: lines.length > 200,
    payment_lines: lines.slice(0, 200).map(line => {
      const payment = line?.payment || {};
      return {
        id: scalar(line?.id), amount: money(line?.amount),
        payment: {
          id: scalar(payment.id), date_source: scalar(payment.date),
          date_semantics: paymentDateSemantics(payment.date),
          ...(receiptReference(payment) ? {dbn_receipt_reference: receiptReference(payment)} : {}),
          status: scalar(payment.status), type: scalar(payment.type),
          provider: scalar(payment.provider), qb_reference: scalar(payment.qb_reference),
          total: money(payment.total), credit_total: money(payment.credit_total),
          unapplied_amount: money(payment.unapplied_amount),
          canceled: scalar(payment.canceled),
        },
      };
    }),
  };
}

module.exports = { extractLaborHours, extractSourceEvidence, receiptReference, paymentDateSemantics };
