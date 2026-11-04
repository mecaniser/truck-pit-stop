from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.services import booking_payment_provider as provider


def setup(monkeypatch, name='quickbooks_payments'):
    tenant_id = uuid4()
    config = SimpleNamespace(tenant_id=tenant_id, version=3, selected_provider=name,
        provider_account_snapshot='realm-own' if name == 'quickbooks_payments' else 'acct_own',
        qbo_realm_snapshot='realm-own', is_active=True, readiness_state='ready', writer_strategy='dieselbridge')
    connection = SimpleNamespace(tenant_id=tenant_id, realm_id='realm-own', status='connected', scopes='com.intuit.quickbooks.payment',
        encrypted_access_token='encrypted-fixture', encrypted_refresh_token='encrypted-fixture',
        access_token_expires_at=datetime.now(timezone.utc)+timedelta(hours=1), refresh_token_expires_at=datetime.now(timezone.utc)+timedelta(days=1))
    monkeypatch.setattr(provider, 'settings', SimpleNamespace(BOOKING_PAYMENTS_ENABLED=True, BOOKING_PAYMENTS_APPROVED_TENANT_IDS='',
        ENVIRONMENT='test', QUICKBOOKS_PAYMENTS_ENVIRONMENT='sandbox', STRIPE_SECRET_KEY='sk_test_fixture',
        STRIPE_CONNECT_INVOICE_PAYMENTS_APPROVED=True, STRIPE_CONNECT_WEBHOOK_SECRET='fixture'))
    monkeypatch.setattr(provider, 'quickbooks_payments_enabled_for_tenant', lambda value: value == tenant_id)
    monkeypatch.setattr(provider.qbp, 'payments_base_url', lambda:'https://sandbox.api.intuit.com')
    tenant = SimpleNamespace(id=tenant_id,is_active=True,deleted_at=None,stripe_account_id='acct_own',stripe_onboarding_complete=True)
    db = SimpleNamespace(scalar=AsyncMock(side_effect=lambda query: tenant if 'FROM tenants' in str(query) else connection if 'quickbooks_connections' in str(query) else config))
    monkeypatch.setattr(provider,'provider_readiness',AsyncMock(return_value=SimpleNamespace(status='ready')))
    binding = provider.BookingProviderBinding(name, config.provider_account_snapshot, 3, 'sandbox', tenant_id)
    metadata = {'purpose':'booking_prepayment_v1','tenant_id':str(tenant_id),'customer_id':str(uuid4()),
        'appointment_id':str(uuid4()),'booking_payment_attempt_id':str(uuid4()),'price_snapshot_sha256':'a'*64}
    return db, tenant, config, connection, binding, metadata


@pytest.mark.asyncio
async def test_capability_is_read_only_and_requires_bound_ready_selected_provider(monkeypatch):
    db,tenant,config,connection,binding,_=setup(monkeypatch)
    result=await provider.booking_provider_capability(db,tenant)
    assert result.available and result.binding == binding
    assert result.token_url == 'https://sandbox.api.intuit.com/quickbooks/v4/payments/tokens'
    config.provider_account_snapshot='foreign-realm'
    assert not (await provider.booking_provider_capability(db,tenant)).available
    config.provider_account_snapshot='realm-own'
    connection.access_token_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    assert not (await provider.booking_provider_capability(db,tenant)).available


@pytest.mark.asyncio
async def test_production_requires_explicit_booking_admission_and_matching_environment(monkeypatch):
    db,tenant,_,_,_,_=setup(monkeypatch)
    provider.settings.ENVIRONMENT='production'
    assert not (await provider.booking_provider_capability(db,tenant)).available
    provider.settings.BOOKING_PAYMENTS_APPROVED_TENANT_IDS=str(tenant.id)
    assert not (await provider.booking_provider_capability(db,tenant)).available
    provider.settings.BOOKING_PAYMENTS_ENABLED=False
    assert not (await provider.booking_provider_capability(db,tenant)).available


@pytest.mark.asyncio
async def test_qbo_creates_once_then_retrieves_bound_charge_without_persisting_token(monkeypatch):
    db,_,_,connection,binding,metadata=setup(monkeypatch)
    full=provider._metadata(metadata,binding)
    charge=provider.qbp.QuickBooksCharge('charge-one','CAPTURED',Decimal('268.44'),
        {'id':'charge-one','status':'CAPTURED','amount':'268.44','currency':'USD','created':'2020-01-02T03:04:05Z','description':provider._description(full)})
    create=AsyncMock(return_value=charge);retrieve=AsyncMock(return_value=charge)
    monkeypatch.setattr(provider.qbp,'create_charge',create);monkeypatch.setattr(provider.qbp,'get_charge',retrieve)
    result=await provider.create_booking_payment(db,binding,amount_minor=26844,currency='usd',metadata=metadata,idempotency_key='stable-key',quickbooks_token='opaque-token')
    assert result.state=='succeeded' and result.amount_received_minor==26844 and result.provider_id=='charge-one'
    assert result.client_secret is None and result.metadata==full and result.amount_minor==26844
    assert create.await_count==retrieve.await_count==1
    assert create.call_args.kwargs['connection'] is connection
    assert create.call_args.kwargs['request_id']=='stable-key'
    assert 'opaque-token' not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('amount','1.00'),('currency','EUR'),('description','foreign booking'),('id','different-charge')])
