// Parses the innerText of a service's /invoice page (see 05_scrape_invoices.js)
// into structured invoice + payment data. The page has no stable DOM hooks for
// this (Vue app, no data-testid on the invoice summary), so we work off the
// rendered text, which is a fixed sequence of labelled lines once blanks are
// stripped.
//
// Sample shape (non-empty lines only):
//   SERVICE / #0337 / Paid / Unlock / COMPANY / <name> / USDOT: ... [optional]
//   ... / Invoice / <invoiceNumber> / <invoiceDate> / ITEM QUANTITY COST ... /
//   <line items with per-line "Subtotal" rows> / Fees / Fee / Shop Supplies /
//   <feeAmount> / Recommendations / Default Labor / <amt> / Default Matrix Parts /
//   <amt> / Fees / <feesTotal> / Discount / <discountAmt> / Subtotal / <subtotal> /
//   % <rate> Tax / <taxAmt> / Total / <totalAmt> / Internal Notes / Add / PROFIT /
//   Labor (N%) / <amt> / Part (N%) / <amt> / Payments /
//   [<amount> / <date>]* / (E-mail History | Recent Activity) / ...

const MONEY_RE = /^-?\$[\d,]+\.\d{2}$/;
const DATE_RE = /^\d{2}\/\d{2}\/\d{4}$/;

function toNumber(money) {
  if (money == null) return null;
  return Number(money.replace(/[$,]/g, ''));
}

function parseInvoicePage(text) {
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

  const result = {
    invoiceStatus: null,
    invoiceNumber: null,
    invoiceDate: null,
    // ETS's own labor/parts split for the service. Without it the importer
    // books every job as 100% labor, so Part Revenue reports as zero while ETS
    // shows a real parts figure.
    laborTotal: null,
    partsTotal: null,
    fees: null,
    discount: null,
    subtotal: null,
    taxRate: null,
    tax: null,
    total: null,
    payments: [],
  };

  const serviceIdx = lines.indexOf('SERVICE');
  if (serviceIdx !== -1 && lines[serviceIdx + 2]) {
    result.invoiceStatus = lines[serviceIdx + 2]; // e.g. "Paid"
  }

  // "Invoice" section header: Invoice / <number> / <date>. Distinguish from the
  // earlier "Invoice" nav-tab line by requiring the next two lines to be a bare
  // number and a date.
  for (let i = 0; i < lines.length; i++) {
    if (
      lines[i] === 'Invoice' &&
      /^\d+$/.test(lines[i + 1] || '') &&
      DATE_RE.test(lines[i + 2] || '')
    ) {
      result.invoiceNumber = lines[i + 1];
      result.invoiceDate = lines[i + 2];
      break;
    }
  }

  // "Recommendations" block: ETS's labor and parts subtotals for the service.
  for (let i = 0; i < lines.length; i++) {
    if (lines[i] === 'Default Labor' && MONEY_RE.test(lines[i + 1] || '')) {
      result.laborTotal = toNumber(lines[i + 1]);
    } else if (lines[i] === 'Default Matrix Parts' && MONEY_RE.test(lines[i + 1] || '')) {
      result.partsTotal = toNumber(lines[i + 1]);
    }
  }

  // Summary block: walk from the end backwards so we land on the final
  // (post-line-items) Subtotal/Fees/Total rather than any per-line-item ones.
  let totalIdx = -1;
  for (let i = lines.length - 1; i >= 0; i--) {
    if (lines[i] === 'Total' && MONEY_RE.test(lines[i + 1] || '')) {
      totalIdx = i;
      result.total = toNumber(lines[i + 1]);
      break;
    }
  }

  if (totalIdx !== -1) {
    for (let i = totalIdx - 1; i >= 0; i--) {
      const line = lines[i];
      const next = lines[i + 1];
      if (result.tax === null && /^%\s*[\d.]+\s*Tax$/.test(line) && MONEY_RE.test(next || '')) {
        result.taxRate = parseFloat(line.match(/[\d.]+/)[0]);
        result.tax = toNumber(next);
      } else if (result.subtotal === null && line === 'Subtotal' && MONEY_RE.test(next || '')) {
        result.subtotal = toNumber(next);
      } else if (result.discount === null && line === 'Discount' && MONEY_RE.test(next || '')) {
        result.discount = toNumber(next);
      } else if (result.fees === null && line === 'Fees' && MONEY_RE.test(next || '')) {
        result.fees = toNumber(next);
        break; // Fees is the earliest field in the summary block; stop here.
      }
    }
  }

  // Payments: list of (amount, date) pairs between "Payments" and the next
  // known section ("E-mail History" or "Recent Activity"). No payment method
  // is rendered on this page.
  const paymentsIdx = lines.indexOf('Payments');
  if (paymentsIdx !== -1) {
    let end = lines.length;
    for (let i = paymentsIdx + 1; i < lines.length; i++) {
      if (lines[i] === 'E-mail History' || lines[i] === 'Recent Activity') {
        end = i;
        break;
      }
    }
    for (let i = paymentsIdx + 1; i < end - 1; i++) {
      if (MONEY_RE.test(lines[i]) && DATE_RE.test(lines[i + 1] || '')) {
        result.payments.push({ amount: toNumber(lines[i]), date: lines[i + 1] });
        i++; // skip the date we just consumed
      }
    }
  }

  return result;
}

module.exports = { parseInvoicePage };
