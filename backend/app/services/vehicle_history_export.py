"""Staff-only, nonfinancial CSV of the physical truck's service history."""
import csv
import io
import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select

from app.db.models.external_service import ExternalServiceRecord as Outside
from app.db.models.labor import Labor
from app.db.models.repair_order import RepairOrder as Order, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.db.models.vehicle import Vehicle

STAFF_ROLES = frozenset({UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST})
IMPORT_SOURCE = "easy_truck_shop_import"
MAX_RECORDS = 1000
MAX_OPERATIONS = 10000
MAX_CSV_BYTES = 2 * 1024 * 1024
HEADERS = (
    "Vehicle ID", "Unit", "VIN", "Year", "Make", "Model", "Record ID", "Source",
    "Original vehicle ID", "History date", "Date basis", "Service date", "Provider",
    "Reference", "Work description", "Operations", "Odometer (mi)", "Odometer basis",
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def fail(status, code, message):
    raise HTTPException(status, {"code": code, "message": message})


def too_large():
    fail(413, "history_export_too_large", "This export is too large. Choose a narrower date range and try again.")


def safe_cell(value):
    if value is None:
        return ""
    text = _CONTROL.sub("", str(value))
    # CSV quoting alone does not prevent Excel/Sheets from executing formulas.
    if text.lstrip().startswith(("=", "+", "-", "@")):
        text = "'" + text
    return text


def local_date(value, timezone):
    # SQLite test datetimes are naive; stored application timestamps are UTC.
    return value.replace(tzinfo=value.tzinfo or UTC).astimezone(timezone).date()


def timestamp_range(column, start, end, timezone):
    conditions = []
    if start:
        conditions.append(column >= datetime.combine(start, time.min, timezone).astimezone(UTC))
    if end and end < date.max:
        conditions.append(column < datetime.combine(end + timedelta(days=1), time.min, timezone).astimezone(UTC))
    return and_(*conditions) if conditions else True


def order_date_range(start, end, timezone):
    imported = Order.source == IMPORT_SOURCE
    native = or_(Order.source.is_(None), Order.source != IMPORT_SOURCE)
    return or_(
        and_(Order.work_completed_at.is_not(None), imported, timestamp_range(Order.work_completed_at, start, end, UTC)),
        and_(Order.work_completed_at.is_not(None), native, timestamp_range(Order.work_completed_at, start, end, timezone)),
        and_(Order.work_completed_at.is_(None), timestamp_range(Order.created_at, start, end, timezone)),
    )


async def bounded_rows(db, statement, raw_characters, maximum_rows):
    """Bound even rows changed after the metadata preflight, without buffering them."""
    result = await db.stream(statement.execution_options(yield_per=1))
    rows = []
    try:
        async for row in result:
            raw_characters[0] += sum(len(value) for value in row if isinstance(value, str))
            if raw_characters[0] > MAX_CSV_BYTES or len(rows) >= maximum_rows:
                too_large()
            rows.append(row)
    finally:
        await result.close()
    return rows


def bounded_text(column):
    # A cap+1 sentinel plus the cumulative guard rejects this row. It can never
    # turn into a successful truncated export, including concurrent text edits.
    return func.substr(column, 1, MAX_CSV_BYTES + 1).label(column.key)


def text_length(*columns):
    return sum(func.coalesce(func.length(column), 0) for column in columns)


async def active_vehicle(db, vehicle_id, tenant_id):
    vehicle = (await db.execute(select(
        Vehicle.id, Vehicle.unit_number, Vehicle.vin, Vehicle.year, Vehicle.make, Vehicle.model,
    ).where(Vehicle.id == vehicle_id, Vehicle.tenant_id == tenant_id, Vehicle.deleted_at.is_(None)))).one_or_none()
    if vehicle is None:
        fail(404, "vehicle_not_found", "Vehicle not found")
    return vehicle


async def export_csv(db, vehicle_id, actor, *, date_from=None, date_to=None):
    if actor.role not in STAFF_ROLES:
        fail(403, "access_denied", "Access denied")
    if not actor.tenant_id:
        fail(400, "tenant_required", "User must be associated with a tenant")
    if date_from and date_to and date_from > date_to:
        fail(422, "invalid_export_filter", "History from must be on or before History to.")
    vehicle = await active_vehicle(db, vehicle_id, actor.tenant_id)
    tenant = (await db.execute(select(Tenant.name, Tenant.timezone).where(Tenant.id == actor.tenant_id))).one()
    try:
        timezone = ZoneInfo(tenant.timezone or "America/New_York")
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("America/New_York")

    order_conditions = [
        Order.tenant_id == actor.tenant_id, Order.vehicle_id == vehicle_id,
        Order.deleted_at.is_(None), Order.status.in_((RepairOrderStatus.COMPLETED, RepairOrderStatus.INVOICED, RepairOrderStatus.PAID)),
    ]
    outside_conditions = [Outside.tenant_id == actor.tenant_id, Outside.vehicle_id == vehicle_id, Outside.deleted_at.is_(None), Outside.voided_at.is_(None)]
    if date_from or date_to:
        order_conditions.append(order_date_range(date_from, date_to, timezone))
        if date_from:
            outside_conditions.append(Outside.service_date >= date_from)
        if date_to:
            outside_conditions.append(Outside.service_date <= date_to)

    # Determine bounded record identity before fetching any work description.
    order_ids = (await db.scalars(select(Order.id).where(*order_conditions).order_by(Order.id).limit(MAX_RECORDS + 1))).all()
    outside_ids = (await db.scalars(select(Outside.id).where(*outside_conditions).order_by(Outside.id).limit(MAX_RECORDS + 1))).all()
    if len(order_ids) + len(outside_ids) > MAX_RECORDS:
        too_large()
    if not order_ids and not outside_ids:
        fail(404, "history_empty", "No completed shop work or active outside-shop history matches this date range.")
    order_conditions.append(Order.id.in_(order_ids))
    outside_conditions.append(Outside.id.in_(outside_ids))
    labor_conditions = [Labor.tenant_id == actor.tenant_id, Labor.repair_order_id.in_(order_ids), Labor.deleted_at.is_(None)]
    # Text columns have no legacy length constraint. Reject oversized raw data
    # in SQL before it can fill a worker; character length is a lower bound on
    # UTF-8 bytes. The final encoder enforces the exact2 MiB output cap.
    raw_size = 0
    if order_ids:
        labor_ids = (await db.scalars(select(Labor.id).where(*labor_conditions).order_by(Labor.id).limit(MAX_OPERATIONS + 1))).all()
        if len(labor_ids) > MAX_OPERATIONS:
            too_large()
        labor_conditions.append(Labor.id.in_(labor_ids))
        raw_size += await db.scalar(select(func.coalesce(func.sum(text_length(Order.description, Order.order_number)), 0)).where(*order_conditions))
        raw_size += await db.scalar(select(func.coalesce(func.sum(text_length(Labor.description)), 0)).where(*labor_conditions))
    if outside_ids:
        raw_size += await db.scalar(select(func.coalesce(func.sum(text_length(Outside.description, Outside.provider_name, Outside.reference)), 0)).where(*outside_conditions))
    if raw_size > MAX_CSV_BYTES:
        too_large()

    # Project only export fields. Notes, prices, actors and financial relations
    # are never fetched or passed through a generic response serializer.
    raw_characters = [0]
    orders = await bounded_rows(db, select(
        Order.id, Order.source, Order.order_number, bounded_text(Order.description),
        Order.work_completed_at, Order.created_at, Order.mileage_in,
        Order.mileage_out, Order.mileage_in_carried,
    ).where(*order_conditions).order_by(Order.id).limit(MAX_RECORDS + 1), raw_characters, MAX_RECORDS)
    outside = await bounded_rows(db, select(
        Outside.id, Outside.original_vehicle_id, Outside.service_date,
        Outside.provider_name, Outside.reference, bounded_text(Outside.description), Outside.odometer,
    ).where(*outside_conditions).order_by(Outside.id).limit(MAX_RECORDS + 1), raw_characters, MAX_RECORDS)
    if not orders and not outside:
        fail(404, "history_empty", "No completed shop work or active outside-shop history matches this date range.")
    operations = {}
    if orders:
        lines = await bounded_rows(db, select(Labor.repair_order_id, bounded_text(Labor.description)).where(
            *labor_conditions, Labor.repair_order_id.in_([row.id for row in orders]),
        ).order_by(Labor.created_at, Labor.id).limit(MAX_OPERATIONS + 1), raw_characters, MAX_OPERATIONS)
        for line in lines:
            operations.setdefault(line.repair_order_id, []).append(line.description)

    rows = []
    for order in orders:
        imported = order.source == IMPORT_SOURCE
        service_date = local_date(order.work_completed_at, UTC if imported else timezone) if order.work_completed_at else None
        history_date = service_date or local_date(order.created_at, timezone)
        basis = ("Imported completion date" if imported else "Work completed") if service_date else "Record created"
        mileage = order.mileage_out if order.mileage_out is not None else order.mileage_in
        mileage_basis = ""
        if mileage is not None:
            mileage_basis = "Imported reading" if imported else ("Mileage out" if order.mileage_out is not None else ("Carried-forward mileage in" if order.mileage_in_carried else "Mileage in"))
        rows.append([
            str(order.id), "Imported ETS history" if imported else "Shop work", "",
            history_date.isoformat(), basis, service_date.isoformat() if service_date else "",
            "Easy Truck Shop import — provider not recorded" if imported else tenant.name,
            order.order_number, order.description, "\n".join(operations.get(order.id, [])), mileage, mileage_basis,
        ])
    for record in outside:
        rows.append([
            str(record.id), "Outside-shop history", str(record.original_vehicle_id),
            record.service_date.isoformat(), "Reported service date", record.service_date.isoformat(),
            record.provider_name, record.reference, record.description, "", record.odometer,
            "Reported outside reading" if record.odometer is not None else "",
        ])
    rows.sort(key=lambda row: (row[3], row[1], row[0]), reverse=True)
    identity = [str(vehicle.id), vehicle.unit_number, vehicle.vin, vehicle.year, vehicle.make, vehicle.model]
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(HEADERS)
    content = bytearray(b"\xef\xbb\xbf")
    content.extend(buffer.getvalue().encode("utf-8"))
    for row in rows:
        buffer.seek(0)
        buffer.truncate()
        writer.writerow([safe_cell(value) for value in identity + row])
        content.extend(buffer.getvalue().encode("utf-8"))
        if len(content) > MAX_CSV_BYTES:
            too_large()
    # No locking/writes: if a known concurrent merge/archive has completed,
    # reject the old vehicle route rather than return a misleading artifact.
    await active_vehicle(db, vehicle_id, actor.tenant_id)
    return bytes(content), len(rows)