async def test_qbo_mismatch_never_creates_verified_success(monkeypatch,field,value):
    db,_,_,_,binding,metadata=setup(monkeypatch)
    raw={'id':'charge-one','status':'CAPTURED','amount':'268.44','currency':'USD','created':'2020-01-02T03:04:05Z','description':provider._description(provider._metadata(metadata,binding))}
    original=provider.qbp.QuickBooksCharge('charge-one','CAPTURED',Decimal('268.44'),raw.copy())
    raw[field]=value
    verified=provider.qbp.QuickBooksCharge(raw['id'],'CAPTURED',Decimal(str(raw['amount'])),raw)
    monkeypatch.setattr(provider.qbp,'create_charge',AsyncMock(return_value=original));monkeypatch.setattr(provider.qbp,'get_charge',AsyncMock(return_value=verified))
    with pytest.raises(provider.BookingProviderError) as error:
        await provider.create_booking_payment(db,binding,amount_minor=26844,currency='usd',metadata=metadata,idempotency_key='stable',quickbooks_token='opaque')
    assert error.value.outcome_unknown


@pytest.mark.asyncio
async def test_unknown_qbo_result_is_not_retried_or_marked_paid(monkeypatch):
    db,_,_,_,binding,metadata=setup(monkeypatch)
    create=AsyncMock(side_effect=provider.qbp.QuickBooksPaymentError('provider timeout',outcome_unknown=True))
    monkeypatch.setattr(provider.qbp,'create_charge',create)
    with pytest.raises(provider.BookingProviderError) as error:
        await provider.create_booking_payment(db,binding,amount_minor=1000,currency='usd',metadata=metadata,idempotency_key='stable',quickbooks_token='opaque')
    assert error.value.outcome_unknown and create.await_count==1


@pytest.mark.asyncio
async def test_wrong_binding_and_metadata_fail_before_provider_io(monkeypatch):
    db,_,config,_,binding,metadata=setup(monkeypatch)
    create=AsyncMock();monkeypatch.setattr(provider.qbp,'create_charge',create)
    config.provider_account_snapshot='foreign'
    with pytest.raises(provider.BookingProviderError):
        await provider.create_booking_payment(db,binding,amount_minor=1000,currency='usd',metadata=metadata,idempotency_key='stable',quickbooks_token='opaque')
    config.provider_account_snapshot=binding.account_id;metadata['tenant_id']=str(uuid4())
    with pytest.raises(provider.BookingProviderError):
        await provider.create_booking_payment(db,binding,amount_minor=1000,currency='usd',metadata=metadata,idempotency_key='stable',quickbooks_token='opaque')
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_stripe_uses_exact_connected_account_key_and_metadata(monkeypatch):
    db,_,_,_,binding,metadata=setup(monkeypatch,'stripe_connect')
    full=provider._metadata(metadata,binding)
    intent={'id':'pi_one','status':'requires_payment_method','amount':1000,'amount_received':0,'currency':'usd',
        'livemode':False,'metadata':full,'latest_charge':None,'client_secret':'fixture-secret'}
    account=Mock(return_value={'charges_enabled':True,'payouts_enabled':True});create=Mock(return_value=intent)
    monkeypatch.setattr(provider.stripe.Account,'retrieve',account);monkeypatch.setattr(provider.stripe.PaymentIntent,'create',create)
    result=await provider.create_booking_payment(db,binding,amount_minor=1000,currency='usd',metadata=metadata,idempotency_key='stable')
    assert result.state=='requires_payment_method' and result.amount_received_minor==0
    assert create.call_args.kwargs['stripe_account']=='acct_own'
    assert create.call_args.kwargs['idempotency_key']=='stable'
    assert create.call_args.kwargs['metadata']==full
    assert create.call_args.kwargs['api_key']=='sk_test_fixture'


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('currency','eur'),('livemode',True),('metadata',{}),('amount_received',999)])
async def test_stripe_retrieval_rejects_forged_or_partial_evidence(monkeypatch,field,value):
    db,_,_,_,binding,metadata=setup(monkeypatch,'stripe_connect')
    intent={'id':'pi_one','status':'succeeded','amount':1000,'amount_received':1000,'currency':'usd','livemode':False,
        'metadata':provider._metadata(metadata,binding),'latest_charge':{'id':'ch_one','payment_intent':'pi_one','currency':'usd','captured':True,'paid':True,'amount_captured':1000,'livemode':False,'created':1577934245}}
    intent[field]=value
    retrieve=Mock(return_value=intent);monkeypatch.setattr(provider.stripe.PaymentIntent,'retrieve',retrieve)
    with pytest.raises(provider.BookingProviderError):
        await provider.retrieve_booking_payment(db,binding,'pi_one',expected_metadata=metadata)
    assert retrieve.call_args.kwargs['stripe_account']=='acct_own'


