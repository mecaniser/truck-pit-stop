"""Actual SQLite regressions for selected-shop source and projection reads."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.api.v1.endpoints.invoices import list_invoices, _list_invoices_legacy
from app.api.v1.endpoints.repair_orders import (
    _ledger_filters, list_repair_orders, repair_order_status_counts,
)
from app.db.models.customer import Customer
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_read_model import RepairOrderReadModel
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole
from app.db.models.vehicle import Vehicle
from app.schemas.repair_order import RepairOrderResponse


async def seed(db, *, projected=False):
    tenants=[Tenant(id=uuid4(),name=f"Shop {n}",slug=f"shop-{uuid4().hex}") for n in range(2)]
    # Shared legacy customer identity across shops must not widen selected shop.
    customer=Customer(id=uuid4(),tenant_id=tenants[0].id,first_name="Shared",last_name="Customer",email=f"{uuid4().hex}@example.com")
    db.add_all([*tenants,customer])
    vehicles=[Vehicle(id=uuid4(),tenant_id=t.id,customer_id=customer.id,make="Volvo",model="VNL") for t in tenants]
    db.add_all(vehicles)
    orders=[]
    invoices=[]
    for n,total in enumerate(["11.00","99.00","77.00"]):
        shop=0 if n==0 else 1
        order=RepairOrder(id=uuid4(),tenant_id=tenants[shop].id,customer_id=customer.id,vehicle_id=vehicles[shop].id,order_number=f"RO-{uuid4().hex}",status=RepairOrderStatus.PAID,total_parts_cost=Decimal(total),total_labor_cost=0,total_cost=Decimal(total))
        # Third invoice intentionally corrupts invoice/order tenant linkage.
        inv=Invoice(id=uuid4(),tenant_id=tenants[0 if n==2 else shop].id,repair_order_id=order.id,invoice_number=f"INV-{uuid4().hex}",status=InvoiceStatus.PAID,subtotal=Decimal(total),tax_amount=0,total_amount=Decimal(total))
        orders.append(order)
        invoices.append(inv)
    db.add_all([*orders,*invoices])
    await db.flush()
    now=datetime.now(timezone.utc)
    own_payment=Payment(id=uuid4(),tenant_id=tenants[0].id,invoice_id=invoices[0].id,payment_number=f"P-{uuid4().hex}",amount=11,method=PaymentMethod.CASH,status=PaymentStatus.COMPLETED,created_at=now-timedelta(days=1),updated_at=now)
    foreign_payment=Payment(id=uuid4(),tenant_id=tenants[1].id,invoice_id=invoices[0].id,payment_number=f"P-{uuid4().hex}",amount=999,method=PaymentMethod.CHECK,status=PaymentStatus.COMPLETED,created_at=now,updated_at=now)
    db.add_all([own_payment,foreign_payment])
    if projected:
        for order in orders:
            db.add(RepairOrderReadModel(repair_order_id=order.id,tenant_id=order.tenant_id,customer_id=customer.id,vehicle_id=order.vehicle_id,status=order.status.value,is_internal=False,is_deleted=False,created_at=order.created_at,search_document=order.order_number,search_compact=order.order_number,payload=RepairOrderResponse.model_validate(order).model_dump(mode="json")))
    await db.commit()
    actor=SimpleNamespace(id=uuid4(),tenant_id=tenants[0].id,customer_id=customer.id,role=UserRole.CUSTOMER)
    return actor,orders,invoices,own_payment


def kwargs(actor,db):
    return dict(status_filter=None,repair_order_id=None,skip=0,limit=100,paginated=True,db=db,current_user=actor)


@pytest.mark.asyncio
async def test_invoice_projection_gap_fallback_keeps_selected_shop(db_session):
    actor,orders,invoices,payment=await seed(db_session)
    # No InvoiceReadModel rows: public list must use its source fallback.
    result=await list_invoices(**kwargs(actor,db_session))
    payload=json.loads(result.body)
    assert payload["total"]==1
    assert [row["id"] for row in payload["items"]]==[str(invoices[0].id)]
    assert payload["items"][0]["payment"]["id"]==str(payment.id)
    assert Decimal(str(payload["items"][0]["payment"]["amount"]))==Decimal("11.00")


@pytest.mark.asyncio
async def test_legacy_staff_query_and_count_reject_cross_tenant_invoice_order_join(db_session):
    actor,orders,invoices,payment=await seed(db_session)
    actor.role=UserRole.GARAGE_OWNER
    result=await _list_invoices_legacy(**kwargs(actor,db_session))
    payload=json.loads(result.body)
    assert payload["total"]==1 and len(payload["items"])==1
    assert payload["items"][0]["id"]==str(invoices[0].id)
    assert payload["items"][0]["payment"]["id"]==str(payment.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("projected",[False,True])
async def test_repair_order_page_and_status_summary_select_one_shop(db_session,projected):
    actor,orders,invoices,_=await seed(db_session,projected=projected)
    args=dict(customer_id=None,vehicle_id=None,status=None,search=None,deleted=False,overdue=False,skip=0,limit=100,paginated=True,db=db_session,current_user=actor)
    result=await list_repair_orders(**args)
    payload=json.loads(result.body)
    assert payload["total"]==1 and [row["id"] for row in payload["items"]]==[str(orders[0].id)]
    summary=await repair_order_status_counts(customer_id=None,vehicle_id=None,search=None,deleted=False,overdue=False,db=db_session,current_user=actor)
    assert summary=={"paid":1,"all":1}
    source,projection=_ledger_filters(actor)
    count,value=(await db_session.execute(select(func.count(RepairOrder.id),func.sum(RepairOrder.total_cost)).where(*source))).one()
    assert count==1 and value==Decimal("11.00")
    if projected:
        count=(await db_session.execute(select(func.count(RepairOrderReadModel.repair_order_id)).where(*projection))).scalar()
        assert count==1


@pytest.mark.asyncio
@pytest.mark.parametrize("missing",["tenant_id","customer_id"])
async def test_customer_missing_selected_identity_fails_closed(db_session,missing):
    actor,_,_,_=await seed(db_session,projected=True)
    setattr(actor,missing,None)
    result=await _list_invoices_legacy(**kwargs(actor,db_session))
    assert json.loads(result.body)["total"]==0
    source,projection=_ledger_filters(actor)
    assert (await db_session.execute(select(func.count(RepairOrder.id)).where(*source))).scalar()==0
    assert (await db_session.execute(select(func.count(RepairOrderReadModel.repair_order_id)).where(*projection))).scalar()==0
