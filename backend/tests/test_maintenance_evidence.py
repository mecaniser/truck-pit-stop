from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.db.models.maintenance import MaintenanceProgram as Program, MaintenanceWorkLink as Link, MaintenanceCompletion as Completion
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.schemas import maintenance as wire
from app.services import maintenance as service
from app.services import operation_execution
from test_maintenance_work import setup


@pytest.fixture
def db_session(db_session):
    db_session.autoflush = False
    return db_session


def actual(miles='110000'):
    return {'performed_on': (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat(),
        'confirm_actual_service_readings': True, 'readings': {'odometer_miles': {'kind': 'manual', 'value': miles, 'basis': 'staff_observed', 'note': None} if miles is not None else None, 'engine_hours': None}}


async def work(db):
    a, item, body = await setup(db)
    preview = await service.work_preview(db, a.owner, a.vehicle.id, body)
    result = await service.work_command(db, a.owner, a.vehicle.id,
        wire.WorkCommit.model_validate({**body.model_dump(mode='json'), 'expected_work_fingerprint': preview['expected_work_fingerprint']}), str(uuid4()))
    order = await db.get(RepairOrder, UUID(result['repair_order_id']))
    order.status = RepairOrderStatus.PENDING_REVIEW
    order.work_completed_at = datetime.now(timezone.utc)
    await db.commit()
    return a, item, order, result


async def qualify(db, order):
    """Fixture the existing work/checklist eligibility before reviewing targets."""
    from app.db.models.labor import Labor
    from app.db.models.service_checklist import RepairOrderChecklistItem as Task
    from app.db.models.user import User,UserRole
    actor=await db.scalar(select(User).where(User.tenant_id==order.tenant_id,User.role==UserRole.GARAGE_OWNER))
    for task in (await db.scalars(select(Task).where(Task.repair_order_id == order.id))).all():
        task.is_completed = True
        task.completed_at = datetime.now(timezone.utc)
        task.completed_by_user_id = actor.id
        task.completed_by_name = 'Synthetic Manager'
    for operation in (await db.scalars(select(Labor).where(Labor.repair_order_id == order.id))).all():
        if operation.execution_status != 'completed':
            operation.execution_status = 'completed'
            operation.execution_version += 1
            operation.completed_at = datetime.now(timezone.utc)
    await db.commit()


async def reviewed(db, a, order, values):
    await qualify(db, order)
    summary = await service.order_maintenance(db, a.owner, 'shop', order.id)
    programs = {row['id']: row for row in summary['programs']}
    links = list((await db.scalars(select(Link).where(Link.repair_order_id == order.id).order_by(Link.id))).all())
    entries = [{'work_link_id': str(link.id), 'expected_link_version': link.version,
        'program': {'program_id': str(link.program_id), 'expected_version': programs[str(link.program_id)]['version']}, 'attestation': value} for link, value in zip(links, values)]
    body = wire.CompletionPreview.model_validate({'purpose': 'completion', 'channel': 'shop', 'repair_order_id': str(order.id),
        'expected_review_fingerprint': summary['expected_review_fingerprint'], 'entries': entries})
    preview = await service.target_preview(db, a.owner, a.vehicle.id, body)
    return wire.MaintenanceReview.model_validate({'request_id': str(uuid4()), 'expected_review_fingerprint': summary['expected_review_fingerprint'],
        'expected_target_fingerprint': preview['expected_target_fingerprint'], 'entries': entries}), preview


@pytest.mark.asyncio
async def test_completion_advances_valid_program_and_retains_pending_then_resolves_once(db_session):
    a, item, order, attached = await work(db_session)
    from app.db.models.labor import Labor
    for operation in (await db_session.scalars(select(Labor).where(Labor.repair_order_id == order.id))).all():
        operation.execution_status = 'completed'
        operation.execution_version += 1
        operation.completed_at = datetime.now(timezone.utc)
    await db_session.commit()
    review, preview = await reviewed(db_session, a, order, [actual(), actual(None)])
    assert {item['outcome'] for item in preview['items']} == {'advanced', 'pending_evidence'}
    prepared = await service.prepare_finalization(db_session, a.owner, order, review, channel='shop')
    await operation_execution.finish_order(db_session, order, a.owner)
    order.status = RepairOrderStatus.COMPLETED
    result = await service.finish_finalization(db_session, a.owner, order, prepared)
    await db_session.commit()
    assert {item['result'] for item in result['items']} == {'advanced', 'pending_evidence'}
    pending = await db_session.scalar(select(Link).where(Link.repair_order_id == order.id, Link.state == 'pending_evidence'))
    program = await db_session.get(Program, pending.program_id)
    assert program.target_miles == 100000 and program.current_cycle == 1
    raw = {'purpose': 'evidence', 'channel': 'shop', 'program': {'program_id': str(program.id), 'expected_version': program.version},
        'evidence': {'action': 'resolve_pending', 'work_link_id': str(pending.id), 'expected_link_version': pending.version, 'attestation': actual()}}
    preview = await service.target_preview(db_session, a.owner, a.vehicle.id, wire.EvidencePreview.model_validate(raw))
    body = wire.EvidenceCommit.model_validate({key: value for key, value in {**raw, 'expected_target_fingerprint': preview['expected_target_fingerprint']}.items() if key != 'purpose'})
    key = str(uuid4())
    saved = await service.evidence_command(db_session, a.owner, a.vehicle.id, body, key)
    repeat = await service.evidence_command(db_session, a.owner, a.vehicle.id, body, key)
    assert saved['completion']['result'] == 'advanced' and repeat['replayed']
    assert saved['program']['targets']['odometer_miles'] == 111000 and saved['program']['current_cycle'] == 2
    assert await db_session.scalar(select(func.count(Completion.id))) == 3
    # Neither actual attestation nor pending resolution changes native mileage.
    await db_session.refresh(order)
    assert order.mileage_out is None


@pytest.mark.asyncio
async def test_absent_review_is_pending_and_invalid_stale_review_is_atomic(db_session):
    a, item, order, attached = await work(db_session)
    review, _ = await reviewed(db_session, a, order, [actual(), actual()])
    first = await db_session.scalar(select(Program).order_by(Program.id))
    before = service.snapshot(first)
    service.touch(first, a.owner)
    first.name = 'Changed after review'
    service.append_event(db_session, a.owner, first, 'rename', before)
    await db_session.commit()
    with pytest.raises(HTTPException) as error:
        await service.prepare_finalization(db_session, a.owner, order, review, channel='shop')
    assert error.value.detail['code'] == 'maintenance_preview_changed'
    await db_session.rollback()
    await db_session.refresh(a.owner)
    await db_session.refresh(order)
    await qualify(db_session, order)
    prepared = await service.prepare_finalization(db_session, a.owner, order, None, channel='shop')
    order.status = RepairOrderStatus.COMPLETED
    result = await service.finish_finalization(db_session, a.owner, order, prepared)
    await db_session.commit()
    assert all(item['result'] == 'pending_evidence' and item['missing'] == ['attestation'] for item in result['items'])
    assert all(row.current_cycle == 1 and row.target_miles == 100000 for row in (await db_session.scalars(select(Program))).all())


@pytest.mark.asyncio
async def test_shared_remove_requires_current_confirmation_and_detaches_whole_scope(db_session):
    a, item, order, attached = await work(db_session)
    order.status = RepairOrderStatus.DRAFT
    await db_session.commit()
    summary = await service.order_maintenance(db_session, a.owner, 'shop', order.id)
    operation = UUID(summary['links'][0]['operation_ids'][0])
    with pytest.raises(HTTPException) as error:
        await service.guard_operation_removal(db_session, a.owner, order, [operation])
    assert error.value.detail['code'] == 'maintenance_preview_changed'
    assert all(link.state == 'active' for link in (await db_session.scalars(select(Link))).all())
    await service.guard_operation_removal(db_session, a.owner, order, [operation], expected=summary['expected_review_fingerprint'])
    await db_session.commit()
    assert all(link.state == 'detached' for link in (await db_session.scalars(select(Link))).all())


@pytest.mark.asyncio
async def test_delete_restore_reclaims_and_conflicting_target_blocks_before_restore(db_session):
    a, item, order, attached = await work(db_session)
    order.status = RepairOrderStatus.DRAFT
    await db_session.commit()
    await service.order_lifecycle(db_session, a.owner, order, 'delete')
    order.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    await service.order_lifecycle(db_session, a.owner, order, 'restore')
    order.deleted_at = None
    await db_session.commit()
    assert all(row.state == 'active' for row in (await db_session.scalars(select(Link))).all())
    await service.order_lifecycle(db_session, a.owner, order, 'delete')
    order.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    program = await db_session.scalar(select(Program).order_by(Program.id))
    before = service.snapshot(program)
    service.touch(program, a.owner)
    program.current_cycle += 1
    service.append_event(db_session, a.owner, program, 'changed', before)
    await db_session.commit()
    with pytest.raises(HTTPException) as error:
        await service.order_lifecycle(db_session, a.owner, order, 'restore')
    assert error.value.detail['code'] == 'maintenance_restore_conflict'
    assert order.deleted_at is not None


@pytest.mark.asyncio
async def test_historical_evidence_never_edits_source_and_correction_requires_complete_ack(db_session):
    from test_service_checklists import seed
    from test_maintenance_programs import create
    from app.db.models.labor import Labor
    a = await seed(db_session)
    a.order.status = RepairOrderStatus.PAID
    a.order.mileage_out = 99999
    await db_session.commit()
    created, _ = await create(db_session, a)
    program_id = UUID(created['program']['id'])
    raw = {'purpose': 'evidence', 'channel': 'shop', 'program': {'program_id': str(program_id), 'expected_version': 1},
        'evidence': {'action': 'recognize', 'source': {'kind': 'repair_order', 'id': str(a.order.id)}, 'attestation': actual()}}
    preview = await service.target_preview(db_session, a.owner, a.vehicle.id, wire.EvidencePreview.model_validate(raw))
    body = wire.EvidenceCommit.model_validate({k: v for k, v in {**raw, 'expected_target_fingerprint': preview['expected_target_fingerprint']}.items() if k != 'purpose'})
    evidence = await service.evidence_command(db_session, a.owner, a.vehicle.id, body, str(uuid4()))
    await db_session.refresh(a.order)
    assert a.order.status == RepairOrderStatus.PAID and not a.order.is_pm and a.order.mileage_out == 99999
    assert a.vehicle.mileage is None
    planning = wire.WorkRequest.model_validate({'channel': 'shop', 'programs': [{'program_id': str(program_id), 'expected_version': evidence['program']['version']}],
        'target': {'kind': 'new', 'bill_to_customer_id': str(a.customer.id), 'description': None},
        'coverage': [{'key': 'next', 'program_ids': [str(program_id)], 'service_id': str(a.service.id), 'operation': {'kind': 'new'}}]})
    work_preview = await service.work_preview(db_session, a.owner, a.vehicle.id, planning)
    scheduled = await service.work_command(db_session, a.owner, a.vehicle.id,
        wire.WorkCommit.model_validate({**planning.model_dump(mode='json'), 'expected_work_fingerprint': work_preview['expected_work_fingerprint']}), str(uuid4()))
    await service.order_lifecycle(db_session, a.owner, a.order, 'source_update')
    a.order.mileage_out = 100001
    await db_session.commit()
    program = await db_session.get(Program, program_id)
    assert 'source_changed' in program.review_codes
    raw = {'purpose': 'evidence', 'channel': 'shop', 'program': {'program_id': str(program_id), 'expected_version': program.version},
        'evidence': {'action': 'reaffirm', 'completion_id': evidence['completion']['id'], 'reason': 'Verified actual service', 'acknowledged_work_link_ids': []}}
    discover = await service.target_preview(db_session, a.owner, a.vehicle.id, wire.EvidencePreview.model_validate(raw))
    assert len(discover['affected_work']) == 1
    body = wire.EvidenceCommit.model_validate({k: v for k, v in {**raw, 'expected_target_fingerprint': discover['expected_target_fingerprint']}.items() if k != 'purpose'})
    with pytest.raises(HTTPException) as error:
        await service.evidence_command(db_session, a.owner, a.vehicle.id, body, str(uuid4()))
    assert error.value.detail['code'] == 'maintenance_preview_changed'
    await db_session.rollback()
    await db_session.refresh(a.owner)
    await db_session.refresh(a.vehicle)
    raw['evidence']['acknowledged_work_link_ids'] = [row['work_link_id'] for row in discover['affected_work']]
    reviewed = await service.target_preview(db_session, a.owner, a.vehicle.id, wire.EvidencePreview.model_validate(raw))
    body = wire.EvidenceCommit.model_validate({k: v for k, v in {**raw, 'expected_target_fingerprint': reviewed['expected_target_fingerprint']}.items() if k != 'purpose'})
    result = await service.evidence_command(db_session, a.owner, a.vehicle.id, body, str(uuid4()))
    assert result['completion']['result'] == 'reaffirmed' and not result['program']['review']['required']
    assert result['program']['targets']['odometer_miles'] == 111000
    assert result['program']['current_cycle'] == 2


@pytest.mark.asyncio
async def test_performed_delete_keeps_review_claim_and_target_change_blocks_restore(db_session):
    from app.db.models.labor import Labor
    a, _, order, _ = await work(db_session)
    operation = await db_session.scalar(select(Labor).where(Labor.repair_order_id == order.id))
    operation.execution_status = 'completed'
    operation.completed_at = datetime.now(timezone.utc)
    await db_session.commit()
    await service.order_lifecycle(db_session, a.owner, order, 'delete')
    order.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    assert all(row.state == 'review_required' for row in (await db_session.scalars(select(Link))).all())
    assert all(row.target_miles == 100000 and row.current_cycle == 1 for row in (await db_session.scalars(select(Program))).all())


@pytest.mark.asyncio
async def test_changed_targets_cannot_reclaim_detached_cycle(db_session):
    a, _, order, _ = await work(db_session)
    await service.order_lifecycle(db_session, a.owner, order, 'delete')
    order.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    program = await db_session.scalar(select(Program).order_by(Program.id))
    before = service.snapshot(program)
    service.touch(program, a.owner)
    program.target_miles += 1
    service.append_event(db_session, a.owner, program, 'explicit_target_change', before)
    await db_session.commit()
    with pytest.raises(HTTPException) as error:
        await service.order_lifecycle(db_session, a.owner, order, 'restore')
    assert error.value.detail['code'] == 'maintenance_restore_conflict'
    assert order.deleted_at is not None


@pytest.mark.asyncio
async def test_pending_supersede_closes_original_claim_once(db_session):
    a, _, order, _ = await work(db_session)
    await qualify(db_session, order)
    prepared = await service.prepare_finalization(db_session, a.owner, order, None, channel='shop')
    order.status = RepairOrderStatus.COMPLETED
    await service.finish_finalization(db_session, a.owner, order, prepared)
    await db_session.commit()
    original = await db_session.scalar(select(Completion).order_by(Completion.id))
    program = await db_session.get(Program, original.program_id)
    raw = {'purpose': 'evidence', 'channel': 'shop', 'program': {'program_id': str(program.id), 'expected_version': program.version},
        'evidence': {'action': 'supersede', 'completion_id': str(original.id), 'reason': 'Actual completed meter confirmed',
            'attestation': actual(), 'acknowledged_work_link_ids': [str(original.work_link_id)]}}
    preview = await service.target_preview(db_session, a.owner, a.vehicle.id, wire.EvidencePreview.model_validate(raw))
    body = wire.EvidenceCommit.model_validate({k: v for k, v in {**raw, 'expected_target_fingerprint': preview['expected_target_fingerprint']}.items() if k != 'purpose'})
    saved = await service.evidence_command(db_session, a.owner, a.vehicle.id, body, str(uuid4()))
    assert saved['completion']['result'] == 'advanced' and saved['program']['current_cycle'] == 2
    assert (await db_session.get(Link, original.work_link_id)).state == 'completed'


@pytest.mark.asyncio
async def test_finalized_financial_progression_keeps_source_digest_but_snapshots_exact_status(db_session):
    from test_service_checklists import seed
    a = await seed(db_session)
    a.order.work_completed_at = datetime.now(timezone.utc)
    a.order.status = RepairOrderStatus.COMPLETED
    await db_session.commit()
    _, snapshot, digest = await service.source_context(db_session,a.owner,'shop',a.vehicle,wire.SourceRef(kind='repair_order',id=a.order.id))
    assert snapshot['status'] == 'completed'
    for status in [RepairOrderStatus.INVOICED,RepairOrderStatus.PAID]:
        a.order.status = status
        a.order.updated_at = datetime.now(timezone.utc)
        a.order.total_cost = 999
        await db_session.commit()
        _, changed, next_digest = await service.source_context(db_session,a.owner,'shop',a.vehicle,wire.SourceRef(kind='repair_order',id=a.order.id))
        assert changed['status'] == status.value and next_digest == digest
    a.order.mileage_out = 1
    await db_session.commit()
    assert (await service.source_context(db_session,a.owner,'shop',a.vehicle,wire.SourceRef(kind='repair_order',id=a.order.id)))[2] != digest
    a.order.mileage_out = None
    a.order.status = RepairOrderStatus.IN_PROGRESS
    await db_session.commit()
    assert (await service.source_context(db_session,a.owner,'shop',a.vehicle,wire.SourceRef(kind='repair_order',id=a.order.id),finalized=False))[2] != digest
    with pytest.raises(HTTPException):
        await service.source_context(db_session,a.owner,'shop',a.vehicle,wire.SourceRef(kind='repair_order',id=a.order.id))


@pytest.mark.asyncio
@pytest.mark.parametrize('correction', ['reaffirm', 'revoke'])
@pytest.mark.parametrize('resolution', ['resolve_pending', 'supersede'])
async def test_pending_correction_chain_resolves_latest_evidence_once(db_session, correction, resolution):
    a, _, order, _ = await work(db_session)
    await qualify(db_session, order)
    prepared = await service.prepare_finalization(db_session, a.owner, order, None, channel='shop')
    order.status = RepairOrderStatus.COMPLETED
    await service.finish_finalization(db_session, a.owner, order, prepared)
    await db_session.commit()
    original = await db_session.scalar(select(Completion).order_by(Completion.id))
    program = await db_session.get(Program, original.program_id)
    link = await db_session.get(Link, original.work_link_id)

    async def commit(intent):
        raw = {'purpose': 'evidence', 'channel': 'shop', 'program': {'program_id': str(program.id), 'expected_version': program.version}, 'evidence': intent}
        preview = await service.target_preview(db_session, a.owner, a.vehicle.id, wire.EvidencePreview.model_validate(raw))
        command = wire.EvidenceCommit.model_validate({k: v for k, v in {**raw, 'expected_target_fingerprint': preview['expected_target_fingerprint']}.items() if k != 'purpose'})
        return await service.evidence_command(db_session, a.owner, a.vehicle.id, command, str(uuid4()))

    corrected = await commit({'action': correction, 'completion_id': str(original.id), 'reason': 'Review pending service evidence', 'acknowledged_work_link_ids': [str(link.id)]})
    assert corrected['program']['current_cycle'] == 1 and corrected['program']['targets']['odometer_miles'] == 100000
    intent = {'action': resolution, 'attestation': actual()}
    if resolution == 'resolve_pending':
        intent.update(work_link_id=str(link.id), expected_link_version=link.version)
    else:
        intent.update(completion_id=corrected['completion']['id'], reason='Actual service reading confirmed', acknowledged_work_link_ids=[str(link.id)])
    saved = await commit(intent)
    latest = await db_session.get(Completion, UUID(saved['completion']['id']))
    assert latest.supersedes_id == UUID(corrected['completion']['id'])
    assert saved['program']['current_cycle'] == 2 and saved['program']['targets']['odometer_miles'] == 111000
    assert link.state == 'completed'
    assert await db_session.scalar(select(func.count(Completion.id)).where(Completion.program_id == program.id)) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('action', ['delete', 'cancel'])
async def test_partial_performed_explicit_restore_preserves_execution_and_targets(db_session, action):
    from app.db.models.labor import Labor
    a, _, order, _ = await work(db_session)
    operation = await db_session.scalar(select(Labor).where(Labor.repair_order_id == order.id))
    order.status = RepairOrderStatus.IN_PROGRESS
    operation.execution_status = 'completed'
    operation.execution_version += 1
    operation.completed_at = datetime.now(timezone.utc)
    await db_session.commit()
    facts = (operation.id, operation.execution_status, operation.execution_version, operation.completed_at, operation.hours, operation.hourly_rate, order.total_cost)
    await service.order_lifecycle(db_session,a.owner,order,action)
    if action == 'delete':
        order.deleted_at = datetime.now(timezone.utc)
    else:
        order.status = RepairOrderStatus.CANCELLED
    await db_session.commit()
    links = list((await db_session.scalars(select(Link))).all())
    assert all(row.state == 'review_required' for row in links)
    if action == 'cancel':
        await service.order_lifecycle(db_session,a.owner,order,'restore')
        assert all(row.state == 'review_required' for row in links)  # still cancelled
    await service.order_lifecycle(db_session,a.owner,order,'restore',intended_status=RepairOrderStatus.IN_PROGRESS)
    order.deleted_at = None
    order.status = RepairOrderStatus.IN_PROGRESS
    await db_session.commit()
    assert all(row.state == 'active' for row in links)
    assert facts == (operation.id, operation.execution_status, operation.execution_version, operation.completed_at, operation.hours, operation.hourly_rate, order.total_cost)
    assert all(row.current_cycle == 1 and row.target_miles == 100000 for row in (await db_session.scalars(select(Program))).all())
    assert await db_session.scalar(select(func.count(Completion.id))) == 0
    # Resume the original work and finalize it once, rather than creating a new claim.
    review, _ = await reviewed(db_session,a,order,[actual(),actual()])
    prepared = await service.prepare_finalization(db_session,a.owner,order,review,channel='shop')
    order.status = RepairOrderStatus.COMPLETED
    result = await service.finish_finalization(db_session,a.owner,order,prepared)
    await db_session.commit()
    assert all(item['result'] == 'advanced' for item in result['items'])
    assert all(row.current_cycle == 2 for row in (await db_session.scalars(select(Program))).all())


@pytest.mark.asyncio
@pytest.mark.parametrize('changed', ['target_aba', 'operation_aba', 'missing_mapping', 'source_review'])
async def test_partial_restore_rejects_changed_or_aba_scope_before_order_mutation(db_session, changed):
    from app.db.models.labor import Labor
    from app.db.models.maintenance import MaintenanceOperationLink as Mapping
    a, _, order, _ = await work(db_session)
    operation = await db_session.scalar(select(Labor).where(Labor.repair_order_id == order.id))
    operation.execution_status = 'completed'
    operation.execution_version += 1
    operation.completed_at = datetime.now(timezone.utc)
    order.status = RepairOrderStatus.IN_PROGRESS
    await db_session.commit()
    await service.order_lifecycle(db_session,a.owner,order,'delete')
    order.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    program = await db_session.scalar(select(Program).order_by(Program.id))
    if changed == 'target_aba':
        for delta in [1,-1]:
            before = service.snapshot(program)
            service.touch(program,a.owner)
            program.target_miles += delta
            service.append_event(db_session,a.owner,program,'explicit_target_change',before)
            await db_session.flush()
    elif changed == 'operation_aba':
        operation.execution_version += 2  # completed -> reopened -> completed
    elif changed == 'missing_mapping':
        mapping = await db_session.scalar(select(Mapping).where(Mapping.work_link_id == (await db_session.scalar(select(Link.id).where(Link.program_id==program.id)))))
        mapping.state = 'detached'
        mapping.version += 1
    else:
        await service.order_lifecycle(db_session,a.owner,order,'source_update')
    await db_session.commit()
    with pytest.raises(HTTPException) as failure:
        await service.order_lifecycle(db_session,a.owner,order,'restore')
    assert failure.value.detail['code'] == 'maintenance_restore_conflict'
    assert order.deleted_at is not None
    await db_session.rollback()
    assert await db_session.scalar(select(func.count(Completion.id))) == 0


@pytest.mark.asyncio
async def test_financial_status_progression_preserves_review_token_and_reopen_does_not_clear_review(db_session):
    from test_service_checklists import seed
    from test_maintenance_programs import create
    a = await seed(db_session)
    a.order.status = RepairOrderStatus.COMPLETED
    a.order.work_completed_at = datetime.now(timezone.utc)
    await db_session.commit()
    created, _ = await create(db_session,a)
    raw={'purpose':'evidence','channel':'shop','program':{'program_id':created['program']['id'],'expected_version':1},
        'evidence':{'action':'recognize','source':{'kind':'repair_order','id':str(a.order.id)},'attestation':actual()}}
    preview=await service.target_preview(db_session,a.owner,a.vehicle.id,wire.EvidencePreview.model_validate(raw))
    for status in [RepairOrderStatus.INVOICED,RepairOrderStatus.PAID]:
        a.order.status=status
        a.order.updated_at=datetime.now(timezone.utc)
        await db_session.commit()
        changed=await service.target_preview(db_session,a.owner,a.vehicle.id,wire.EvidencePreview.model_validate(raw))
        assert changed['expected_target_fingerprint']==preview['expected_target_fingerprint']
    saved=await service.evidence_command(db_session,a.owner,a.vehicle.id,wire.EvidenceCommit.model_validate({k:v for k,v in {**raw,'expected_target_fingerprint':preview['expected_target_fingerprint']}.items() if k!='purpose'}),str(uuid4()))
    evidence=await db_session.get(Completion,UUID(saved['completion']['id']))
    assert evidence.source_snapshot['status']=='paid'
    program=await db_session.get(Program,evidence.program_id)
    targets,cycle=service.targets(program),program.current_cycle
    await service.order_lifecycle(db_session,a.owner,a.order,'reopen')
    a.order.status=RepairOrderStatus.IN_PROGRESS
    await db_session.commit()
    a.order.status=RepairOrderStatus.COMPLETED
    await db_session.commit()
    assert program.review_codes==['source_changed'] and program.current_cycle==cycle and service.targets(program)==targets
    assert evidence.source_snapshot['status']=='paid'


@pytest.mark.asyncio
async def test_same_day_observation_preceding_actual_service_is_not_a_false_regression(db_session):
    from zoneinfo import ZoneInfo
    from app.db.models.maintenance import MaintenanceReading as Reading
    a, _, order, _ = await work(db_session)
    stamp=datetime.now(timezone.utc)
    day=stamp.astimezone(ZoneInfo(a.tenant.timezone)).date().isoformat()
    older=Reading(tenant_id=a.tenant.id,vehicle_id=a.vehicle.id,observed_at=stamp-timedelta(minutes=1),
        created_at=stamp-timedelta(seconds=30),odometer_miles=100713,source='staff_observed',actor_id=a.owner.id,request_id=uuid4())
    db_session.add(older)
    await db_session.commit()
    attestation={**actual('101000'),'performed_on':day}
    review,_=await reviewed(db_session,a,order,[attestation,attestation])
    prepared=await service.prepare_finalization(db_session,a.owner,order,review,channel='shop')
    order.status=RepairOrderStatus.COMPLETED
    await service.finish_finalization(db_session,a.owner,order,prepared)
    await db_session.commit()
    programs=list((await db_session.scalars(select(Program))).all())
    for program in programs:
        result=await service.program_view(db_session,a.owner,'shop',program,a.vehicle,a.tenant,datetime.now(timezone.utc))
        assert result['due']['miles']['reading']['comparison_value']=='101000'
        assert not result['review']['required']
        assert result['due']['miles']['reading']['observed_at'] is None
        assert result['due']['miles']['reading']['observed_on']==day
    # A newly observed lower meter after accepted actual service remains a real
    # review signal; acceptance does not reset or rewrite vehicle observations.
    later=Reading(tenant_id=a.tenant.id,vehicle_id=a.vehicle.id,observed_at=datetime.now(timezone.utc)+timedelta(seconds=1),
        created_at=datetime.now(timezone.utc)+timedelta(seconds=1),odometer_miles=100800,source='staff_observed',actor_id=a.owner.id,request_id=uuid4())
    db_session.add(later)
    await db_session.commit()
    result=await service.program_view(db_session,a.owner,'shop',programs[0],a.vehicle,a.tenant,datetime.now(timezone.utc)+timedelta(seconds=2))
    assert result['review']['codes']==['reading_regression']
    assert result['due']['miles']['reading']['value']=='100800'
    await db_session.refresh(older)
    assert older.odometer_miles==100713


@pytest.mark.asyncio
async def test_disabled_meter_regression_does_not_mark_date_only_program_for_review(db_session,monkeypatch):
    from test_service_checklists import seed
    from test_maintenance_programs import create,config,explicit
    a=await seed(db_session)
    cfg=config(a)
    cfg['intervals']={'days':90,'miles':None,'engine_hours':None}
    target=explicit()
    target['targets']['odometer_miles']=None
    created,_=await create(db_session,a,cfg=cfg,initial=target)
    program=await db_session.get(Program,UUID(created['program']['id']))
    original=service.current_readings
    async def regression(*args,**kwargs):
        readings=await original(*args,**kwargs)
        readings['odometer_miles']={'value':'100','comparison_value':None,'admission':'regression','freshness':'fresh'}
        return readings
    monkeypatch.setattr(service,'current_readings',regression)
    result=await service.program_view(db_session,a.owner,'shop',program,a.vehicle,a.tenant,datetime.now(timezone.utc))
    assert result['due']['miles']['state']=='disabled' and not result['review']['required']


@pytest.mark.asyncio
async def test_reaffirm_does_not_move_actual_reading_acceptance_boundary(db_session):
    from zoneinfo import ZoneInfo
    from app.db.models.maintenance import MaintenanceReading as Reading
    a,_,order,_=await work(db_session)
    day=datetime.now(timezone.utc).astimezone(ZoneInfo(a.tenant.timezone)).date().isoformat()
    review,_=await reviewed(db_session,a,order,[{**actual('101000'),'performed_on':day},None])
    prepared=await service.prepare_finalization(db_session,a.owner,order,review,channel='shop')
    order.status=RepairOrderStatus.COMPLETED
    await service.finish_finalization(db_session,a.owner,order,prepared)
    await db_session.commit()
    completion=await db_session.scalar(select(Completion).where(Completion.result=='advanced'))
    program=await db_session.get(Program,completion.program_id)
    observed=datetime.now(timezone.utc)
    reading=Reading(tenant_id=a.tenant.id,vehicle_id=a.vehicle.id,observed_at=observed,created_at=observed,
        odometer_miles=100800,source='staff_observed',actor_id=a.owner.id,request_id=uuid4())
    db_session.add(reading)
    await db_session.commit()
    raw={'purpose':'evidence','channel':'shop','program':{'program_id':str(program.id),'expected_version':program.version},
        'evidence':{'action':'reaffirm','completion_id':str(completion.id),'reason':'Verified unchanged actual evidence','acknowledged_work_link_ids':[]}}
    preview=await service.target_preview(db_session,a.owner,a.vehicle.id,wire.EvidencePreview.model_validate(raw))
    result=await service.evidence_command(db_session,a.owner,a.vehicle.id,wire.EvidenceCommit.model_validate({k:v for k,v in {**raw,'expected_target_fingerprint':preview['expected_target_fingerprint']}.items() if k!='purpose'}),str(uuid4()))
    assert result['program']['review']['codes']==['reading_regression']
    assert result['program']['targets']['odometer_miles']==102000
    assert result['program']['current_cycle']==2


@pytest.mark.asyncio
@pytest.mark.parametrize('eligibility', ['checklist', 'operation', 'hold'])
async def test_completion_preview_reuses_read_only_work_eligibility(db_session,eligibility):
    from app.db.models.service_checklist import RepairOrderChecklistItem as Task
    from app.db.models.maintenance import MaintenanceProgramEvent as Event
    a,_,order,_=await work(db_session)
    order.work_completed_at=None
    if eligibility!='checklist':
        for task in (await db_session.scalars(select(Task).where(Task.repair_order_id==order.id))).all():
            task.is_completed=True
            task.completed_at=datetime.now(timezone.utc)
            task.completed_by_user_id=a.owner.id
            task.completed_by_name='Synthetic Manager'
    if eligibility=='hold':
        await qualify(db_session,order)
        order.hold_reason='waiting_parts'
    await db_session.commit()
    summary=await service.order_maintenance(db_session,a.owner,'shop',order.id)
    by_id={row['id']:row for row in summary['programs']}
    links=list((await db_session.scalars(select(Link).where(Link.repair_order_id==order.id))).all())
    raw={'purpose':'completion','channel':'shop','repair_order_id':str(order.id),'expected_review_fingerprint':summary['expected_review_fingerprint'],
        'entries':[{'work_link_id':str(link.id),'expected_link_version':link.version,'program':{'program_id':str(link.program_id),'expected_version':by_id[str(link.program_id)]['version']},'attestation':None} for link in links]}
    count=await db_session.scalar(select(func.count(Event.id)))
    with pytest.raises(HTTPException) as failure:
        await service.target_preview(db_session,a.owner,a.vehicle.id,wire.CompletionPreview.model_validate(raw))
    assert failure.value.status_code==409 and isinstance(failure.value.detail,str)
    assert {'checklist':'checklist tasks','operation':'remaining operation','hold':'held order'}[eligibility] in failure.value.detail
    assert order.work_completed_at is None and order.status==RepairOrderStatus.PENDING_REVIEW
    assert await db_session.scalar(select(func.count(Event.id)))==count
    assert await db_session.scalar(select(func.count(Completion.id)))==0


@pytest.mark.asyncio
@pytest.mark.parametrize('day_offset', [-1,0,1])
async def test_manager_chronology_never_rewinds_and_missing_review_can_resolve_history(db_session,day_offset):
    a,_,first,_=await work(db_session)
    a.tenant.timezone='UTC'
    await db_session.commit()
    first_actual=actual()
    review,_=await reviewed(db_session,a,first,[first_actual,first_actual])
    prepared=await service.prepare_finalization(db_session,a.owner,first,review,channel='shop')
    first.status=RepairOrderStatus.COMPLETED
    await service.finish_finalization(db_session,a.owner,first,prepared)
    await db_session.commit()
    programs=list((await db_session.scalars(select(Program).order_by(Program.id))).all())
    before={row.id:(service.targets(row),row.current_cycle,row.controlling_completion_id) for row in programs}
    body=wire.WorkRequest.model_validate({'channel':'shop','programs':[{'program_id':str(row.id),'expected_version':row.version} for row in programs],
        'target':{'kind':'new','bill_to_customer_id':str(a.customer.id),'description':'Next actual service'},
        'coverage':[{'key':'next','program_ids':[str(row.id) for row in programs],'service_id':str(a.service.id),'operation':{'kind':'new'}}]})
    preview=await service.work_preview(db_session,a.owner,a.vehicle.id,body)
    work_result=await service.work_command(db_session,a.owner,a.vehicle.id,wire.WorkCommit.model_validate({**body.model_dump(mode='json'),'expected_work_fingerprint':preview['expected_work_fingerprint']}),str(uuid4()))
    order=await db_session.get(RepairOrder,UUID(work_result['repair_order_id']))
    order.status=RepairOrderStatus.PENDING_REVIEW
    await qualify(db_session,order)
    summary=await service.order_maintenance(db_session,a.owner,'shop',order.id)
    links=list((await db_session.scalars(select(Link).where(Link.repair_order_id==order.id).order_by(Link.id))).all())
    date_value=(datetime.fromisoformat(first_actual['performed_on']).date()+timedelta(days=day_offset)).isoformat()
    value={**actual(),'performed_on':date_value}
    entries=[{'work_link_id':str(link.id),'expected_link_version':link.version,
        'program':{'program_id':str(link.program_id),'expected_version':(await db_session.get(Program,link.program_id)).version},'attestation':value} for link in links]
    raw={'purpose':'completion','channel':'shop','repair_order_id':str(order.id),'expected_review_fingerprint':summary['expected_review_fingerprint'],'entries':entries}
    if day_offset<=0:
        with pytest.raises(HTTPException) as invalid:
            await service.target_preview(db_session,a.owner,a.vehicle.id,wire.CompletionPreview.model_validate(raw))
        assert invalid.value.detail['code']=='maintenance_review_required'
        review=wire.MaintenanceReview.model_validate({'request_id':str(uuid4()),'expected_review_fingerprint':summary['expected_review_fingerprint'],'expected_target_fingerprint':'0'*64,'entries':entries})
        with pytest.raises(HTTPException) as locked:
            await service.prepare_finalization(db_session,a.owner,order,review,channel='shop')
        assert locked.value.detail['code']=='maintenance_review_required'
        assert order.status==RepairOrderStatus.PENDING_REVIEW
        assert await db_session.scalar(select(func.count(Completion.id)))==2
        assert all((service.targets(row),row.current_cycle,row.controlling_completion_id)==before[row.id] for row in programs)
        if day_offset==0:
            return
        prepared=await service.prepare_finalization(db_session,a.owner,order,None,channel='shop')
        order.status=RepairOrderStatus.COMPLETED
        await service.finish_finalization(db_session,a.owner,order,prepared)
        await db_session.commit()
        link=links[0]
        program=await db_session.get(Program,link.program_id)
        raw={'purpose':'evidence','channel':'shop','program':{'program_id':str(program.id),'expected_version':program.version},
            'evidence':{'action':'resolve_pending','work_link_id':str(link.id),'expected_link_version':link.version,'attestation':value}}
        preview=await service.target_preview(db_session,a.owner,a.vehicle.id,wire.EvidencePreview.model_validate(raw))
        assert preview['items'][0]['outcome']=='history_only'
        saved=await service.evidence_command(db_session,a.owner,a.vehicle.id,wire.EvidenceCommit.model_validate({k:v for k,v in {**raw,'expected_target_fingerprint':preview['expected_target_fingerprint']}.items() if k!='purpose'}),str(uuid4()))
        assert saved['completion']['result']=='history_only' and link.state=='completed'
        assert (service.targets(program),program.current_cycle,program.controlling_completion_id)==before[program.id]
    else:
        preview=await service.target_preview(db_session,a.owner,a.vehicle.id,wire.CompletionPreview.model_validate(raw))
        assert all(row['outcome']=='advanced' for row in preview['items'])