@pytest.mark.asyncio
async def test_expiry_cancels_only_bound_unpaid_stripe_intent(monkeypatch):
    db,_,_,_,binding,metadata=setup(monkeypatch,'stripe_connect')
    raw={'id':'pi_one','status':'requires_payment_method','amount':1000,'amount_received':0,'currency':'usd','livemode':False,
         'metadata':provider._metadata(metadata,binding),'latest_charge':None}
    monkeypatch.setattr(provider.stripe.PaymentIntent,'retrieve',Mock(return_value=raw))
    cancel=Mock(return_value={**raw,'status':'canceled'})
    monkeypatch.setattr(provider.stripe.PaymentIntent,'cancel',cancel)
    result=await provider.cancel_unpaid_booking_payment(db,binding,'pi_one',expected_metadata=metadata,idempotency_key='stable-expiry')
    assert result.state=='cancelled' and result.amount_received_minor==0
    assert cancel.call_args.kwargs['stripe_account']=='acct_own'
    assert cancel.call_args.kwargs['idempotency_key']=='stable-expiry'


@pytest.mark.asyncio
async def test_expiry_never_cancels_successful_or_processing_payment(monkeypatch):
    db,_,_,_,binding,metadata=setup(monkeypatch,'stripe_connect')
    raw={'id':'pi_one','status':'succeeded','amount':1000,'amount_received':1000,'currency':'usd','livemode':False,
         'metadata':provider._metadata(metadata,binding),'latest_charge':{'id':'ch_one','payment_intent':'pi_one','currency':'usd','captured':True,'paid':True,'amount_captured':1000,'livemode':False,'created':1577934245}}
    monkeypatch.setattr(provider.stripe.PaymentIntent,'retrieve',Mock(return_value=raw))
    cancel=Mock();monkeypatch.setattr(provider.stripe.PaymentIntent,'cancel',cancel)
    result=await provider.cancel_unpaid_booking_payment(db,binding,'pi_one',expected_metadata=metadata,idempotency_key='stable-expiry')
    assert result.state=='succeeded'
    cancel.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('provider_marks_unknown', [True, False])
async def test_known_charge_identity_survives_verification_timeout(monkeypatch, provider_marks_unknown):
    db,_,_,_,binding,metadata=setup(monkeypatch)
    charge=provider.qbp.QuickBooksCharge('charge-known','CAPTURED',Decimal('10.00'),{})
    monkeypatch.setattr(provider.qbp,'create_charge',AsyncMock(return_value=charge))
    monkeypatch.setattr(provider.qbp,'get_charge',AsyncMock(side_effect=provider.qbp.QuickBooksPaymentError('timeout',outcome_unknown=provider_marks_unknown)))
    with pytest.raises(provider.BookingProviderError) as error:
        await provider.create_booking_payment(db,binding,amount_minor=1000,currency='usd',metadata=metadata,idempotency_key='stable',quickbooks_token='opaque')
    assert error.value.outcome_unknown and error.value.provider_id=='charge-known'


@pytest.mark.asyncio
async def test_cancellation_with_money_received_is_not_clean_expiry_proof(monkeypatch):
    db,_,_,_,binding,metadata=setup(monkeypatch,'stripe_connect')
    raw={'id':'pi_one','status':'canceled','amount':1000,'amount_received':500,'currency':'usd','livemode':False,
         'metadata':provider._metadata(metadata,binding),'latest_charge':{'id':'ch_one','payment_intent':'pi_one','currency':'usd','captured':True,'paid':True,'amount_captured':1000,'livemode':False,'created':1577934245}}
    monkeypatch.setattr(provider.stripe.PaymentIntent,'retrieve',Mock(return_value=raw))
    with pytest.raises(provider.BookingProviderError) as error:
        await provider.cancel_unpaid_booking_payment(db,binding,'pi_one',expected_metadata=metadata,idempotency_key='stable-expiry')
    assert error.value.outcome_unknown


