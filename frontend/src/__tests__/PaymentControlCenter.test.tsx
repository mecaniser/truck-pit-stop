import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ default: apiMocks }))
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

import PaymentControlCenter from '@/features/platform-admin/PaymentControlCenter'

const stripeOverview = {
  platform_fee_default_percent: '2.00',
  configuration: {
    secret_key_configured: true,
    publishable_key_configured: true,
    platform_webhook_configured: true,
    connect_webhook_configured: true,
    mode: 'test',
    connect_webhook_url: 'https://example.test/connect',
    platform_webhook_url: 'https://example.test/platform',
  },
  webhook_health: { merchants_with_recent_delivery: 0, merchants_with_delivery_error: 0, last_payment_error_at: null },
  merchant_summary: { active: 1, not_started: 0, incomplete: 0, under_review: 0, restricted: 0, unreachable: 0 },
  merchants: [{
    tenant_id: 'tenant-1', tenant_name: 'Truck Pit Stop', owner_email: 'owner@example.test',
    account_id: 'acct_123', status: 'active', charges_enabled: true, payouts_enabled: true,
    requirements: [], platform_fee_percent: null, uses_default_fee: true,
    last_webhook_at: null, last_webhook_event: null, last_webhook_error: null,
  }],
  alerts: [],
}

const quickBooksOverview = {
  configuration: {
    client_id_configured: true, client_secret_configured: true, redirect_uri_configured: true,
    token_encryption_configured: true, webhook_verifier_configured: true,
    accounting_environment: 'sandbox', payments_environment: 'sandbox',
    accounting_environment_valid: true, payments_environment_valid: true,
    webhook_url: 'https://example.test/qb',
  },
  merchant_summary: { active: 0, not_connected: 0, accounting_only: 0, refresh_required: 0, reconnect_required: 0, attention: 0 },
  webhook_health: { merchants_with_recent_delivery: 0, merchants_with_delivery_error: 0, merchants_with_cdc_error: 0 },
  merchants: [],
  alerts: [],
}

describe('PaymentControlCenter provider reset step-up', () => {
  beforeEach(() => {
    apiMocks.get.mockReset()
    apiMocks.post.mockReset()
    apiMocks.patch.mockReset()
    apiMocks.get.mockImplementation((path: string) => Promise.resolve({ data: ({
      '/admin/payments-control/overview': stripeOverview,
      '/admin/payments-control/ledger': { entries: [], totals: { volume: '0', platform_fees: '0' } },
      '/admin/payments-control/quickbooks/overview': quickBooksOverview,
      '/admin/payments-control/quickbooks/ledger': { entries: [], totals: { volume: '0', refunded: '0', unreconciled: 0 } },
    } as Record<string, unknown>)[path] }))
    apiMocks.post.mockImplementation((path: string) => Promise.resolve({ data:
      path === '/auth/step-up-grants'
        ? { grant_token: 'target-bound-grant', scope: 'platform.payment_sources.stripe.reset', expires_at: new Date(Date.now() + 120000).toISOString(), one_time: true }
        : { reset: true },
    }))
  })

  it('requests a target-bound destructive grant and sends it on Stripe reset', async () => {
    const user = userEvent.setup()
    render(<PaymentControlCenter />)

    await user.click(await screen.findByRole('button', { name: 'Reset Stripe' }))
    const dialog = await screen.findByRole('alertdialog', { name: 'Reset Stripe connection?' })
    await user.type(within(dialog).getByLabelText('Your current password'), 'fresh-password')
    await user.click(within(dialog).getByRole('button', { name: 'Verify and reset Stripe' }))

    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith('/auth/step-up-grants', {
        password: 'fresh-password',
        scope: 'platform.payment_sources.stripe.reset',
        target_tenant_id: 'tenant-1',
      })
      expect(apiMocks.post).toHaveBeenCalledWith(
        '/admin/payments-control/tenants/tenant-1/reset-stripe-connection',
        undefined,
        { headers: { 'X-Step-Up-Authorization': 'target-bound-grant' } },
      )
    })
  })
})
