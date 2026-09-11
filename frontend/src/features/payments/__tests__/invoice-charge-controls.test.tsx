import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import InvoiceTaxExemptionControl from '../InvoiceTaxExemptionControl'
import type { InvoiceSettlementSummary } from '../types'

const api = vi.hoisted(() => ({adjustInvoiceCharges:vi.fn()}))
vi.mock('../api', async original => ({...await original<typeof import('../api')>(),...api}))
const summary = ():InvoiceSettlementSummary => ({...DB048_SETTLEMENT_FIXTURES.unpaid.summary,charge_controls:{tax_exempt:false,shop_supplies_enabled:true,can_adjust:true,unavailable_reason:null,support_reference:null,original_shop_supplies_amount:'24.00',original_tax_amount:'88.44'}})
const editing=vi.fn()
function show(initial=summary()) {
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})
  function Harness() {
    const [value,setValue]=useState(initial)
    return <InvoiceTaxExemptionControl invoiceId={value.invoice_id} summary={value} onUpdated={setValue} onEditingChange={editing} />
  }
  return render(<QueryClientProvider client={client}><Harness /></QueryClientProvider>)
}
describe('Reversible invoice charge controls', () => {
  beforeEach(()=>{api.adjustInvoiceCharges.mockReset();editing.mockReset()})
  it('saves exemption then allows restoring tax and toggling supplies without changing original audit', async () => {
    let saved=summary()
    api.adjustInvoiceCharges.mockImplementation(async (_id,body)=>{
      saved={...saved,version:saved.version+1,charge_controls:{...saved.charge_controls!,tax_exempt:body.tax_exempt,shop_supplies_enabled:body.shop_supplies_enabled,support_reference:body.support_reference}}
      return saved
    })
    show()
    const tax=screen.getByRole('switch',{name:'Sales tax exemption'})
    await userEvent.click(tax)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(api.adjustInvoiceCharges).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button',{name:'Add certificate/reference'}))
    await userEvent.type(screen.getByRole('textbox'),' CERT-01 ')
    await userEvent.click(screen.getByRole('button',{name:'Update invoice'}))
    await waitFor(()=>expect(screen.queryByRole('button',{name:'Update invoice'})).not.toBeInTheDocument())
    expect(tax).toHaveAttribute('aria-checked','true')
    expect(tax).toBeEnabled()
    await userEvent.click(tax)
    await userEvent.click(screen.getByRole('switch',{name:'Shop supplies'}))
    await userEvent.click(screen.getByRole('button',{name:'Update invoice'}))
    expect(api.adjustInvoiceCharges).toHaveBeenLastCalledWith(saved.invoice_id,{expected_settlement_version:2,tax_exempt:false,shop_supplies_enabled:false,support_reference:null},expect.any(String))
    await waitFor(()=>expect(screen.getByRole('switch',{name:'Shop supplies'})).toBeEnabled())
    await userEvent.click(screen.getByRole('switch',{name:'Shop supplies'}))
    await userEvent.click(screen.getByRole('button',{name:'Update invoice'}))
    expect(api.adjustInvoiceCharges).toHaveBeenLastCalledWith(saved.invoice_id,expect.objectContaining({expected_settlement_version:3,tax_exempt:false,shop_supplies_enabled:true}),expect.any(String))
  })
  it('can discard a draft without sending an update', async () => {
    show()
    await userEvent.click(screen.getByRole('switch',{name:'Sales tax exemption'}))
    expect(editing).toHaveBeenLastCalledWith(true)
    await userEvent.click(screen.getByRole('button',{name:'Discard changes'}))
    expect(screen.getByRole('switch',{name:'Sales tax exemption'})).toHaveAttribute('aria-checked','false')
    expect(api.adjustInvoiceCharges).not.toHaveBeenCalled()
    expect(editing).toHaveBeenLastCalledWith(false)
  })
  it('freezes an uncertain request and retries its exact body/key', async () => {
    api.adjustInvoiceCharges.mockRejectedValue(new Error('Connection lost'))
    show()
    await userEvent.click(screen.getByRole('switch',{name:'Shop supplies'}))
    await userEvent.click(screen.getByRole('button',{name:'Update invoice'}))
    await screen.findByRole('alert')
    expect(screen.getByRole('switch',{name:'Shop supplies'})).toBeDisabled()
    expect(screen.queryByRole('button',{name:'Discard changes'})).not.toBeInTheDocument()
    const first=api.adjustInvoiceCharges.mock.calls[0]
    await userEvent.click(screen.getByRole('button',{name:'Retry update'}))
    expect(api.adjustInvoiceCharges.mock.calls[1]).toEqual(first)
  })
  it('allows retry after invoice contention but blocks stale versions', async () => {
    const failure=new AxiosError('Busy')
    failure.response={status:409,data:{error:{code:'invoice_busy',message:'Retry invoice lock.',retryable:true}},statusText:'Conflict',headers:{},config:{} as never}
    api.adjustInvoiceCharges.mockRejectedValue(failure)
    show()
    await userEvent.click(screen.getByRole('switch',{name:'Shop supplies'}))
    await userEvent.click(screen.getByRole('button',{name:'Update invoice'}))
    await screen.findByRole('alert')
    expect(screen.getByRole('button',{name:'Update invoice'})).toBeEnabled()
    failure.response.data={error:{code:'stale_settlement_version',message:'Refresh invoice.',current_version:2}}
    await userEvent.click(screen.getByRole('button',{name:'Update invoice'}))
    await screen.findByText('Refresh invoice.')
    expect(screen.getByRole('button',{name:'Update invoice'})).toBeDisabled()
  })
  it('keeps unsafe invoice controls visible but disabled', () => {
    const value=summary();value.charge_controls={...value.charge_controls!,tax_exempt:true,can_adjust:false,unavailable_reason:'Resolve the pending payment first.'}
    show(value)
    for(const control of screen.getAllByRole('switch')) expect(control).toBeDisabled()
    expect(screen.getByText('Resolve the pending payment first.')).toBeInTheDocument()
    expect(api.adjustInvoiceCharges).not.toHaveBeenCalled()
  })
})
