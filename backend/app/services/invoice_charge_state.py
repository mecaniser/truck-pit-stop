"""Pure effective charge state shared by settlement and receipt projections."""
def latest(invoice):
    return max(getattr(invoice, "charge_adjustments", []) or [], key=lambda row: row.version, default=None)


def effective_tax_exempt(invoice):
    row = latest(invoice)
    return bool(row.evidence["settings"]["tax_exempt"]) if row else bool(getattr(invoice, "tax_exemption", None))
