"""DB120 export privacy, bounded completeness and truthful history semantics."""
import csv
from datetime import UTC, date, datetime
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from fastapi import HTTPException
import pytest
from sqlalchemy import func, select
from app.db.models.external_service import ExternalServiceEvent, ExternalServiceRecord
from app.db.models.labor import Labor
from app.db.models.repair_order import RepairOrder, RepairOrderStatus as Status
from app.db.models.user import UserRole
from app.db.models.vehicle import Vehicle
from app.services import vehicle_history_export as service
from app.services.vehicle_merge import merge_vehicles
from test_service_checklists import seed


def decoded(content):
    return list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'), newline='')))


async def outside(db, a, **values):
    record = ExternalServiceRecord(**(dict(id=uuid4(), tenant_id=a.tenant.id, vehicle_id=a.vehicle.id, original_vehicle_id=a.vehicle.id, provider_name='Outside shop', service_date=date(2026, 2, 12), description='Replaced fan belt', created_by_user_id=a.owner.id, created_by_name='Staff', updated_by_user_id=a.owner.id, updated_by_name='Staff') | values))
    db.add(record)
    await db.flush()
    return record


async def order(db, a, **values):
    record = RepairOrder(**(dict(id=uuid4(), tenant_id=a.tenant.id, vehicle_id=a.vehicle.id, customer_id=a.customer.id, order_number=f'QA-{uuid4().hex[:12]}', status=Status.COMPLETED, description='Service description', work_completed_at=datetime(2026, 2, 10, 18, tzinfo=UTC)) | values))
    db.add(record)
    await db.flush()
    return record


def labor(a, order_id, **values):
    return Labor(**(dict(id=uuid4(), tenant_id=a.tenant.id, repair_order_id=order_id, description='Operation description', hours=1, hourly_rate=100, total_cost=100) | values))


async def error(awaitable, status, code):
    with pytest.raises(HTTPException) as exc:
        await awaitable
    assert exc.value.status_code == status
    assert exc.value.detail['code'] == code


@pytest.mark.asyncio
async def test_mixed_export_truthful_dates_odometer_privacy_no_writes(db_session):
    a = await seed(db_session)
    a.vehicle.unit_number, a.vehicle.vin = 'UNIT-7', '1HTMMAAL17H123456'
    a.vehicle.notes, a.vehicle.mileage, a.vehicle.next_pm_miles = 'PRIVATE VEHICLE NOTE', 999999, 1000000
    a.customer.email, a.customer.phone = 'private@example.invalid', '555-555-1212'
    a.order.status, a.order.description = Status.COMPLETED, 'Brake service'
    a.order.work_completed_at = datetime(2026, 2, 13, 2, tzinfo=UTC)
    a.order.mileage_in, a.order.mileage_out = 100, 120
    a.order.customer_notes, a.order.shop_notes = 'PRIVATE CUSTOMER NOTE', 'PRIVATE SHOP NOTE'
    a.order.internal_notes, a.order.total_cost = '{"private":"PRIVATE JSON"}', 314159.26
    imported = await order(db_session, a, source=service.IMPORT_SOURCE, work_completed_at=None, created_at=datetime(2026, 2, 10, 2, tzinfo=UTC), mileage_in=60, mileage_out=60)
    external = await outside(db_session, a, odometer=0, reported_cost='987654.32')
    unknown = await outside(db_session, a, service_date=date(2026, 2, 11), odometer=None)
    db_session.add_all([labor(a, a.order.id, description='First operation', created_at=datetime(2026, 1, 1, tzinfo=UTC)), labor(a, a.order.id, description='Second operation', created_at=datetime(2026, 1, 2, tzinfo=UTC)), labor(a, a.order.id, description='DELETED LABOR', deleted_at=datetime.now(UTC))])
    await db_session.commit()
    await db_session.refresh(a.order)
    await db_session.refresh(a.vehicle)
    before = (a.order.updated_at, a.vehicle.updated_at, a.order.total_cost, a.vehicle.mileage, a.vehicle.next_pm_miles)
    content, count = await service.export_csv(db_session, a.vehicle.id, a.owner)
    assert content.startswith(b'\xef\xbb\xbf') and b'\r\n' in content and count == 4
    rows = decoded(content)
    assert list(rows[0]) == list(service.HEADERS)
    assert [r['History date'] for r in rows] == sorted([r['History date'] for r in rows], reverse=True)
    by_id = {r['Record ID']: r for r in rows}
    native = by_id[str(a.order.id)]
    assert native['Source'] == 'Shop work' and native['Provider'] == a.tenant.name
    assert native['History date'] == native['Service date'] == '2026-02-12'
    assert native['Operations'] == 'First operation\nSecond operation'
    assert (native['Odometer (mi)'], native['Odometer basis']) == ('120', 'Mileage out')
    imp = by_id[str(imported.id)]
    assert (imp['History date'], imp['Service date'], imp['Date basis']) == ('2026-02-09', '', 'Record created')
    assert imp['Source'] == 'Imported ETS history' and imp['Odometer basis'] == 'Imported reading'
    ext = by_id[str(external.id)]
    assert ext['Original vehicle ID'] == str(a.vehicle.id) and ext['Odometer (mi)'] == '0' and ext['Date basis'] == 'Reported service date'
    assert by_id[str(unknown.id)]['Odometer (mi)'] == by_id[str(unknown.id)]['Odometer basis'] == ''
    for forbidden in ['PRIVATE', 'private@example.invalid', '555-555-1212', '314159.26', '987654.32', '999999', 'DELETED LABOR', 'total_cost', 'balance', 'amount']:
        assert forbidden not in content.decode('utf-8-sig')
    await db_session.refresh(a.order)
    await db_session.refresh(a.vehicle)
    assert before == (a.order.updated_at, a.vehicle.updated_at, a.order.total_cost, a.vehicle.mileage, a.vehicle.next_pm_miles)
    assert await db_session.scalar(select(func.count(ExternalServiceEvent.id))) == 0


