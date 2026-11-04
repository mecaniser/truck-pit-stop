import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SettlementAccess } from '../types'

const requests = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: requests }))
import { fetchAllocations } from '../api'

describe('allocation resolution wire adapter', () => {
  beforeEach(() => vi.clearAllMocks())
  it.each<SettlementAccess>([{ kind: 'authenticated', invoiceId: 'fictional-invoice' }, { kind: 'guest', token: 'fictional-token' }])('preserves server-authorized recovery for $kind access', async access => {
    const resolution = { attempt_id: 'fictional-attempt', invoice_id: 'fictional-invoice', attempt_version: 1, settlement_version: 2, rail: 'zelle', requested_principal: '100.00', currency: 'USD', attempt_state: 'pending', checkout_status: 'transfer_reported', reservation_amount: '100.00', can_retry: false, actions: { cancel_unsent: true, check_provider_status: false, request_review: true, release_with_terminal_evidence: false, record_late_receipt: false }, block_reason: null, resolution_notice: null, review_status: 'none' }
    const wire = { data: { items: [{ id: 'fictional-attempt', attempt_id: 'fictional-attempt', rail: 'zelle', state: 'pending', principal_amount: '100.00', resolution }], next_cursor: null } }
    requests.get.mockResolvedValue(wire)
    requests.post.mockResolvedValue(wire)
    const result = await fetchAllocations(access)
    expect(result.items[0].resolution).toEqual(resolution)
    expect(result.items[0].resolution?.actions.cancel_unsent).toBe(true)
  })
  it('does not invent recovery capabilities for older responses', async () => {
    requests.get.mockResolvedValue({ data: { items: [{ id: 'old-attempt', rail: 'card', state: 'pending' }] } })
    expect((await fetchAllocations({ kind: 'authenticated', invoiceId: 'fictional-invoice' })).items[0].resolution).toBeNull()
  })
})
