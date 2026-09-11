"""Pure effective charge state shared by settlement and receipt projections."""
def latest(invoice):
    return max(getattr(invoice, "charge_adjustments", []) or [], key=lambda row: row.version, default=None)


def effective_tax_exempt(invoice):
    row = latest(invoice)
    return bool(row.evidence["settings"]["tax_exempt"]) if row else bool(getattr(invoice, "tax_exemption", None))


def effective_card_fee_enabled(invoice):
    row = latest(invoice)
    return row.evidence["settings"].get("card_fee_enabled", True) if row else True
