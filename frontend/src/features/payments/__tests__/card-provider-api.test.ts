import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DB048_PROVIDER_READINESS } from '@/test-fixtures/db048/settlements'

const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: mocks }))
import { updateCardProvider } from '../api'

describe('card provider update contract', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.get.mockResolvedValue({ data: {} })
    mocks.put.mockResolvedValue({ data: {} })
  })

  it('sends the server grant with idempotency and preserves gross accounting mappings', async () => {
    const mappings = {
      stripe_clearing_account: '1', qbp_clearing_account: '2',
      check_deposit_account: '3', zelle_ach_account: '4',
      card_fee_income_account: '5', processor_fee_expense_account: '6',
      sales_tax_liability_account: '7', checking_account: '8',
      qbo_card_fee_item_id: '11', qbo_card_fee_tax_code_id: '10',
    }
    await updateCardProvider('quickbooks_payments', {
      ...DB048_PROVIDER_READINESS, configuration_version: 4,
      writer_strategy: 'dieselbridge', mappings,
    }, 'request-key', 'server-grant')
    expect(mocks.put).toHaveBeenCalledWith('/payments/settings/card-provider', {
      selected_provider: 'quickbooks_payments', expected_version: 4,
      writer_strategy: 'dieselbridge', ...mappings,
    }, { headers: { 'Idempotency-Key': 'request-key', 'X-Step-Up-Authorization': 'server-grant' } })
  })
})
