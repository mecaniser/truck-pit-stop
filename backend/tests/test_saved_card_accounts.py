"""Saved-card account isolation and stale-customer recovery; no real Stripe calls."""
from types import SimpleNamespace as NS
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.endpoints import payments
from app.core.dependencies import get_current_active_user, get_db
from app.db.models.customer import Customer
from app.db.models.tenant import Tenant
from app.db.models.user import UserRole


class Database:
    def __init__(self, customer, tenant):
        self.customer, self.tenant = customer, tenant
        self.commits = 0
        self.queries = []

    async def execute(self, query):
        self.queries.append(query)
        params = query.compile().params
        entity = query.column_descriptions[0]['entity']
        if entity is Customer:
            matches = params.get('id_1') == self.customer.id
            matches = matches and params.get('tenant_id_1', self.customer.tenant_id) == self.customer.tenant_id
            if 'customers.deleted_at IS NULL' in str(query):
                matches = matches and not self.customer.deleted_at
            value = self.customer if matches else None
        elif entity is Tenant:
            value = self.tenant if self.tenant.id in params.values() and self.tenant.is_active else None
        else:
            raise AssertionError(entity)
        return NS(scalar_one_or_none=lambda: value)

    async def commit(self):
        self.commits += 1


@pytest.fixture
def context(monkeypatch):
    tenant_id, customer_id = uuid4(), uuid4()
    customer = NS(id=customer_id, tenant_id=tenant_id, stripe_customer_id='cus_existing',
                  deleted_at=None, email='driver@example.com', first_name='Test', last_name='Driver', company_name=None)
    tenant = NS(id=tenant_id, is_active=True, stripe_account_id='acct_shop', stripe_onboarding_complete=True)
    user = NS(role=UserRole.CUSTOMER, customer_id=customer_id, tenant_id=tenant_id)
    db = Database(customer, tenant)
    app = FastAPI()
    app.include_router(payments.router, prefix='/payments')
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    # Every touched provider method is stubbed, even in authorization tests.
    mocks = {}
    for resource, methods in [('Customer', ['create', 'retrieve', 'modify']),
                              ('SetupIntent', ['create']), ('PaymentMethod', ['list', 'retrieve', 'detach'])]:
        for method in methods:
            mock = Mock(side_effect=AssertionError(f'Unexpected {resource}.{method}'))
            monkeypatch.setattr(getattr(payments.stripe, resource), method, mock)
            mocks[f'{resource}.{method}'] = mock
    return NS(app=app, user=user, db=db, customer=customer, tenant=tenant, mocks=mocks)


async def request(c, method, path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=c.app), base_url='http://test') as client:
        return await client.request(method, '/payments'+path)


def succeed(mock, value):
    mock.side_effect = None
    mock.return_value = value


@pytest.mark.asyncio
@pytest.mark.parametrize('reference', [None, 'cus_missing', 'cus_existing'])
async def test_setup_uses_connected_account_and_recovers_only_missing_reference(context, reference):
    c = context
    c.customer.stripe_customer_id = reference
    modify = c.mocks['Customer.modify']
    if reference == 'cus_missing':
        modify.side_effect = payments.stripe.error.InvalidRequestError('No such customer', 'customer', code='resource_missing')
    else:
        succeed(modify, {'id': reference})
    succeed(c.mocks['Customer.create'], {'id': 'cus_new'})
    succeed(c.mocks['SetupIntent.create'], NS(client_secret='synthetic_secret'))
    response = await request(c, 'POST', '/setup-intent')
    assert response.status_code == 200, response.text
    assert response.json() == {'client_secret': 'synthetic_secret', 'stripe_account_id': 'acct_shop'}
    expected = 'cus_existing' if reference == 'cus_existing' else 'cus_new'
    c.mocks['SetupIntent.create'].assert_called_once_with(customer=expected, stripe_account='acct_shop', payment_method_types=['card'])
    assert c.customer.stripe_customer_id == expected
    assert c.db.commits == (0 if reference == 'cus_existing' else 1)
    assert any(query._for_update_arg is not None for query in c.db.queries)
    assert c.mocks['Customer.create'].call_count == (0 if reference == 'cus_existing' else 1)
    if c.mocks['Customer.create'].called:
        assert c.mocks['Customer.create'].call_args.kwargs['stripe_account'] == 'acct_shop'


@pytest.mark.asyncio
async def test_other_provider_errors_do_not_replace_customer(context):
    c = context
    c.mocks['Customer.modify'].side_effect = payments.stripe.error.APIConnectionError('offline')
    with pytest.raises(payments.stripe.error.APIConnectionError):
        await request(c, 'POST', '/setup-intent')
    c.mocks['Customer.create'].assert_not_called()
    assert c.customer.stripe_customer_id == 'cus_existing'
    assert c.db.commits == 0