@pytest.mark.asyncio
async def test_all_statuses_deletion_voiding_and_more_than_one_page(db_session):
    a = await seed(db_session)
    for state in Status:
        await order(db_session, a, status=state, description=state.value)
    await order(db_session, a, deleted_at=datetime.now(UTC), description='Deleted order')
    for index in range(28):
        await outside(db_session, a, description=f'Outside {index}')
    await outside(db_session, a, voided_at=datetime.now(UTC), description='Voided outside')
    await outside(db_session, a, deleted_at=datetime.now(UTC), description='Deleted outside')
    content, count = await service.export_csv(db_session, a.vehicle.id, a.owner)
    assert count == 31
    assert {r['Work description'] for r in decoded(content)} == {'completed', 'invoiced', 'paid'} | {f'Outside {index}' for index in range(28)}


@pytest.mark.asyncio
@pytest.mark.parametrize('role', list(UserRole))
async def test_role_allowlist(db_session, role):
    if role not in service.STAFF_ROLES:
        db = AsyncMock()
        await error(service.export_csv(db, uuid4(), SimpleNamespace(role=role, tenant_id=uuid4())), 403, 'access_denied')
        db.execute.assert_not_called()
    else:
        a = await seed(db_session)
        a.owner.role = role
        await outside(db_session, a)
        assert (await service.export_csv(db_session, a.vehicle.id, a.owner))[1] == 1


@pytest.mark.asyncio
async def test_tenant_active_vehicle_and_inconsistent_links(db_session):
    a, b = await seed(db_session), await seed(db_session)
    await outside(db_session, a, description='VISIBLE')
    await order(db_session, a, tenant_id=b.tenant.id, description='FOREIGN ORDER')
    db_session.add(labor(b, a.order.id, description='FOREIGN LABOR'))
    a.order.status = Status.PAID
    await db_session.flush()
    content, count = await service.export_csv(db_session, a.vehicle.id, a.owner)
    assert count == 2 and b'FOREIGN' not in content
    for target in [b.vehicle.id, uuid4()]:
        await error(service.export_csv(db_session, target, a.owner), 404, 'vehicle_not_found')
    a.vehicle.deleted_at = datetime.now(UTC)
    await db_session.flush()
    await error(service.export_csv(db_session, a.vehicle.id, a.owner), 404, 'vehicle_not_found')
    a.owner.tenant_id = None
    await error(service.export_csv(db_session, a.vehicle.id, a.owner), 400, 'tenant_required')


