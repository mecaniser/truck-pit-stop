"""Customer assertions and read-only staff review of exact Zelle requests."""
from decimal import Decimal
from sqlalchemy import select
from app.core.config import settings
from app.db.models.customer import Customer
from app.services.invoice_identity import load_invoice_display_number
from app.services.pending_zelle_staff_notification_service import enqueue_staff_sms

async def enqueue_report_notice(db, *, invoice, tenant, customer_id, attempt):
    """Queue eligible SMS in the report transaction; no transport or email IO."""
    if not settings.SMS_AUTOMATION_OUTBOX_ENABLED or not tenant.sms_enabled or not tenant.messaging_enabled:
        return
    customer=await db.scalar(select(Customer).where(Customer.id==customer_id,
        Customer.tenant_id==tenant.id,Customer.deleted_at.is_(None)))
    display=await load_invoice_display_number(db,invoice,tenant)
    name=(' '.join(filter(None,[customer.first_name,customer.last_name])) or customer.company_name) if customer else 'Customer'
    body=(f'{name} reported a Zelle transfer of ${Decimal(attempt.principal_amount):,.2f} '
          f'for invoice {display}. This is a customer report, not verified receipt. '
          'Review the exact request in the shop payment queue.')
    await enqueue_staff_sms(db,tenant_id=tenant.id,
        domain_event_id=f'invoice:{invoice.id}:zelle-attempt-report:{attempt.id}',
        template_name='pending_zelle_staff_submit_sms',body=body,skip_unconsented=True)


def _review_staff(actor):
    from app.core.dependencies import user_has_permission
    from app.db.models.user import UserRole
    return actor.role in {UserRole.GARAGE_OWNER,UserRole.GARAGE_ADMIN} and user_has_permission(actor,'payments')


def _queue_cursor(tenant_id,row):
    import base64,json
    return base64.urlsafe_b64encode(json.dumps([str(tenant_id),row.created_at.isoformat(),row.kind,str(row.row_id)],separators=(',',':')).encode()).decode().rstrip('=')


def _parse_cursor(raw,tenant_id,include_cards=False):
    import base64,json
    from datetime import datetime
    from uuid import UUID
    from app.services.invoice_settlement_service import SettlementDomainError
    try:
        if not raw or len(raw)>1024:raise ValueError()
        scope,stamp,kind,identity=json.loads(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)))
        if scope!=str(tenant_id) or kind not in ({'canonical_card_attempt','canonical_efs_attempt','canonical_zelle_attempt','legacy_zelle_submission'} if include_cards else {'canonical_zelle_attempt','legacy_zelle_submission'}):raise ValueError()
        return datetime.fromisoformat(stamp),kind,UUID(identity)
    except (ValueError,TypeError,UnicodeError,base64.binascii.Error):
        raise SettlementDomainError('invalid_cursor','The payment review cursor is invalid.',status_code=422) from None


