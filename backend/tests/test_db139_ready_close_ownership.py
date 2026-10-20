"""Synthetic SQL projection tests; no providers or production writes."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.api.v1.endpoints import dashboard
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.vehicle import Vehicle


@pytest.mark.asyncio
async def test_ready_close_ownership_all_three_sql_paths_and_history(db_session):
    tenant_id, other_tenant_id, customer_id, vehicle_id = (uuid4() for _ in range(4))
    tenant = Tenant(id=tenant_id, name="Synthetic native shop", slug=f"native-{uuid4().hex[:8]}", timezone="UTC")
    other_tenant = Tenant(id=other_tenant_id, name="Synthetic other shop", slug=f"other-{uuid4().hex[:8]}", timezone="UTC")
    customer = Customer(id=customer_id, tenant_id=tenant_id, first_name="Synthetic", last_name="Customer",
                        email=f"ownership-{uuid4().hex[:8]}@example.test")
    vehicle = Vehicle(id=vehicle_id, tenant_id=tenant_id, customer_id=customer_id, make="Volvo", model="VNR")
    actor = User(id=uuid4(), tenant_id=tenant_id, first_name="Synthetic", last_name="Owner",
                 email=f"ownership-{uuid4().hex[:8]}@example.test", hashed_password="unused",
                 role=UserRole.GARAGE_OWNER, is_active=True)
    db_session.add_all([tenant, other_tenant, customer, vehicle, actor])
    await db_session.flush()
    now = datetime.now(timezone.utc)
    expected = set()
    excluded = set()
    all_orders = []

    def order(label, *, status=RepairOrderStatus.COMPLETED, source=None, amount="100.00", native=False):
        row = RepairOrder(id=uuid4(), tenant_id=tenant_id, customer_id=customer_id, vehicle_id=vehicle_id,
                          order_number=label, status=status, source=source, total_cost=Decimal(amount),
                          updated_at=now + timedelta(seconds=len(all_orders)))
        db_session.add(row)
        all_orders.append(row)
        (expected if native else excluded).add(str(row.id))
        return row

    def invoice(parent, *, source=None, policy="standard", status=InvoiceStatus.SENT,
                deleted=False, pending=False, foreign=False):
        row = Invoice(id=uuid4(), tenant_id=other_tenant_id if foreign else tenant_id,
                      repair_order_id=parent.id, invoice_number=f"SYN-INV-{uuid4().hex[:12]}",
                      status=status, source=source, accounting_policy=policy,
                      subtotal=Decimal("100.00"), total_amount=Decimal("100.00"),
                      zelle_pending_submitted_at=now if pending else None,
                      deleted_at=now if deleted else None)
        db_session.add(row)
        return row

    order("NATIVE-COMPLETED", native=True)
    invoice(order("NATIVE-INVOICED", status=RepairOrderStatus.INVOICED, native=True))
    order("NATIVE-ZERO", amount="0.00", native=True)
    foreign_link = order("NATIVE-FOREIGN-INVOICE", native=True)
    invoice(foreign_link, source="easy_truck_shop_import", foreign=True)
    zelle = order("NATIVE-PENDING-ZELLE", status=RepairOrderStatus.INVOICED)
    invoice(zelle, pending=True)
    for status in (RepairOrderStatus.COMPLETED, RepairOrderStatus.INVOICED):
        for amount in ("0.00", "199.00"):
            order(f"ETS-MISSING-{status.value}-{amount}", status=status, amount=amount,
                  source="easy_truck_shop_import")
    for payment_state in InvoiceStatus:
        imported = order(f"ETS-INVOICE-{payment_state.value}", status=RepairOrderStatus.INVOICED,
                         source="easy_truck_shop_import")
        invoice(imported, status=payment_state, pending=True)
    for source, policy in (("easy_truck_shop_import", "standard"), (None, "historical_export_hold")):
        for deleted in (False, True):
            linked = order(f"LINKED-{policy}-{deleted}", status=RepairOrderStatus.INVOICED)
            invoice(linked, source=source, policy=policy, status=InvoiceStatus.CANCELLED, deleted=deleted)
    # More historical candidates than the cap cannot consume native page slots
    # or create a false has_more flag; ownership must be applied inside SQL.
    for index in range(dashboard.ACTION_QUEUE_LANE_LIMIT + 2):
        order(f"ETS-CAP-{index:03d}", source="easy_truck_shop_import", amount="300.00")
    await db_session.flush()
    # Expire/evict source objects so success proves the action queue's load_only
    # includes source; otherwise async serialization raises MissingGreenlet.
    db_session.expunge_all()
    queue = await dashboard.get_dashboard_action_queue(db=db_session, current_user=actor)
    assert {row.id for row in queue.orders_ready_to_close} == expected
    assert queue.orders_ready_to_close_has_more is False
    assert all(row.source is None for row in queue.orders_ready_to_close)
    assert str(zelle.id) in {row.id for row in queue.orders_needing_action}
    summary = await dashboard.get_dashboard_daily_workset_value_summary(
        lane="ready_to_close", search=None, db=db_session, current_user=actor)
    assert summary.order_count == len(expected)
    assert summary.order_value == Decimal("300.00")
    stats = await dashboard.get_dashboard_stats(db=db_session, current_user=actor)
    assert {row.id for row in stats.orders_ready_to_close} == expected
    # Ownership only removes the billing queue membership, never history.
    assert len(stats.recent_orders) == 10
    assert all(row.source == "easy_truck_shop_import" for row in stats.recent_orders)
    assert stats.total_repair_orders == len(all_orders)
    assert not db_session.new and not db_session.dirty and not db_session.deleted
    persisted = (await db_session.execute(select(RepairOrder.id, RepairOrder.status, RepairOrder.source)
                    .where(RepairOrder.tenant_id == tenant_id))).all()
    assert len(persisted) == len(all_orders)
    assert sum(source == "easy_truck_shop_import" for _, _, source in persisted) > dashboard.ACTION_QUEUE_LANE_LIMIT


@pytest.mark.asyncio
async def test_native_ready_queue_pagination_survives_import_exclusion(db_session):
    tenant_id, customer_id, vehicle_id = uuid4(), uuid4(), uuid4()
    db_session.add_all([
        Tenant(id=tenant_id, name="Synthetic pagination", slug=f"page-{uuid4().hex[:8]}", timezone="UTC"),
        Customer(id=customer_id, tenant_id=tenant_id, first_name="Synthetic", last_name="Customer",
                 email=f"page-{uuid4().hex[:8]}@example.test"),
        Vehicle(id=vehicle_id, tenant_id=tenant_id, customer_id=customer_id, make="Volvo", model="VNR"),
    ])
    await db_session.flush()
    for index in range(dashboard.ACTION_QUEUE_LANE_LIMIT + 1):
        db_session.add(RepairOrder(id=uuid4(), tenant_id=tenant_id, customer_id=customer_id,
            vehicle_id=vehicle_id, order_number=f"NATIVE-PAGE-{index:03d}",
            status=RepairOrderStatus.COMPLETED, total_cost=Decimal("1.00")))
    await db_session.flush()
    queue = await dashboard._load_dashboard_action_queue(db_session, tenant_id, None)
    assert len(queue.orders_ready_to_close) == dashboard.ACTION_QUEUE_LANE_LIMIT
    assert queue.orders_ready_to_close_has_more is True
    assert all(row.order_number.startswith("NATIVE-PAGE-") for row in queue.orders_ready_to_close)