@pytest.mark.asyncio
async def test_inclusive_ranges_dst_imported_midnight_unknown_completion(db_session):
    a = await seed(db_session)
    for label, stamp in [('Before', datetime(2026, 3, 8, 4, 59, tzinfo=UTC)), ('Start', datetime(2026, 3, 8, 5, tzinfo=UTC)), ('End', datetime(2026, 3, 9, 3, 59, tzinfo=UTC)), ('After', datetime(2026, 3, 9, 4, tzinfo=UTC))]:
        await order(db_session, a, description=label, work_completed_at=stamp)
    await order(db_session, a, source=service.IMPORT_SOURCE, description='Imported date', work_completed_at=datetime(2026, 3, 8, tzinfo=UTC))
    await order(db_session, a, source=service.IMPORT_SOURCE, description='Unknown completion', work_completed_at=None, created_at=datetime(2026, 3, 8, 5, tzinfo=UTC))
    await outside(db_session, a, service_date=date(2026, 3, 8), description='Outside')
    content, count = await service.export_csv(db_session, a.vehicle.id, a.owner, date_from=date(2026, 3, 8), date_to=date(2026, 3, 8))
    assert count == 5
    rows = decoded(content)
    assert {r['Work description'] for r in rows} == {'Start', 'End', 'Imported date', 'Unknown completion', 'Outside'}
    assert {r['History date'] for r in rows} == {'2026-03-08'}
    imported = next(r for r in rows if r['Work description'] == 'Imported date')
    assert (imported['Service date'], imported['Date basis']) == ('2026-03-08', 'Imported completion date')
    assert (await service.export_csv(db_session, a.vehicle.id, a.owner, date_to=date(2026, 3, 7)))[1] == 1
    assert (await service.export_csv(db_session, a.vehicle.id, a.owner, date_from=date(2026, 3, 9)))[1] == 1
    await error(service.export_csv(db_session, a.vehicle.id, a.owner, date_from=date(2026, 3, 9), date_to=date(2026, 3, 8)), 422, 'invalid_export_filter')


@pytest.mark.asyncio
async def test_odometer_fallback_and_internal_fleet(db_session):
    a = await seed(db_session)
    a.vehicle.mileage = 900000
    first = await order(db_session, a, mileage_in=0, mileage_out=None, mileage_in_carried=True, is_internal=True)
    second = await order(db_session, a, mileage_in=34, mileage_out=None)
    third = await order(db_session, a, mileage_in=None, mileage_out=None)
    content, _ = await service.export_csv(db_session, a.vehicle.id, a.owner)
    rows = {r['Record ID']: r for r in decoded(content)}
    assert (rows[str(first.id)]['Odometer (mi)'], rows[str(first.id)]['Odometer basis']) == ('0', 'Carried-forward mileage in')
    assert rows[str(second.id)]['Odometer basis'] == 'Mileage in'
    assert rows[str(third.id)]['Odometer (mi)'] == '' and b'900000' not in content


@pytest.mark.asyncio
async def test_record_operation_utf8_byte_caps(db_session, monkeypatch):
    a = await seed(db_session)
    first = await outside(db_session, a)
    await outside(db_session, a)
    monkeypatch.setattr(service, 'MAX_RECORDS', 1)
    await error(service.export_csv(db_session, a.vehicle.id, a.owner), 413, 'history_export_too_large')
    monkeypatch.setattr(service, 'MAX_RECORDS', 1000)
    a.order.status = Status.COMPLETED
    db_session.add_all([labor(a, a.order.id), labor(a, a.order.id)])
    await db_session.flush()
    monkeypatch.setattr(service, 'MAX_OPERATIONS', 1)
    await error(service.export_csv(db_session, a.vehicle.id, a.owner), 413, 'history_export_too_large')
    monkeypatch.setattr(service, 'MAX_OPERATIONS', 10000)
    content, count = await service.export_csv(db_session, a.vehicle.id, a.owner)
    monkeypatch.setattr(service, 'MAX_CSV_BYTES', len(content))
    assert (await service.export_csv(db_session, a.vehicle.id, a.owner))[1] == count
    first.description = '🚚' * 1000
    await db_session.flush()
    await error(service.export_csv(db_session, a.vehicle.id, a.owner), 413, 'history_export_too_large')


@pytest.mark.parametrize('value', ['=HYPERLINK("evil")', '  +1', '\t-2', '\r\n@SUM(1)', '\x00\x01=1', '\x85=2'])
def test_formula_protection(value):
    result = service.safe_cell(value)
    assert result.startswith("'") and '\x00' not in result and '\x01' not in result and '\x85' not in result


