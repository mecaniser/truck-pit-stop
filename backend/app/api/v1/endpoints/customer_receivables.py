"""Read-only DB-135 customer account and unsent statement preview."""
from __future__ import annotations

from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import text

from app.core.dependencies import CurrentUser, get_current_active_user, user_has_permission
from app.db.models.user import UserRole
from app.db.session import AsyncSessionLocal
from app.services.customer_receivables import account_snapshot, decode_cursor, encode_cursor, row_sort_key


router = APIRouter()
PDF_ACTIVITY_CAP = 200
PDF_BYTES_CAP = 2_000_000


def _authorize(user: CurrentUser) -> UUID:
    if user.role not in {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN} or not user_has_permission(user, "payments"):
        raise HTTPException(status_code=403, detail="Customer account access denied")
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Customer account access denied")
    return user.tenant_id


async def _snapshot(tenant_id: UUID, customer_id: UUID) -> dict:
    # Auth uses its own dependency session. This dedicated session starts the
    # financial read at the exact snapshot boundary and always rolls it back.
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        try:
            return await account_snapshot(db, tenant_id=tenant_id, customer_id=customer_id)
        finally:
            await db.rollback()


@router.get("/{customer_id}/account")
async def read_customer_account(
    customer_id: UUID,
    response: Response,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None, max_length=512),
    source_filter: str = Query("all", max_length=32),
    user: CurrentUser = Depends(get_current_active_user),
):
    tenant_id = _authorize(user)
    if source_filter not in {"all", "native", "ets_history", "review_required"}:
        raise HTTPException(status_code=422, detail="Invalid account source filter")
    after = decode_cursor(cursor, tenant_id, customer_id, source_filter)
    snapshot = await _snapshot(tenant_id, customer_id)
    rows = snapshot.pop("transactions")
    if source_filter != "all":
        rows = [row for row in rows if row["source_owner"] == source_filter]
    if after is not None:
        rows = [row for row in rows if row_sort_key(row) < after]
    page = rows[:limit]
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    snapshot["transactions"] = page
    snapshot["next_cursor"] = encode_cursor(tenant_id, customer_id, source_filter, page[-1]) if len(rows) > limit and page else None
    return snapshot


def render_statement_pdf(snapshot: dict) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, pageCompression=1)
    page_width, page_height = letter
    y = page_height - 52

    def line(label: str, *, size: int = 10) -> None:
        nonlocal y
        if y < 55:
            pdf.showPage()
            y = page_height - 52
        pdf.setFont("Helvetica", size)
        # drawString treats text as text, never as PDF markup or HTML.
        pdf.drawString(48, y, " ".join(str(label).split())[:105])
        y -= 16 if size <= 10 else 22

    line("Customer account statement — preview only", size=15)
    line(snapshot["customer"]["name"])
    line(f"Generated {snapshot['generated_at']} · As of {snapshot['as_of_date']} (shop local)")
    line("No statement was sent or issued. Current snapshot; no historical opening balance.")
    y -= 10
    native = snapshot["native"]
    if native["collectible_complete"]:
        line(f"DieselBridge native collectible: ${native['collectible']}", size=12)
    else:
        line("Native balance incomplete — do not use this preview to collect", size=12)
        line(f"Verified native subtotal only: ${native['collectible']}")
        line(f"{native['unverified_invoice_count']} invoice(s) excluded from balance and aging")
    line("Aging below includes verified native principal only.")
    for label, key in (("Current", "current"), ("1–30 overdue", "days_1_30"),
                       ("31–60 overdue", "days_31_60"), ("61–90 overdue", "days_61_90"),
                       ("90+ overdue", "days_90_plus"), ("Undated due", "undated_due"),
                       ("Unapplied credit, separate", "unapplied_credit")):
        line(f"{label}: ${native[key]}")
    line(f"Review required: {native['review_required_count']} item(s)")
    y -= 10
    line("ETS historical — not a DieselBridge collection balance", size=12)
    line("ETS observed open balance: unavailable; imported activity does not establish debt.")
    line(f"ETS review required: {snapshot['ets_history']['review_required_count']}")
    y -= 10
    all_rows = snapshot["transactions"]
    omitted = max(0, len(all_rows) - PDF_ACTIVITY_CAP)
    line(f"Activity ({min(len(all_rows), PDF_ACTIVITY_CAP)} shown)", size=12)
    for row in all_rows[:PDF_ACTIVITY_CAP]:
        when = row["occurred_at"] or row["source_date"] or "date unavailable"
        amount = f"${row['amount']}" if row["amount"] is not None else "amount held"
        remaining = f" · remaining ${row['remaining_principal']}" if row["remaining_principal"] is not None else ""
        invoice_ref = row.get("invoice_number") or row.get("invoice_id")
        action = f" ({row['credit_action']})" if row.get("credit_action") else ""
        line(f"{when[:10]} · {row['source_owner']} {row['kind']}{action}")
        line(f"Entry {row['id']} · invoice {invoice_ref or 'unlinked'}")
        line(f"Amount {amount}{remaining}")
    if omitted:
        line(f"{omitted} activity rows omitted. Displayed rows do not reconcile to full-account totals.")
    pdf.save()
    result = buffer.getvalue()
    if len(result) > PDF_BYTES_CAP:
        raise HTTPException(status_code=413, detail="Statement preview exceeds size limit")
    return result


@router.get("/{customer_id}/account/statement.pdf")
async def download_customer_statement(customer_id: UUID, user: CurrentUser = Depends(get_current_active_user)):
    tenant_id = _authorize(user)
    snapshot = await _snapshot(tenant_id, customer_id)
    content = render_statement_pdf(snapshot)
    return Response(content, media_type="application/pdf", headers={
        "Cache-Control": "private, no-store",
        "Content-Disposition": f'attachment; filename="customer-account-{customer_id}.pdf"',
        "X-Content-Type-Options": "nosniff",
    })
