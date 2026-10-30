"""Customer-scoped operational RO history, independent of invoice grants."""
import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.fleet_invoice_exports import _active_key
from app.core.dependencies import get_db
from app.db.models.fleet_invoice_api_key import FleetInvoiceApiKey
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.vehicle import Vehicle

router = APIRouter()
VERSION = 'db094-repair-history-v1'
MAX_REPAIR_HISTORY_ROWS = 1000


def _digest(value: dict) -> str:
    content = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@router.get('/repair-orders')
async def repair_order_history(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    key: FleetInvoiceApiKey = Depends(_active_key),
):
    if request.query_params:
        raise HTTPException(422, detail={'code': 'invalid_repair_history_filters',
                                        'message': 'Repair history requires a complete scoped snapshot.'})
    # One materialized joined query prevents per-row reads from mixing revisions.
    rows = (await db.execute(
        select(
            RepairOrder.id, RepairOrder.order_number, RepairOrder.status,
            RepairOrder.description, RepairOrder.created_at, RepairOrder.work_completed_at,
            Vehicle.id.label('vehicle_id'), Vehicle.vin, Vehicle.unit_number,
        )
        .join(Vehicle, Vehicle.id == RepairOrder.vehicle_id)
        .where(
            RepairOrder.tenant_id == key.tenant_id,
            RepairOrder.customer_id == key.customer_id,
            Vehicle.tenant_id == key.tenant_id,
            RepairOrder.deleted_at.is_(None),
            RepairOrder.is_internal.is_(False),
            RepairOrder.status.in_((RepairOrderStatus.COMPLETED,
                                   RepairOrderStatus.INVOICED, RepairOrderStatus.PAID)),
        )
        .order_by(RepairOrder.id)
        .limit(MAX_REPAIR_HISTORY_ROWS + 1)
    )).all()
    if len(rows) > MAX_REPAIR_HISTORY_ROWS:
        raise HTTPException(409, detail={'code': 'repair_history_snapshot_too_large',
                                        'message': 'Repair history exceeds the complete snapshot limit.'})
    items = []
    for row in rows:
        created = _utc(row.created_at)
        completed = _utc(row.work_completed_at) if row.work_completed_at else None
        item = {
            'repair_order_id': str(row.id), 'order_number': row.order_number,
            'vehicle_id': str(row.vehicle_id), 'vin': row.vin, 'unit_number': row.unit_number,
            'status': row.status.value, 'description': row.description,
            'created_at': created.isoformat(),
            'work_completed_at': completed.isoformat() if completed else None,
            'service_date': (completed or created).date().isoformat(),
            'service_date_source': 'work_completed_at' if completed else 'created_at_fallback',
        }
        item['revision'] = _digest(item)
        items.append(item)
    snapshot = {'version': VERSION, 'shop_id': str(key.tenant_id),
                'customer_id': str(key.customer_id), 'items': items}
    response.headers['Cache-Control'] = 'private, no-store'
    return {**snapshot, 'snapshot_id': _digest(snapshot), 'complete': True, 'count': len(items)}
