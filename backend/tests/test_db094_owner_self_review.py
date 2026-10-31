"""Owner opt-in changes reviewer separation only; every identity guard still applies."""
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import select

from app.api.v1.endpoints import historical_invoice_reviews as reviews
from app.core.security import create_access_token
from app.db.models.historical_invoice_export import HistoricalInvoiceEvidence, HistoricalInvoiceDecision, HistoricalInvoiceMapping
from app.db.models.user import UserRole
from test_db094_historical_identity_proof import seed, record, request, approval


def headers(user):
    return {"Authorization": f'Bearer {create_access_token({"sub": str(user.id)})}'}


@pytest.mark.asyncio
@pytest.mark.parametrize('replacement', [False, True])
async def test_owner_explicit_self_review_and_approval_audit_through_http(client, db_session, replacement):
    owner, _, target, _, invoice, notification, observed, _ = await seed(db_session, replacement=replacement)
    evidence = await record(db_session, owner, invoice, notification)
    stored = await db_session.get(HistoricalInvoiceEvidence, evidence['evidence_id'])
    original = stored.source_document, stored.source_sha256, stored.recorded_by_user_id
    data = request(evidence, target, invoice, notification, observed).model_dump(mode='json')
    root = f'/api/v1/fleet-invoice-exports/historical-invoices/{invoice.id}'
    verify = root + f'/evidence/{stored.id}/verify'
    assert (await client.post(verify, json=data, headers=headers(owner))).status_code == 403
    result = await client.post(verify, json={**data, 'owner_self_review': True}, headers=headers(owner))
    assert result.status_code == 200, result.text
    assert result.json()['verification_mode'] == 'owner_self_review'
    assert result.json()['verified_by_user_id'] == str(owner.id)
    await db_session.refresh(stored)
    assert (stored.source_document, stored.source_sha256, stored.recorded_by_user_id) == original
    assert stored.verification_mode == 'owner_self_review'
    assert not (await db_session.execute(select(HistoricalInvoiceMapping))).scalars().all()
    assert not (await db_session.execute(select(HistoricalInvoiceDecision))).scalars().all()
    assert (await client.post(verify, json={**data, 'owner_self_review': True}, headers=headers(owner))).status_code == 409
    decision = approval(evidence, target).model_dump(mode='json')
    result = await client.post(root+'/decisions', json=decision, headers=headers(owner))
    assert result.status_code == 200, result.text
    assert result.json()['evidence_verification_mode'] == 'owner_self_review'
    replay = await client.post(root+'/decisions', json=decision, headers=headers(owner))
    assert replay.json() == result.json()
    audit = (
        await db_session.execute(select(HistoricalInvoiceDecision).where(HistoricalInvoiceDecision.invoice_id == invoice.id))
    ).scalar_one()
    assert audit.actor_user_id == owner.id
    assert audit.evidence_verification_mode == 'owner_self_review'
    assert audit.evidence_sha256 == original[1]
    assert audit.evidence_identity_proof_sha256 == stored.identity_proof_sha256
    # Revocation stays available even after the original reviewer loses owner role.
    owner.role = UserRole.GARAGE_ADMIN
    await db_session.commit()
    new_owner = (await seed(db_session))[0]
    new_owner.tenant_id = invoice.tenant_id
    await db_session.commit()
    revoke = reviews.DecisionRequest(action='revoke', expected_version=1,
        idempotency_key=str(uuid4()), reason='Remove prior reviewed scope after identity drift')
    removed = await reviews.decide(invoice.id, revoke, Response(), db=db_session, user=new_owner)
    assert removed['evidence_verification_mode'] == 'owner_self_review'


@pytest.mark.asyncio
@pytest.mark.parametrize('role', [UserRole.GARAGE_ADMIN, UserRole.MECHANIC, UserRole.CUSTOMER, UserRole.SUPER_ADMIN])
async def test_nonowner_cannot_opt_into_self_review(client, db_session, role):
    owner, _, target, _, invoice, notification, observed, _ = await seed(db_session)
    evidence = await record(db_session, owner, invoice, notification)
    owner.role = role
    await db_session.commit()
    body = request(evidence, target, invoice, notification, observed, owner_self_review=True)
    url=f'/api/v1/fleet-invoice-exports/historical-invoices/{invoice.id}/evidence/{evidence["evidence_id"]}/verify'
    assert (await client.post(url, json=body.model_dump(mode='json'), headers=headers(owner))).status_code == 403
    stored=await db_session.get(HistoricalInvoiceEvidence,evidence['evidence_id'])
    assert stored.verified_at is None and stored.verification_mode is None


