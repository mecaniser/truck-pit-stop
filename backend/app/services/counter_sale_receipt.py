"""Branded immutable counter-sale receipt rendering."""
from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

from app.db.models.inventory_lifecycle import CounterSaleReturn
from app.db.models.tenant import Tenant


def generate_counter_sale_receipt_pdf(*, tenant: Tenant, snapshot: dict[str, Any], returns: list[CounterSaleReturn]) -> bytes:
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=.55 * inch, rightMargin=.55 * inch, topMargin=.55 * inch, bottomMargin=.55 * inch)
    story = [Paragraph(tenant.name, styles["Title"]), Paragraph(f"PARTS RECEIPT {snapshot['sale_number']}", styles["Heading2"]), Paragraph(str(snapshot.get("completed_at") or ""), styles["Normal"]), Spacer(1, 12)]
    buyer = snapshot.get("buyer") or {}
    if buyer.get("name") or buyer.get("email"):
        story.extend([Paragraph(f"Buyer: {buyer.get('name') or 'Walk-in'} {buyer.get('email') or ''}", styles["Normal"]), Spacer(1, 8)])
    data = [["Part", "Qty", "Unit", "Tax", "Total"]]
    for line in snapshot.get("lines") or []:
        data.append([line["name"], str(line["quantity"]), f"${line['unit_price']}", f"${line['tax']}", f"${line['total']}"])
    table = Table(data, colWidths=[3.25 * inch, .5 * inch, .9 * inch, .75 * inch, .9 * inch])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#CBD5E1")), ("ALIGN", (1, 1), (-1, -1), "RIGHT"), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("PADDING", (0, 0), (-1, -1), 6)]))
    story.extend([table, Spacer(1, 12)])
    for label, key in (("Subtotal", "subtotal"), ("Tax", "tax"), ("Total", "total")):
        story.append(Paragraph(f"<b>{label}:</b> ${snapshot.get(key, '0.00')}", styles["Normal"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Tender: {snapshot.get('tender', '').replace('_', ' ').title()}", styles["Normal"]))
    if returns:
        refunded = sum((row.refund_amount for row in returns), 0)
        story.append(Paragraph(f"Completed returns/refunds: ${refunded:.2f}", styles["Normal"]))
    doc.build(story)
    return buffer.getvalue()