@pytest.mark.asyncio
async def test_roundtrip_and_all_untrusted_cells(db_session):
    a = await seed(db_session)
    a.vehicle.unit_number, a.vehicle.make, a.vehicle.vin, a.vehicle.model = ' =1', '@Make', '+VIN', '-Model'
    a.tenant.name = '=Tenant'
    a.order.status, a.order.description, a.order.order_number = Status.COMPLETED, 'Literal, "quoted"\nsecond line', '=RO'
    db_session.add(labor(a, a.order.id, description='\t=Operation'))
    await outside(db_session, a, provider_name='+Provider', reference='-Reference', description='\n@Outside')
    await db_session.flush()
    rows = decoded((await service.export_csv(db_session, a.vehicle.id, a.owner))[0])
    for row in rows:
        for column in ['Unit', 'VIN', 'Make', 'Model', 'Provider', 'Reference', 'Operations']:
            if row[column]:
                assert row[column].startswith("'")
    assert next(r for r in rows if r['Source'] == 'Shop work')['Work description'] == a.order.description


@pytest.mark.asyncio
async def test_merged_vehicle_history_preserves_external_origin(db_session):
    a = await seed(db_session)
    old_id = a.vehicle.id
    record = await outside(db_session, a)
    a.vehicle.vin = '1HTMMAAL17H123456'
    target = Vehicle(id=uuid4(), tenant_id=a.tenant.id, customer_id=a.customer.id, make='Target', model='Truck', vin=a.vehicle.vin)
    db_session.add(target)
    await db_session.commit()
    await merge_vehicles(db_session, tenant_id=a.tenant.id, canonical_id=target.id, duplicate_id=a.vehicle.id, merged_by_user_id=a.owner.id, confirm_vin=target.vin)
    await db_session.commit()
    row = decoded((await service.export_csv(db_session, target.id, a.owner))[0])[0]
    assert row['Vehicle ID'] == str(target.id) and row['Record ID'] == str(record.id) and row['Original vehicle ID'] == str(old_id)
    await error(service.export_csv(db_session, old_id, a.owner), 404, 'vehicle_not_found')


@pytest.mark.asyncio
async def test_http_empty_headers_validation_identity_and_auth(client, db_session):
    from app.main import app
    from app.core.dependencies import get_current_active_user
    a = await seed(db_session)
    app.dependency_overrides[get_current_active_user] = lambda: a.owner
    path = f'/api/v1/vehicles/{a.vehicle.id}/service-history.csv'
    try:
        response = await client.get(path)
        assert response.status_code == 404 and response.json()['detail']['code'] == 'history_empty'
        assert 'content-disposition' not in response.headers
        await outside(db_session, a)
        response = await client.get(path)
        assert response.status_code == 200 and response.headers['content-type'] == 'text/csv; charset=utf-8'
        assert response.headers['x-export-row-count'] == '1' and response.headers['x-export-vehicle-id'] == str(a.vehicle.id)
        assert response.headers['content-disposition'] == f'attachment; filename="vehicle-service-history-{a.vehicle.id}.csv"'
        for query in ['date_from=not-a-date', 'date_from=2026-02-30', 'date_from=1899-12-31', 'date_from=20260101', 'date_from=2026-02-01&date_to=2026-01-01', 'tenant_id=abc', 'limit=1', 'date_from=2026-01-01&date_from=2026-02-01']:
            bad = await client.get(path + '?' + query)
            assert bad.status_code == 422, bad.text
            assert 'content-disposition' not in bad.headers
            assert 'no-store' in bad.headers['cache-control'] and bad.headers['x-content-type-options'] == 'nosniff'
        a.owner.role = UserRole.CUSTOMER
        denied = await client.get(path)
        assert denied.status_code == 403 and 'no-store' in denied.headers['cache-control']
        a.owner.role = UserRole.GARAGE_OWNER
        a.vehicle.deleted_at = datetime.now(UTC)
        await db_session.flush()
        missing = await client.get(path)
        assert missing.status_code == 404 and missing.json()['detail']['code'] == 'vehicle_not_found'
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
    unauthenticated = await client.get(path)
    assert unauthenticated.status_code == 401 and 'no-store' in unauthenticated.headers['cache-control']


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['order', 'labor', 'outside'])
async def test_oversized_raw_text_rejected_before_body_fetch(db_session, monkeypatch, source):
    a = await seed(db_session)
    payload = 'x' * 1025
    if source == 'order':
        await order(db_session, a, description=payload)
    elif source == 'labor':
        a.order.status = Status.COMPLETED
        db_session.add(labor(a, a.order.id, description=payload))
    else:
        await outside(db_session, a, description=payload)
    await db_session.flush()
    monkeypatch.setattr(service, 'MAX_CSV_BYTES', 1024)
    body_fetch = AsyncMock(side_effect=AssertionError('Must reject before text body fetch'))
    monkeypatch.setattr(service, 'bounded_rows', body_fetch)
    await error(service.export_csv(db_session, a.vehicle.id, a.owner), 413, 'history_export_too_large')
    body_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_concurrent_text_growth_after_preflight_still_rejected(db_session, monkeypatch):
    a = await seed(db_session)
    saved = await order(db_session, a)
    original = service.bounded_rows
    first = True
    async def changed_after_preflight(db, statement, raw_characters, maximum_rows):
        nonlocal first
        if first:
            first = False
            saved.description = 'x' * 3000
            await db_session.flush()
        return await original(db, statement, raw_characters, maximum_rows)
    monkeypatch.setattr(service, 'MAX_CSV_BYTES', 1024)
    monkeypatch.setattr(service, 'bounded_rows', changed_after_preflight)
    await error(service.export_csv(db_session, a.vehicle.id, a.owner), 413, 'history_export_too_large')