@pytest.mark.asyncio
async def test_owner_cannot_label_someone_elses_upload_as_self_review(db_session):
    owner, reviewer, target, _, invoice, notification, observed, _ = await seed(db_session)
    evidence=await record(db_session,reviewer,invoice,notification)
    body=request(evidence,target,invoice,notification,observed,owner_self_review=True)
    with pytest.raises(HTTPException) as error:
        await reviews.verify_evidence(invoice.id,evidence['evidence_id'],body,Response(),db=db_session,user=owner)
    assert error.value.status_code==422
    result=await reviews.verify_evidence(invoice.id,evidence['evidence_id'],body.model_copy(update={'owner_self_review':False}),Response(),db=db_session,user=owner)
    assert result['verification_mode']=='independent'


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['hash','tenant','uuid','alias','ambiguous_recipient','invoice','no_proof'])
async def test_self_review_preserves_identity_and_replacement_guards(db_session,failure):
    owner,_,target,other,invoice,notification,observed,_=await seed(db_session,replacement=True)
    evidence=await record(db_session,owner,invoice,notification)
    body=request(evidence,target,invoice,notification,observed,owner_self_review=True)
    if failure=='hash': body.source_sha256='0'*64
    elif failure=='tenant':
        other_owner,*_=await seed(db_session); owner=other_owner
    elif failure=='uuid': body.identity_proof.observed_invoice_id=uuid4()
    elif failure=='alias': body.observed_invoice_number='ETSINV-unproven'
    elif failure=='ambiguous_recipient': other.email=target.email;await db_session.commit()
    elif failure=='invoice': invoice.supersedes_invoice_id=None;await db_session.commit()
    elif failure=='no_proof': body.identity_proof=None
    with pytest.raises(HTTPException):
        await reviews.verify_evidence(invoice.id,evidence['evidence_id'],body,Response(),db=db_session,user=owner)
    stored=await db_session.get(HistoricalInvoiceEvidence,evidence['evidence_id'])
    assert stored.verified_at is None and stored.verification_mode is None
    assert not (await db_session.execute(select(HistoricalInvoiceMapping))).scalars().all()


@pytest.mark.asyncio
async def test_opt_in_does_not_accept_client_audit_or_inactive_identity(client,db_session):
    owner,_,target,_,invoice,notification,observed,_=await seed(db_session)
    evidence=await record(db_session,owner,invoice,notification)
    data=request(evidence,target,invoice,notification,observed,owner_self_review=True).model_dump(mode='json')
    url=f'/api/v1/fleet-invoice-exports/historical-invoices/{invoice.id}/evidence/{evidence["evidence_id"]}/verify'
    assert (await client.post(url,json=data)).status_code in (401,403)
    for field,value in [('verification_mode','owner_self_review'),('verified_by_user_id',str(uuid4()))]:
        assert (await client.post(url,json={**data,field:value},headers=headers(owner))).status_code==422
    owner.is_active=False;await db_session.commit()
    assert (await client.post(url,json=data,headers=headers(owner))).status_code in (401,403)


@pytest.mark.asyncio
async def test_approval_rechecks_self_review_audit_and_source_drift(db_session):
    owner,_,target,_,invoice,notification,observed,_=await seed(db_session)
    evidence=await record(db_session,owner,invoice,notification)
    body=request(evidence,target,invoice,notification,observed,owner_self_review=True)
    await reviews.verify_evidence(invoice.id,evidence['evidence_id'],body,Response(),db=db_session,user=owner)
    frozen=await db_session.get(HistoricalInvoiceEvidence,evidence['evidence_id'])
    frozen.verification_mode=None  # SQLite has no PG guards: approval must still fail closed.
    await db_session.commit()
    with pytest.raises(HTTPException) as error:
        await reviews.decide(invoice.id,approval(evidence,target),Response(),db=db_session,user=owner)
    assert error.value.status_code==409
    frozen.verification_mode='owner_self_review';notification.body+=' changed';await db_session.commit()
    with pytest.raises(HTTPException) as error:
        await reviews.decide(invoice.id,approval(evidence,target),Response(),db=db_session,user=owner)
    assert error.value.status_code==409


@pytest.mark.asyncio
@pytest.mark.parametrize('missing_actor',[False,True])
async def test_legacy_independent_mode_requires_recorded_reviewer(db_session,missing_actor):
    owner,reviewer,target,_,invoice,notification,observed,_=await seed(db_session)
    evidence=await record(db_session,owner,invoice,notification)
    await reviews.verify_evidence(invoice.id,evidence['evidence_id'],request(evidence,target,invoice,notification,observed),Response(),db=db_session,user=reviewer)
    frozen=await db_session.get(HistoricalInvoiceEvidence,evidence['evidence_id'])
    frozen.verification_mode=None  # Emulates a verified pre196 row, without a backfill.
    if missing_actor: frozen.verified_by_user_id=None
    await db_session.commit()
    if missing_actor:
        with pytest.raises(HTTPException) as error:
            await reviews.decide(invoice.id,approval(evidence,target),Response(),db=db_session,user=owner)
        assert error.value.status_code==409
        assert not (await db_session.execute(select(HistoricalInvoiceMapping))).scalars().all()
    else:
        result=await reviews.decide(invoice.id,approval(evidence,target),Response(),db=db_session,user=owner)
        assert result['evidence_verification_mode'] is None
