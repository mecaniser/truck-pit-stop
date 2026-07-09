"""Invoice PDF generation using ReportLab."""
from __future__ import annotations

import urllib.request
from decimal import Decimal
from io import BytesIO
from typing import Optional

from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.core.vehicle_display import vehicle_display_label

# ── Brand colours ──────────────────────────────────────────────────────────────
C_DARK = HexColor("#1F2937")
C_AMBER = HexColor("#D97706")
C_LIGHT = HexColor("#F3F4F6")
C_BORDER = HexColor("#E5E7EB")
C_MID = HexColor("#6B7280")
C_GREEN = HexColor("#16A34A")
C_RED = HexColor("#DC2626")

# ── Paragraph styles ───────────────────────────────────────────────────────────
def _style(name: str, **kw) -> ParagraphStyle:
    defaults = dict(fontName="Helvetica", fontSize=9, leading=13, textColor=C_DARK)
    defaults.update(kw)
    return ParagraphStyle(name, **defaults)


S_LABEL = _style("label", fontSize=7, textColor=C_MID, fontName="Helvetica-Bold", leading=10)
S_BODY = _style("body")
S_BOLD = _style("bold", fontName="Helvetica-Bold")
S_SMALL = _style("small", fontSize=8, textColor=C_MID, leading=11)
S_TITLE = _style("title", fontSize=22, fontName="Helvetica-Bold", textColor=C_DARK, leading=26)
S_INV_NUM = _style("invnum", fontSize=12, fontName="Helvetica-Bold", textColor=C_AMBER, leading=16)
S_SHOP = _style("shop", fontSize=12, fontName="Helvetica-Bold", leading=16)
S_RIGHT = _style("right", alignment=TA_RIGHT)
S_RIGHT_BOLD = _style("rightbold", alignment=TA_RIGHT, fontName="Helvetica-Bold")
S_CENTER = _style("center", alignment=TA_CENTER)
S_CENTER_SMALL = _style("centersmall", alignment=TA_CENTER, fontSize=8, textColor=C_MID, leading=11)


def _p(text: str, style: ParagraphStyle = S_BODY) -> Paragraph:
    return Paragraph(str(text), style)