@pytest.mark.asyncio
async def test_test_runtime_cannot_offer_or_create_live_stripe_payments(monkeypatch):
    db,tenant,_,_,binding,metadata=setup(monkeypatch,'stripe_connect')
    provider.settings.STRIPE_SECRET_KEY='sk_live_fixture'
    provider.settings.BOOKING_PAYMENTS_APPROVED_TENANT_IDS=str(tenant.id)
    create=Mock();monkeypatch.setattr(provider.stripe.PaymentIntent,'create',create)
    assert not (await provider.booking_provider_capability(db,tenant)).available
    live=provider.BookingProviderBinding(binding.provider,binding.account_id,binding.configuration_version,'production',binding.tenant_id)
    with pytest.raises(provider.BookingProviderError):
        await provider.create_booking_payment(db,live,amount_minor=1000,currency='usd',metadata=metadata,idempotency_key='stable')
    create.assert_not_called()


@pytest.mark.asyncio
async def test_missing_received_amount_never_proves_cancelled_unpaid(monkeypatch):
    db,_,_,_,binding,metadata=setup(monkeypatch,'stripe_connect')
    raw={'id':'pi_one','status':'canceled','amount':1000,'currency':'usd','livemode':False,
         'metadata':provider._metadata(metadata,binding),'latest_charge':None}
    monkeypatch.setattr(provider.stripe.PaymentIntent,'retrieve',Mock(return_value=raw))
    with pytest.raises(provider.BookingProviderError) as error:
        await provider.cancel_unpaid_booking_payment(db,binding,'pi_one',expected_metadata=metadata,idempotency_key='stable-expiry')
    assert error.value.outcome_unknown


@pytest.mark.asyncio
async def test_qbo_receipt_time_comes_from_provider_not_late_retrieval(monkeypatch):
    db,_,_,_,binding,metadata=setup(monkeypatch)
    raw={'id':'charge-old','status':'CAPTURED','amount':'10.00','currency':'USD','created':'2020-01-02T03:04:05Z',
         'description':provider._description(provider._metadata(metadata,binding))}
    monkeypatch.setattr(provider.qbp,'get_charge',AsyncMock(return_value=provider.qbp.QuickBooksCharge('charge-old','CAPTURED',Decimal('10.00'),raw)))
    result=await provider.retrieve_booking_payment(db,binding,'charge-old',expected_metadata=metadata)
    assert result.paid_at == datetime(2020,1,2,3,4,5,tzinfo=timezone.utc)
    raw.pop('created')
    with pytest.raises(provider.BookingProviderError):
        await provider.retrieve_booking_payment(db,binding,'charge-old',expected_metadata=metadata)


@pytest.mark.asyncio
async def test_stripe_unknown_create_recovery_requires_original_idempotent_intent(monkeypatch):
    db,_,_,_,binding,metadata=setup(monkeypatch,'stripe_connect')
    full=provider._metadata(metadata,binding)
    intent={'id':'pi_canonical','status':'succeeded','amount':1000,'amount_received':1000,'currency':'usd','livemode':False,
        'metadata':full,'latest_charge':{'id':'ch_real','payment_intent':'pi_canonical','currency':'usd','captured':True,'paid':True,'amount_captured':1000,'livemode':False,'created':1577934245}}
    create=Mock(return_value=intent);retrieve=Mock(return_value=intent)
    monkeypatch.setattr(provider.stripe.PaymentIntent,'create',create);monkeypatch.setattr(provider.stripe.PaymentIntent,'retrieve',retrieve)
    args=dict(amount_minor=1000,currency='usd',metadata=metadata,idempotency_key='original-server-key',attempt_created_at=datetime.now(timezone.utc)-timedelta(minutes=1))
    result=await provider.recover_created_booking_payment(db,binding,expected_provider_id='pi_canonical',**args)
    assert result.state=='succeeded' and result.paid_at==datetime(2020,1,2,3,4,5,tzinfo=timezone.utc)
    assert create.call_args.kwargs['idempotency_key']=='original-server-key'
    assert create.call_args.kwargs['capture_method']=='automatic'
    assert create.call_args.kwargs['payment_method_types']==['card']
    before=retrieve.call_count
    with pytest.raises(provider.BookingProviderError):
        await provider.recover_created_booking_payment(db,binding,expected_provider_id='pi_other_copied_metadata',**args)
    assert retrieve.call_count==before
    create.reset_mock()
    args['attempt_created_at']=datetime.now(timezone.utc)-timedelta(hours=24)
    with pytest.raises(provider.BookingProviderError):
        await provider.recover_created_booking_payment(db,binding,expected_provider_id='pi_canonical',**args)
    create.assert_not_called()
