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

module.exports = { extractLaborHours };