def _fmt(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def _fetch_logo(url: str) -> Optional[BytesIO]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            return BytesIO(resp.read())
    except Exception:
        return None


def _status_color(status: str):
    s = status.lower()
    if s == "paid":
        return C_GREEN
    if s == "overdue":
        return C_RED
    return C_AMBER


def _status_label(status: str) -> str:
    return {"paid": "PAID", "overdue": "OVERDUE", "cancelled": "CANCELLED"}.get(
        status.lower(), "OUTSTANDING"
    )


# ── Page header / footer drawn on every page ───────────────────────────────────
def _make_page_handler(
    shop_name: str,
    shop_address: Optional[str],
    shop_email: Optional[str],
    shop_phone: Optional[str],
    logo_data: Optional[BytesIO],
    invoice_number: str,
    invoice_date: str,
):
    W, H = letter
    MARGIN = 0.5 * inch

    def handler(canvas, doc):
        canvas.saveState()
        y_top = H - MARGIN

        # ── Left: INVOICE + number ──────────────────────────────────────────
        canvas.setFont("Helvetica-Bold", 22)
        canvas.setFillColor(C_DARK)
        canvas.drawString(MARGIN, y_top - 18, "INVOICE")

        canvas.setFont("Helvetica-Bold", 11)
        canvas.setFillColor(C_AMBER)
        canvas.drawString(MARGIN, y_top - 34, invoice_number)

        # ── Right: logo + shop info ─────────────────────────────────────────
        info_x = W - MARGIN
        text_y = y_top - 10

        logo_w = 1.4 * inch

        if logo_data:
            logo_data.seek(0)
            try:
                img = Image(logo_data, width=logo_w, height=0.55 * inch)
                img.drawOn(canvas, W - MARGIN - logo_w, y_top - 0.6 * inch)
                text_y = y_top - 0.7 * inch - 4
            except Exception:
                pass

        canvas.setFont("Helvetica-Bold", 11)
        canvas.setFillColor(C_DARK)
        canvas.drawRightString(info_x, text_y, shop_name)
        text_y -= 13

        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(C_MID)
        if shop_address:
            canvas.drawRightString(info_x, text_y, shop_address)
            text_y -= 11
        if shop_email:
            canvas.drawRightString(info_x, text_y, shop_email)
            text_y -= 11
        if shop_phone:
            canvas.drawRightString(info_x, text_y, shop_phone)

        # ── Divider line (below the tallest header element) ─────────────────
        div_y = y_top - 120
        canvas.setStrokeColor(C_BORDER)
        canvas.setLineWidth(0.75)
        canvas.line(MARGIN, div_y, W - MARGIN, div_y)

        # ── Footer ──────────────────────────────────────────────────────────
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(C_MID)
        from datetime import datetime
        ts = datetime.now().strftime("%m/%d/%Y %I:%M %p")
        canvas.drawString(MARGIN, MARGIN - 4, ts)
        canvas.drawRightString(
            W - MARGIN, MARGIN - 4, f"Page {doc.page}"
        )
        canvas.setStrokeColor(C_BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, MARGIN + 8, W - MARGIN, MARGIN + 8)

        canvas.restoreState()

    return handler


# ── Public entry point ─────────────────────────────────────────────────────────
def generate_invoice_pdf(
    *,
    # Invoice meta
    invoice_number: str,
    order_number: str,
    invoice_date: str,
    service_completed: Optional[str],
    due_date: Optional[str],
    status: str,
    notes: Optional[str] = None,
    # Bill To
    customer_company: Optional[str],
    customer_name: str,
    customer_email: Optional[str],
    customer_phone: Optional[str],
    # Shop
    shop_name: str,
    shop_address: Optional[str],
    shop_email: Optional[str],
    shop_phone: Optional[str],
    shop_logo_url: Optional[str] = None,
    # Vehicle
    vehicle_year: Optional[str],
    vehicle_make: str,
    vehicle_model: str,
    vehicle_unit: Optional[str] = None,
    vehicle_vin: Optional[str] = None,
    vehicle_odometer: Optional[int] = None,
    # Line items
    labor_items: Optional[list] = None,
    parts_items: Optional[list] = None,
    # Totals
    labor_total: Decimal = Decimal("0"),
    parts_total: Decimal = Decimal("0"),
    shop_supplies_amount: Decimal = Decimal("0"),
    service_fee_amount: Decimal = Decimal("0"),
    subtotal: Decimal = Decimal("0"),
    tax_amount: Decimal = Decimal("0"),
    tax_rate: Optional[float] = None,
    discount_amount: Decimal = Decimal("0"),
    total_amount: Decimal = Decimal("0"),
    # Payment
    invoice_access_url: Optional[str] = None,
    zelle_email: Optional[str] = None,
    zelle_phone: Optional[str] = None,
) -> bytes:
    labor_items = labor_items or []
    parts_items = parts_items or []

    buf = BytesIO()
    W, H = letter
    MARGIN = 0.5 * inch
    CONTENT_W = W - 2 * MARGIN

    # Fetch logo once
    logo_data: Optional[BytesIO] = None
    if shop_logo_url:
        logo_data = _fetch_logo(shop_logo_url)

    page_handler = _make_page_handler(
        shop_name=shop_name,
        shop_address=shop_address,
        shop_email=shop_email,
        shop_phone=shop_phone,
        logo_data=logo_data,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
    )

    # topMargin must clear the canvas header (logo ~0.6in + shop name + 3 text lines ≈ 1.7in total)
    TOP_MARGIN = 1.85 * inch
    BOT_MARGIN = 0.6 * inch
    doc = BaseDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOT_MARGIN,
    )
    frame = Frame(MARGIN, BOT_MARGIN, CONTENT_W, H - TOP_MARGIN - BOT_MARGIN, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=page_handler)])

    story = []

    # ── Bill To / Invoice Info (2-column) ──────────────────────────────────────
    status_col = _status_color(status)
    status_lbl = _status_label(status)

    bill_rows = []
    if customer_company:
        bill_rows.append(_p(customer_company, S_BOLD))
    bill_rows.append(_p(customer_name, S_BODY if customer_company else S_BOLD))
    if customer_email:
        bill_rows.append(_p(customer_email, S_SMALL))
    if customer_phone:
        bill_rows.append(_p(customer_phone, S_SMALL))

    info_rows = [
        [_p("Invoice Date", S_LABEL), _p(invoice_date, S_BOLD)],
    ]
    if service_completed:
        info_rows.append([_p("Service Completed", S_LABEL), _p(service_completed, S_BODY)])
    if due_date:
        info_rows.append([_p("Due Date", S_LABEL), _p(due_date, S_BOLD)])
    info_rows.append([_p("Order #", S_LABEL), _p(order_number, S_BODY)])

    info_tbl = Table(info_rows, colWidths=[0.9 * inch, 1.5 * inch])
    info_tbl.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))

    # Status badge cell
    badge_style = ParagraphStyle(
        "badge",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=white,
        alignment=TA_CENTER,
        leading=14,
    )
    badge_para = _p(status_lbl, badge_style)
    badge_cell = Table([[badge_para]], colWidths=[1.5 * inch])
    badge_cell.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), status_col),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    bill_left = Table(
        [[_p("BILL TO", S_LABEL)]] + [[r] for r in bill_rows],
        colWidths=[CONTENT_W * 0.5],
    )
    bill_left.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))

    right_col = Table([[info_tbl], [badge_cell]], colWidths=[CONTENT_W * 0.5])
    right_col.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    header_grid = Table(
        [[bill_left, right_col]],
        colWidths=[CONTENT_W * 0.5, CONTENT_W * 0.5],
    )
    header_grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(header_grid)
    story.append(Spacer(1, 10))

    # ── Vehicle info ───────────────────────────────────────────────────────────
    vehicle_str = vehicle_display_label(vehicle_year, vehicle_make, vehicle_model, None)
    vehicle_rows = [[_p("VEHICLE", S_LABEL)], [_p(vehicle_str, S_BOLD)]]
    detail_parts = []
    if vehicle_unit:
        detail_parts.append(f"Unit: {vehicle_unit}")
    if vehicle_vin:
        detail_parts.append(f"VIN: {vehicle_vin}")
    if vehicle_odometer:
        detail_parts.append(f"Odometer: {vehicle_odometer:,} Miles")
    if detail_parts:
        vehicle_rows.append([_p("  ·  ".join(detail_parts), S_SMALL)])

    veh_tbl = Table(vehicle_rows, colWidths=[CONTENT_W])
    veh_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(veh_tbl)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width=CONTENT_W, thickness=0.75, color=C_BORDER, spaceAfter=6))

    # ── Line items table ───────────────────────────────────────────────────────
    COL_W = [CONTENT_W * 0.46, CONTENT_W * 0.16, CONTENT_W * 0.19, CONTENT_W * 0.19]

    def section_header(label: str) -> list:
        return [
            Table(
                [[_p(label, _style("sh", fontName="Helvetica-Bold", fontSize=9, textColor=C_DARK))]],
                colWidths=[CONTENT_W],
            ),
            "", "", "",
        ]

    header_row = [
        _p("Description", _style("th", fontName="Helvetica-Bold", fontSize=8, textColor=white)),
        _p("Qty / Hrs", _style("thr", fontName="Helvetica-Bold", fontSize=8, textColor=white, alignment=TA_RIGHT)),
        _p("Rate / Price", _style("thr2", fontName="Helvetica-Bold", fontSize=8, textColor=white, alignment=TA_RIGHT)),
        _p("Total", _style("tht", fontName="Helvetica-Bold", fontSize=8, textColor=white, alignment=TA_RIGHT)),
    ]

    rows = [header_row]
    row_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), C_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ROWBACKGROUND", (0, 0), (-1, 0), C_DARK),
    ]
    ri = 1  # current row index

    def _add_section(label: str, items: list, is_labor: bool):
        nonlocal ri
        if not items:
            return
        rows.append(section_header(label))
        row_styles.append(("BACKGROUND", (0, ri), (-1, ri), C_LIGHT))
        row_styles.append(("SPAN", (0, ri), (-1, ri)))
        row_styles.append(("TOPPADDING", (0, ri), (-1, ri), 5))
        row_styles.append(("BOTTOMPADDING", (0, ri), (-1, ri), 5))
        ri += 1

        for item in items:
            if is_labor:
                hrs = item.get("hours", Decimal("0"))
                rate = item.get("hourly_rate", Decimal("0"))
                total = item.get("total_cost", Decimal("0"))
                qty_str = f"{float(hrs):.1f} hr{'s' if float(hrs) != 1 else ''}"
                rate_str = _fmt(Decimal(str(rate)))
            else:
                qty = item.get("quantity", 1)
                rate = item.get("unit_price", Decimal("0"))
                total = item.get("total_price", Decimal("0"))
                qty_str = str(qty)
                rate_str = _fmt(Decimal(str(rate)))

            name_text = item.get("description") or item.get("name", "")
            savings_val = Decimal(str(item.get("savings", 0))) if not is_labor else Decimal("0")
            if savings_val > 0:
                list_p = item.get("list_price")
                list_str = _fmt(Decimal(str(list_p))) if list_p is not None else ""
                name_text = (
                    f'{name_text}<br/><font size="7" color="#059669">Saved '
                    f'{_fmt(savings_val)}{" (list " + list_str + ")" if list_str else ""}</font>'
                )
            rows.append([
                _p(name_text, S_BODY),
                _p(qty_str, S_RIGHT),
                _p(rate_str, S_RIGHT),
                _p(_fmt(Decimal(str(total))), S_RIGHT_BOLD),
            ])
            row_styles.append(("BOTTOMPADDING", (0, ri), (-1, ri), 4))
            row_styles.append(("TOPPADDING", (0, ri), (-1, ri), 4))
            ri += 1

    _add_section("Labor", labor_items, is_labor=True)
    _add_section("Parts", parts_items, is_labor=False)

    # Fees
    fee_items = []
    if shop_supplies_amount > 0:
        fee_items.append({"name": "Shop Supplies", "quantity": 1, "unit_price": shop_supplies_amount, "total_price": shop_supplies_amount})
    if service_fee_amount > 0:
        fee_items.append({"name": "Processing Fee", "quantity": 1, "unit_price": service_fee_amount, "total_price": service_fee_amount})
    _add_section("Fees", fee_items, is_labor=False)

    # Alternating row background
    for i in range(1, ri):
        if not any(
            s[0] == "BACKGROUND" and s[1] == (0, i)
            for s in row_styles
        ):
            bg = C_LIGHT if i % 2 == 0 else white
            row_styles.append(("ROWBACKGROUND", (0, i), (-1, i), bg))

    row_styles += [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, C_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]

    items_tbl = Table(rows, colWidths=COL_W, repeatRows=1)
    items_tbl.setStyle(TableStyle(row_styles))
    story.append(items_tbl)
    story.append(Spacer(1, 10))

    # ── Totals summary ─────────────────────────────────────────────────────────
    def total_row(label: str, amount: Decimal, bold: bool = False, color=None) -> list:
        sty = _style("tr", alignment=TA_RIGHT, fontName="Helvetica-Bold" if bold else "Helvetica",
                     fontSize=10 if bold else 9, textColor=color or C_DARK, leading=14 if bold else 12)
        return ["", _p(label, sty), _p(_fmt(amount), sty)]

    total_rows = []
    if labor_total:
        total_rows.append(total_row("Labor", labor_total))
    if parts_total:
        total_rows.append(total_row("Parts", parts_total))
    if shop_supplies_amount:
        total_rows.append(total_row("Shop Supplies", shop_supplies_amount))
    if service_fee_amount:
        total_rows.append(total_row("Processing Fee", service_fee_amount))
    total_rows.append(total_row("Subtotal", subtotal))
    # Itemized parts savings (discount off list price). Shown as informational
    # line only — the savings are already baked into the parts unit prices above.
    parts_savings_total = sum(
        (Decimal(str(p.get("savings", 0))) for p in (parts_items or [])),
        Decimal("0"),
    )
    if parts_savings_total > 0:
        total_rows.append(total_row("You saved", -parts_savings_total, color=C_GREEN))
    if discount_amount > 0:
        total_rows.append(total_row(f"Discount", -discount_amount, color=C_GREEN))
    tax_label = f"Tax ({tax_rate:.2f}%)" if tax_rate else "Tax"
    total_rows.append(total_row(tax_label, tax_amount))
    total_rows.append(total_row("TOTAL DUE", total_amount, bold=True, color=white))

    sum_tbl = Table(
        total_rows,
        colWidths=[CONTENT_W * 0.44, CONTENT_W * 0.32, CONTENT_W * 0.24],
    )
    sum_style = [
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEABOVE", (1, len(total_rows) - 1), (-1, len(total_rows) - 1), 1.0, C_DARK),
        ("BACKGROUND", (1, len(total_rows) - 1), (-1, len(total_rows) - 1), C_DARK),
        ("TEXTCOLOR", (1, len(total_rows) - 1), (-1, len(total_rows) - 1), white),
        ("TOPPADDING", (0, len(total_rows) - 1), (-1, len(total_rows) - 1), 6),
        ("BOTTOMPADDING", (0, len(total_rows) - 1), (-1, len(total_rows) - 1), 6),
    ]
    # Discount in green
    for i, row in enumerate(total_rows):
        label_text = row[1].text if hasattr(row[1], "text") else ""
        if "Discount" in str(label_text):
            sum_style.append(("TEXTCOLOR", (1, i), (-1, i), C_GREEN))

    sum_tbl.setStyle(TableStyle(sum_style))
    story.append(KeepTogether([sum_tbl]))
    story.append(Spacer(1, 16))

    # ── Payment instructions ───────────────────────────────────────────────────
    payment_items = []
    if invoice_access_url:
        # Strip query params so the URL is clean and readable in print
        from urllib.parse import urlparse
        _parsed = urlparse(invoice_access_url)
        clean_url = f"{_parsed.scheme}://{_parsed.netloc}{_parsed.path}"
        payment_items.append(_p(
            f'<b>Pay Online:</b> <font color="#D97706">{clean_url}</font>',
            _style("paylink", fontSize=8, textColor=C_DARK, leading=12),
        ))
    if zelle_email or zelle_phone:
        zelle_parts = ["<b>Zelle:</b>"]
        if zelle_email:
            zelle_parts.append(zelle_email)
        if zelle_phone:
            zelle_parts.append(zelle_phone)
        payment_items.append(_p("  ·  ".join(zelle_parts), _style("zelle", fontSize=8, textColor=C_DARK, leading=12)))

    if payment_items:
        pay_block = Table(
            [[item] for item in payment_items],
            colWidths=[CONTENT_W],
        )
        pay_block.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_LIGHT),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("LINEABOVE", (0, 0), (-1, 0), 1, C_AMBER),
        ]))
        story.append(KeepTogether([pay_block]))
        story.append(Spacer(1, 10))

    # ── Notes ──────────────────────────────────────────────────────────────────
    if notes:
        story.append(_p("<b>Notes:</b>", S_BOLD))
        story.append(Spacer(1, 3))
        story.append(_p(notes, S_SMALL))
        story.append(Spacer(1, 10))

    # ── Thank-you ──────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=CONTENT_W, thickness=0.5, color=C_BORDER, spaceBefore=4, spaceAfter=6))
    story.append(_p("Thank you for your business!", S_CENTER_SMALL))

    doc.build(story)
    return buf.getvalue()