async def review_queue(db,actor,*,cursor=None,limit=50,include_cards=False):
    """Read existing requests, including unverified history; never backfill."""
    from contextlib import nullcontext
    from datetime import datetime,timezone
    from sqlalchemy import and_,or_,literal,union_all,case
    from app.db.models.invoice import Invoice,InvoiceStatus
    from app.db.models.invoice_settlement import InvoicePaymentAttempt,InvoiceSettlement
    from app.services.invoice_settlement_service import SettlementDomainError,current_zelle_attempt_matches
    from app.api.v1.endpoints.invoice_settlements import invoice_for_principal
    if not _review_staff(actor):raise SettlementDomainError('payment_review_forbidden','Payment review access is required.',status_code=403)
    if not 1<=limit<=100:raise SettlementDomainError('invalid_limit','Choose a review page size between1 and100.',status_code=422)
    tenant_id=actor.tenant_id
    with getattr(db,'no_autoflush',nullcontext()):
        invoice_scope=[Invoice.tenant_id==tenant_id,Invoice.deleted_at.is_(None),Invoice.voided_at.is_(None),Invoice.status.not_in([InvoiceStatus.PAID,InvoiceStatus.CANCELLED])]
        canonical=select(case((InvoicePaymentAttempt.rail=='card',literal('canonical_card_attempt')),(InvoicePaymentAttempt.source=='customer_efs_v1',literal('canonical_efs_attempt')),else_=literal('canonical_zelle_attempt')).label('kind'),InvoicePaymentAttempt.id.label('row_id'),InvoicePaymentAttempt.created_at.label('created_at'),Invoice.id.label('invoice_id')).join(Invoice,and_(Invoice.id==InvoicePaymentAttempt.invoice_id,Invoice.tenant_id==InvoicePaymentAttempt.tenant_id)).where(*invoice_scope,InvoicePaymentAttempt.tenant_id==tenant_id,(or_(InvoicePaymentAttempt.rail.in_(['zelle','card']),and_(InvoicePaymentAttempt.rail=='fleet_payment',InvoicePaymentAttempt.source=='customer_efs_v1')) if include_cards else InvoicePaymentAttempt.rail=='zelle'),InvoicePaymentAttempt.state=='pending',InvoicePaymentAttempt.deleted_at.is_(None))
        legacy=select(literal('legacy_zelle_submission').label('kind'),Invoice.id.label('row_id'),Invoice.zelle_pending_submitted_at.label('created_at'),Invoice.id.label('invoice_id')).where(*invoice_scope,Invoice.zelle_pending_submitted_at.is_not(None))
        cohort=union_all(canonical,legacy).subquery()
        query=select(cohort)
        if cursor:
            stamp,kind,identity=_parse_cursor(cursor,tenant_id,include_cards)
            query=query.where(or_(cohort.c.created_at<stamp,and_(cohort.c.created_at==stamp,cohort.c.kind<kind),and_(cohort.c.created_at==stamp,cohort.c.kind==kind,cohort.c.row_id<identity)))
        raw=(await db.execute(query.order_by(cohort.c.created_at.desc(),cohort.c.kind.desc(),cohort.c.row_id.desc()).limit(limit+1))).all()
        more=len(raw)>limit;selected=raw[:limit];rows=[];contexts={}
        identities=[item.row_id for item in selected if item.kind in {'canonical_card_attempt','canonical_zelle_attempt','canonical_efs_attempt'}]
        attempts={item.id:item for item in (await db.scalars(select(InvoicePaymentAttempt).where(InvoicePaymentAttempt.tenant_id==tenant_id,InvoicePaymentAttempt.id.in_(identities)))).all()} if identities else {}
        for item in selected:
            if item.invoice_id not in contexts:
                try:
                    invoice,tenant,customer_id=await invoice_for_principal(db,item.invoice_id,actor)
                    customer=await db.scalar(select(Customer).where(Customer.tenant_id==tenant_id,Customer.id==customer_id,Customer.deleted_at.is_(None)))
                    settlement=await db.scalar(select(InvoiceSettlement).where(InvoiceSettlement.tenant_id==tenant_id,InvoiceSettlement.invoice_id==invoice.id,InvoiceSettlement.customer_id==customer_id,InvoiceSettlement.deleted_at.is_(None)))
                    confirmable=bool(customer)
                    if invoice.accounting_policy=='source_collection_hold':
                        from app.services.source_debt_handoff import invoice_handoff
                        try:await invoice_handoff(db,invoice,require_active=True)
                        except SettlementDomainError:confirmable=False
                    contexts[item.invoice_id]=(invoice,tenant,customer_id,customer,settlement,confirmable)
                except SettlementDomainError:
                    contexts[item.invoice_id]=None
            context=contexts[item.invoice_id]
            if context is None:continue
            invoice,tenant,customer_id,customer,settlement,confirmable=context
            if not customer:continue
            attempt=attempts.get(item.row_id) if item.kind in {'canonical_card_attempt','canonical_zelle_attempt','canonical_efs_attempt'} else None
            report_status='legacy_report';reported_at=invoice.zelle_pending_submitted_at
            if attempt:
                if not settlement or attempt.settlement_id!=settlement.id or attempt.customer_id!=customer_id:continue
                evidence=attempt.manual_evidence or {};reported_at=None;report_status='unverified_request'
                if evidence.get('transfer_sent_confirmed') is True and evidence.get('reported_at'):
                    try:reported_at=datetime.fromisoformat(evidence['reported_at']);report_status='explicit_report'
                    except (TypeError,ValueError):pass
                elif current_zelle_attempt_matches(invoice=invoice,settlement=settlement,attempt=attempt):reported_at=invoice.zelle_pending_submitted_at;report_status='legacy_report'
                expires=attempt.expires_at
                if expires and expires.replace(tzinfo=expires.tzinfo or timezone.utc)<=datetime.now(timezone.utc):confirmable=False
                principal=attempt.principal_amount
            else:
                # Prefer the exact matching compatibility attempt without ever
                # copying its state onto mutable legacy full-invoice flags.
                candidates=(await db.scalars(select(InvoicePaymentAttempt).where(InvoicePaymentAttempt.tenant_id==tenant_id,InvoicePaymentAttempt.invoice_id==invoice.id,InvoicePaymentAttempt.rail=='zelle',InvoicePaymentAttempt.deleted_at.is_(None)))).all()
                matched=None
                if settlement:
                    for candidate in candidates:
                        marker=(candidate.manual_evidence or {}).get('compatibility_submitted_at')
                        try:
                            stamp=datetime.fromisoformat(marker) if marker else None
                            same_time=bool(stamp and stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).astimezone(timezone.utc)==invoice.zelle_pending_submitted_at.replace(tzinfo=invoice.zelle_pending_submitted_at.tzinfo or timezone.utc).astimezone(timezone.utc))
                        except (TypeError,ValueError):same_time=False
                        if same_time and candidate.settlement_id==settlement.id and candidate.customer_id==customer_id:matched=candidate;break
                if matched and matched.state=='pending':continue
                if matched:
                    attempt=matched;attempts[matched.id]=matched;confirmable=False;reported_at=invoice.zelle_pending_submitted_at
                principal=attempt.principal_amount if attempt else invoice.total_amount-(invoice.service_fee_amount or Decimal('0'))
            display=await load_invoice_display_number(db,invoice,tenant)
            name=customer.company_name or ' '.join(filter(None,[customer.first_name,customer.last_name]))
            rows.append({'kind':'canonical_zelle_attempt' if attempt else item.kind,'invoice_id':str(invoice.id),'repair_order_id':str(invoice.repair_order_id),'display_invoice_number':display,'customer_id':str(customer_id),'customer_display_name':name,'principal_amount':f'{Decimal(principal):.2f}','attempt_id':str(attempt.id) if attempt else None,'settlement_id':str(settlement.id) if settlement else None,'settlement_version':settlement.version if settlement else None,'created_at':item.created_at,'reported_at':reported_at,'report_status':report_status,'review_mode':'canonical_attempt' if attempt else 'legacy_invoice','can_confirm':confirmable})
        if include_cards:
            from app.services.payment_attempt_resolution import project_many
            projected=await project_many(db,list(attempts.values()),actor=actor,audience='staff')
            from app.services.customer_efs import summaries
            efss=await summaries(db,list(attempts.values()),actor=actor,audience='staff')
            for row in rows:
                attempt=attempts.get(__import__('uuid').UUID(row['attempt_id'])) if row['attempt_id'] else None
                row['rail']=attempt.rail if attempt else 'zelle'
                row['kind']='canonical_card_attempt' if attempt and attempt.rail=='card' else row['kind']
                row['resolution']=projected.get(attempt.id) if attempt else None
                row['efs']=efss.get(attempt.id) if attempt else None
                if attempt and attempt.source=='customer_efs_v1':row['kind']='canonical_efs_attempt';row['provider_label']='EFS';row['can_confirm']=False
                if attempt and attempt.rail=='card':row['can_confirm']=False
        return {'rows':rows,'next_cursor':_queue_cursor(tenant_id,selected[-1]) if more and selected else None}