@pytest.mark.asyncio
async def test_config_is_read_only_and_returns_selected_account(context):
    response = await request(context, 'GET', '/methods/config')
    assert response.json() == {'stripe_account_id': 'acct_shop'}
    assert all(not mock.called for mock in context.mocks.values())
    assert context.db.commits == 0


@pytest.mark.asyncio
async def test_list_scopes_cards_and_default_to_same_account(context):
    c = context
    card = NS(id='pm_card', card=NS(brand='visa', last4='4242', exp_month=10, exp_year=2030))
    succeed(c.mocks['PaymentMethod.list'], NS(data=[card]))
    succeed(c.mocks['Customer.retrieve'], NS(get=lambda key: False, invoice_settings=NS(default_payment_method='pm_card')))
    response = await request(c, 'GET', '/methods')
    assert response.status_code == 200
    assert response.json()[0]['is_default'] is True
    c.mocks['PaymentMethod.list'].assert_called_once_with(customer='cus_existing', type='card', stripe_account='acct_shop')
    c.mocks['Customer.retrieve'].assert_called_once_with('cus_existing', stripe_account='acct_shop')
    assert c.db.commits == 0


@pytest.mark.asyncio
async def test_missing_customer_list_reports_error_without_repair_on_get(context):
    c = context
    c.mocks['PaymentMethod.list'].side_effect = payments.stripe.error.InvalidRequestError('missing', 'customer', code='resource_missing')
    response = await request(c, 'GET', '/methods')
    assert response.status_code == 409
    assert 'Add a card' in response.json()['detail']
    assert c.db.commits == 0
    c.mocks['Customer.create'].assert_not_called()


@pytest.mark.asyncio
async def test_no_reference_is_successful_empty_list_without_provider_call(context):
    context.customer.stripe_customer_id = None
    response = await request(context, 'GET', '/methods')
    assert response.status_code == 200 and response.json() == []
    assert all(not mock.called for mock in context.mocks.values())


@pytest.mark.asyncio
@pytest.mark.parametrize('path,method', [('/setup-intent','POST'),('/methods','GET'),('/methods/config','GET'),('/methods/pm_card','DELETE'),('/methods/pm_card/default','POST')])
@pytest.mark.parametrize('failure', ['role', 'customer', 'tenant', 'unconnected', 'onboarding', 'inactive', 'deleted'])
async def test_invalid_principals_and_unready_shops_never_call_stripe(context, path, method, failure):
    c = context
    expected = 409
    if failure == 'role':
        c.user.role = UserRole.GARAGE_ADMIN
        expected = 403
    elif failure == 'customer':
        c.user.customer_id = uuid4()
        expected = 404
    elif failure == 'tenant':
        c.user.tenant_id = uuid4()
        expected = 404
    elif failure == 'unconnected':
        c.tenant.stripe_account_id = None
    elif failure == 'onboarding':
        c.tenant.stripe_onboarding_complete = False
    elif failure == 'deleted':
        c.customer.deleted_at = 'retired'
        expected = 404
    else:
        c.tenant.is_active = False
    response = await request(c, method, path)
    assert response.status_code == expected, response.text
    assert all(not mock.called for mock in c.mocks.values())


@pytest.mark.asyncio
@pytest.mark.parametrize('action', ['delete', 'default'])
@pytest.mark.parametrize('owns_card', [True, False])
async def test_card_mutations_require_ownership_and_use_connected_account(context, action, owns_card):
    c = context
    succeed(c.mocks['PaymentMethod.retrieve'], NS(customer='cus_existing' if owns_card else 'cus_other'))
    succeed(c.mocks['PaymentMethod.detach'], {})
    succeed(c.mocks['Customer.modify'], {})
    path, method = ('/methods/pm_card', 'DELETE') if action == 'delete' else ('/methods/pm_card/default', 'POST')
    response = await request(c, method, path)
    assert response.status_code == (204 if owns_card else 403)
    c.mocks['PaymentMethod.retrieve'].assert_called_once_with('pm_card', stripe_account='acct_shop')
    if not owns_card:
        c.mocks['PaymentMethod.detach'].assert_not_called()
        c.mocks['Customer.modify'].assert_not_called()
    elif action == 'delete':
        c.mocks['PaymentMethod.detach'].assert_called_once_with('pm_card', stripe_account='acct_shop')
    else:
        c.mocks['Customer.modify'].assert_called_once_with('cus_existing', invoice_settings={'default_payment_method':'pm_card'}, stripe_account='acct_shop')
