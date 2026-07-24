from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.api.v1.endpoints import fleet
from app.db.models.fleet_board_read_model import FleetBoardReadModel


class _EmptyScalarResult:
    def scalars(self):
        return self

    def all(self):
        return []


class _StatementRecordingSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _EmptyScalarResult()


@pytest.mark.asyncio
async def test_projected_id_lookup_is_valid_postgresql_distinct_sql():
    """The ID-only fallback probe must not order by unselected vehicle fields."""
    db = _StatementRecordingSession()

    await fleet._fleet_board_vehicle_ids(db, uuid4())

    sql = str(db.statement.compile(dialect=postgresql.dialect()))
    assert "SELECT DISTINCT vehicles.id" in sql
    assert "ORDER BY" not in sql


@pytest.mark.asyncio
async def test_board_reads_backfilled_projection_without_live_repair_order_scan(db_session):
    """A projection row is sufficient to render a fleet card after backfill."""
    from test_fleet_board import _seed

    tenant, _fleet_customer, user = await _seed(db_session)
    vehicle_id = uuid4()
    db_session.add(FleetBoardReadModel(
        vehicle_id=vehicle_id,
        tenant_id=tenant.id,
        vehicle_data={
            "unit_number": "P-1", "year": 2022, "make": "Volvo", "model": "VNL",
            "brand_short": "VO", "body_type": None, "vin": None, "plate": None,
            "driver_name": None, "driver_phone": "+17045551234", "mileage": 100_000,
            "pm_interval_miles": 25_000,
            "next_pm_miles": 130_000, "pm_remaining": 30_000, "pm_interval_days": 70,
            "pm_due_date": None, "pm_days_remaining": None, "location_label": None,
            "location_city": None, "lat": None, "lng": None, "speed_mph": 0,
            "heading": None, "status_override": None, "active_warning_lights": None,
        },
        urgent_work_order=None,
        pm_work_order=None,
        open_work_order_count=0,
        open_incident_count=0,
    ))
    await db_session.commit()

    board = await fleet.fleet_board(db=db_session, current_user=user)

    assert len(board.trucks) == 1
    assert board.trucks[0].id == vehicle_id
    assert board.trucks[0].status == "active"
    assert board.trucks[0].driver_phone == "+17045551234"