async def broadcast_report_invalidation(db, *, invoice, customer_id):
    """Best-effort cache invalidation after commit, bound to the billed payer."""
    from app.db.models.repair_order import RepairOrder
    from app.core.websocket import broadcast_repair_order_update
    from app.core.logging import get_logger
    try:
        order=await db.scalar(select(RepairOrder).where(RepairOrder.id==invoice.repair_order_id,RepairOrder.tenant_id==invoice.tenant_id))
        if order is None:return
        await broadcast_repair_order_update(tenant_id=str(invoice.tenant_id),customer_id=str(customer_id),order_id=str(order.id),order_number=order.order_number,status=order.status.value,updated_at=order.updated_at.isoformat() if order.updated_at else None)
    except Exception:
        get_logger(__name__).warning('zelle_report_invalidation_failed',invoice_id=str(invoice.id))


async def compatibility_report_intent(db, *, invoice, subject_type, subject_id, amount, idempotency_header):
    """Resolve omitted amounts from the durable original command, never a changed balance.

    Headerless legacy clients have one stable command per invoice and subject.
    New independent partial reports must use the canonical explicit-amount API.
    """
    from app.db.models.invoice_settlement import InvoicePaymentAttempt
    from app.services.invoice_settlement_service import money, SettlementDomainError
    key=(idempotency_header or f"compat:{subject_type}-zelle:{invoice.id}:{subject_id}").strip()
    if not key or len(key)>255:
        raise SettlementDomainError('idempotency_key_invalid','Invalid Idempotency-Key',status_code=422)
    existing=await db.scalar(select(InvoicePaymentAttempt).where(
        InvoicePaymentAttempt.tenant_id==invoice.tenant_id,
        InvoicePaymentAttempt.idempotency_key==key))
    if existing is None and idempotency_header is None:
        # Prior adapters included the then-current amount in their fallback key.
        # Resolve an unambiguous historical command before considering new capacity.
        historical=(await db.scalars(select(InvoicePaymentAttempt).where(
            InvoicePaymentAttempt.tenant_id==invoice.tenant_id,
            InvoicePaymentAttempt.invoice_id==invoice.id,
            InvoicePaymentAttempt.subject_type==subject_type,
            InvoicePaymentAttempt.subject_id==(subject_id if subject_type=='customer' else None),
            InvoicePaymentAttempt.source=='compatibility_adapter',
            InvoicePaymentAttempt.rail=='zelle',
            InvoicePaymentAttempt.idempotency_key.startswith(key+':'),
        ))).all()
        if len(historical)>1:
            raise SettlementDomainError('idempotency_conflict','Multiple earlier transfer reports exist. Review their status before reporting another transfer.')
        if historical:
            existing=historical[0]
            key=existing.idempotency_key
    if existing is not None:
        if (existing.invoice_id!=invoice.id or existing.subject_type!=subject_type
            or existing.subject_id!=(subject_id if subject_type=='customer' else None)
            or existing.source!='compatibility_adapter' or existing.rail!='zelle'):
            raise SettlementDomainError('idempotency_conflict','This idempotency key was used for a different request.')
        if amount is None:amount=existing.principal_amount
    return key, money(amount) if amount is not None else None
