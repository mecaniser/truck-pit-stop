"""Source exports recorded settlement facts without turning them into payment dates."""
from datetime import datetime,timezone
from decimal import Decimal as D
from types import SimpleNamespace as NS
from uuid import uuid4
import pytest
from app.services.fleet_settlement_projection import project_settlement


def fixture():
    inv=NS(id=uuid4(),tenant_id=uuid4(),subtotal=D('4844.38'),shop_supplies_amount=D('42.00'),service_fee_amount=D('171.02'),tax_amount=D('0'),discount_amount=D('0'),total_amount=D('5057.40'))
    settlement=NS(id=uuid4(),tenant_id=inv.tenant_id,invoice_id=inv.id,customer_id=uuid4(),state='paid',principal_total=D('4886.38'),max_card_fee=D('171.02'),max_card_fee_tax=D('0'),confirmed_principal=D('4886.38'),active_pending_principal=D('0'),unapplied_credit=D('0'),refund_pending=D('0'))
    p=NS(id=uuid4(),tenant_id=inv.tenant_id,invoice_id=inv.id,settlement_id=settlement.id,customer_id=settlement.customer_id,rail='cash',state='confirmed',principal_amount=D('4886.38'),received_amount=D('4886.38'),applied_principal_amount=D('4886.38'),applied_card_fee_amount=D('0'),applied_card_fee_tax_amount=D('0'),provider_charge_amount=D('4886.38'),unapplied_amount=D('0'),confirmed_at=datetime(2026,9,13,tzinfo=timezone.utc),deleted_at=None,manual_evidence={'secret':'PRIVATE'},provider_reference='PRIVATE')
    return inv,settlement,p


def test_cash_4886_keeps_quoted5057_and_max171_separate_without_inferred_date():
    inv,s,p=fixture();value=project_settlement(inv,s,[p])
    assert value['status']=='available' and value['principal_total']=='4886.38' and value['max_card_fee']=='171.02'
    assert value['payments'][0]['gross_received_amount']=='4886.38'
    assert value['payments'][0]['actual_paid_date'] is None and value['payments'][0]['paid_date_basis']=='unknown'
    assert value['payments'][0]['confirmed_at'].startswith('2026-09-13')
    assert inv.total_amount==D('5057.40') and 'PRIVATE' not in str(value)


def test_partial_card_preserves_fullprincipal_and_actual_gross():
    inv,s,p=fixture();s.state='partially_paid';s.confirmed_principal=D('200');p.rail='card';p.principal_amount=p.received_amount=p.applied_principal_amount=D('200');p.applied_card_fee_amount=D('7.00');p.provider_charge_amount=D('207.00')
    value=project_settlement(inv,s,[p]);assert value['status']=='available'
    assert value['principal_total']=='4886.38' and value['confirmed_principal']=='200.00'
    assert value['payments'][0]['received_amount']=='200.00' and value['payments'][0]['gross_received_amount']=='207.00'


@pytest.mark.parametrize('change', ['reversed','refunded','credit','pending_refund','inconsistent','foreign'])
def test_uncertain_or_reversed_evidence_requires_review(change):
    inv,s,p=fixture()
    if change in ('reversed','refunded'):p.state=change
    if change=='credit':s.unapplied_credit=D('1')
    if change=='pending_refund':s.refund_pending=D('1')
    if change=='inconsistent':s.confirmed_principal=D('4886.39')
    if change=='foreign':p.customer_id=uuid4()
    assert project_settlement(inv,s,[p])['status']=='review_required'


def test_payment_only_revision_does_not_rewrite_prior_object():
    inv,s,p=fixture();before=project_settlement(inv,s,[p]);p.state='reversed';s.confirmed_principal=D('0');s.state='unpaid';after=project_settlement(inv,s,[p])
    assert before['revision']!=after['revision'] and before['payments'][0]['state']=='confirmed'


def test_valid_cash_tax_is_preserved_for_consumer_policy_review_not_stripped():
    inv,s,p=fixture();inv.tax_amount=D('10');inv.total_amount+=D('10');s.principal_total+=D('10');s.confirmed_principal+=D('10');p.principal_amount+=D('10');p.applied_principal_amount+=D('10');p.received_amount+=D('10')
    value=project_settlement(inv,s,[p]);assert value['status']=='available' and value['principal_total']=='4896.38'
    assert inv.tax_amount==D('10')


def test_payment_bound_fails_complete_snapshot_instead_of_truncation():
    inv,s,p=fixture()
    with pytest.raises(ValueError,match='exceeds limit'):project_settlement(inv,s,[p]*1001)


def test_foreign_customer_fact_is_not_serialized_even_as_review():
    inv,s,p=fixture();p.customer_id=uuid4();p.principal_amount=D('1234.56');p.received_amount=D('1234.56')
    value=project_settlement(inv,s,[p]);assert value['status']=='review_required' and value['payments']==[]
    assert str(p.id) not in str(value) and '1234.56' not in str(value)


def test_invalid_source_state_is_not_exposed_as_free_text():
    inv,s,p=fixture();s.state='PRIVATE arbitrary source text'
    with pytest.raises(ValueError,match='Unsupported source settlement state'):project_settlement(inv,s,[p])


def test_pending_principal_and_overallocation_require_consistency():
    inv,s,p=fixture();s.active_pending_principal=D('1')
    value=project_settlement(inv,s,[p]);assert value['status']=='review_required'
    assert 'source_pending_principal_mismatch' in value['review_reasons'] and 'source_principal_overallocated' in value['review_reasons']