@pytest.mark.asyncio
async def test_account_transfer_and_deleted_customer_do_not_rewrite_physical_history(db_session):
    from app.db.models.customer import Customer
    a = await seed(db_session)
    replacement = Customer(id=uuid4(), tenant_id=a.tenant.id, first_name='New', last_name='Account', email='never-export@example.invalid')
    db_session.add(replacement)
    old_order = await order(db_session, a)
    await outside(db_session, a)
    a.vehicle.customer_id = replacement.id
    a.customer.deleted_at = datetime.now(UTC)
    await db_session.flush()
    content, count = await service.export_csv(db_session, a.vehicle.id, a.owner)
    assert count == 2 and str(old_order.id).encode() in content
    assert b'never-export@example.invalid' not in content


@pytest.mark.asyncio
async def test_foreign_outside_record_inconsistent_legacy_fixture_is_not_exported(db_session):
    a, b = await seed(db_session), await seed(db_session)
    await outside(db_session, a, tenant_id=b.tenant.id, description='FOREIGN OUTSIDE')
    await outside(db_session, a, description='Visible')
    content, count = await service.export_csv(db_session, a.vehicle.id, a.owner)
    assert count == 1 and b'FOREIGN' not in content


@pytest.mark.asyncio
async def test_http_limit_and_unexpected_failure_are_private_json(client, db_session, monkeypatch):
    from app.main import app
    from app.core.dependencies import get_current_active_user
    a = await seed(db_session)
    await outside(db_session, a)
    app.dependency_overrides[get_current_active_user] = lambda: a.owner
    path = f'/api/v1/vehicles/{a.vehicle.id}/service-history.csv'
    try:
        monkeypatch.setattr(service, 'MAX_CSV_BYTES', 1)
        failed = await client.get(path)
        assert failed.status_code == 413 and failed.json()['detail']['code'] == 'history_export_too_large'
        monkeypatch.setattr(service, 'export_csv', AsyncMock(side_effect=RuntimeError('internal failed source')))
        failed = await client.get(path)
        assert failed.status_code == 500 and failed.json()['detail']['code'] == 'history_export_failed'
        assert 'internal failed source' not in failed.text
        assert 'content-disposition' not in failed.headers and 'x-export-row-count' not in failed.headers
        assert 'no-store' in failed.headers['cache-control'] and failed.headers['x-content-type-options'] == 'nosniff'
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


@pytest.mark.asyncio
async def test_operation_count_cap_rejects_before_text_length_inspection(db_session, monkeypatch):
    a = await seed(db_session)
    a.order.status = Status.COMPLETED
    db_session.add_all([labor(a, a.order.id, description='x' * 2000), labor(a, a.order.id)])
    await db_session.flush()
    monkeypatch.setattr(service, 'MAX_OPERATIONS', 1)
    def should_not_inspect(*columns):
        raise AssertionError('Over-cap operation IDs must reject before inspecting text')
    monkeypatch.setattr(service, 'text_length', should_not_inspect)
    await error(service.export_csv(db_session, a.vehicle.id, a.owner), 413, 'history_export_too_large')
