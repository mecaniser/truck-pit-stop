import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import PendingManualPaymentPanel from '../PendingManualPaymentPanel'
import type { PaymentAllocation } from '../types'

const api = vi.hoisted(() => ({confirmPaymentAttempt:vi.fn()}))
vi.mock('../api', async original => ({...await original<typeof import('../api')>(),...api}))
const fixture = DB048_SETTLEMENT_FIXTURES.pendingZelle500
const summary = {...fixture.summary,allowed_actions:{...fixture.summary.allowed_actions,confirm_manual:true}}
const allocation = (): PaymentAllocation => ({...fixture.allocations[0],attempt_version:3,reference_number:null,sender_evidence:{sender_name:'Dispatcher',sender_email:'dispatch@example.com',sender_phone:'5551234567',reference_number:'PORTAL-ZELLE-500',note:'Sent from fleet account'}})
function show(item = allocation()) {
  const client = new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})
  const ui = (value: PaymentAllocation) => <QueryClientProvider client={client}><PendingManualPaymentPanel invoiceId={summary.invoice_id} summary={summary} allocations={[value]} onUpdated={vi.fn()} /></QueryClientProvider>
  const rendered = render(ui(item))
  return {...rendered,refresh:(value:PaymentAllocation)=>rendered.rerender(ui(value))}
}
describe('Portal Zelle submission review', () => {
  beforeEach(()=>api.confirmPaymentAttempt.mockReset())
  it('prefills submitted details without recording money and confirms the same attempt', async () => {
    const item=allocation()
    api.confirmPaymentAttempt.mockResolvedValue({settlement:summary})
    show(item)
    expect(screen.getByLabelText('Transaction reference')).toHaveValue('PORTAL-ZELLE-500')
    expect(screen.getByLabelText(/Verification note/)).toHaveValue('Sent from fleet account')
    expect(screen.getByText(/Submitted sender: Dispatcher.*dispatch@example.com.*5551234567/)).toBeInTheDocument()
    expect(api.confirmPaymentAttempt).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button',{name:'Confirm Zelle received'}))
    expect(api.confirmPaymentAttempt).toHaveBeenCalledWith({kind:'authenticated',invoiceId:summary.invoice_id},item.attempt_id,expect.objectContaining({expected_attempt_version:3,received_amount:'500.00',reference:'PORTAL-ZELLE-500',note:'Sent from fleet account'}),expect.any(String))
  })
  it('does not invent a reference when only sender contact was supplied', () => {
    show({...allocation(),sender_evidence:{sender_email:'dispatch@example.com'}})
    expect(screen.getByLabelText('Transaction reference')).toHaveValue('')
    expect(screen.getByRole('button',{name:'Confirm Zelle received'})).toBeDisabled()
  })
  it('prefers a verified reference and preserves staff edits across same-attempt refresh', async () => {
    const item={...allocation(),reference_number:'VERIFIED-500'}
    const view=show(item)
    expect(screen.getByLabelText('Transaction reference')).toHaveValue('VERIFIED-500')
    await userEvent.clear(screen.getByLabelText(/Verification note/))
    await userEvent.type(screen.getByLabelText(/Verification note/),'Checked bank receipt')
    view.refresh({...item,attempt_version:4})
    expect(screen.getByLabelText(/Verification note/)).toHaveValue('Checked bank receipt')
    expect(api.confirmPaymentAttempt).not.toHaveBeenCalled()
  })
})
