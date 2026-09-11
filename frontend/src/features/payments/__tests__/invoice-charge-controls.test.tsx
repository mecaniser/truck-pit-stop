import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
    return <><InvoiceTaxExemptionControl invoiceId={value.invoice_id} summary={value} onUpdated={setValue} onEditingChange={editing} /><output>{value.principal_total}</output></>
  }
  return render(<QueryClientProvider client={client}><Harness /></QueryClientProvider>)
}
function successfulSaves() {
  let saved=summary()
  api.adjustInvoiceCharges.mockImplementation(async (_id,body)=>{
    saved={...saved,version:saved.version+1,charge_controls:{...saved.charge_controls!,tax_exempt:body.tax_exempt,shop_supplies_enabled:body.shop_supplies_enabled,support_reference:body.support_reference}}
    return saved
  })
}
const failure = (code:string, status=409, current_version?:number) => {
  const error=new AxiosError(code)
  error.response={status,data:{error:{code,message:code,current_version}},statusText:'Error',headers:{},config:{} as never}
  return error
}
describe('Immediate invoice charge toggles', () => {
  beforeEach(()=>{api.adjustInvoiceCharges.mockReset();editing.mockReset()})
  it('saves and reverses each toggle with one click and no secondary confirmation', async () => {
    successfulSaves()
    show()
    const tax=screen.getByRole('switch',{name:'Sales tax'})
    await userEvent.click(tax)
    await waitFor(()=>expect(tax).toBeEnabled())
    expect(api.adjustInvoiceCharges).toHaveBeenLastCalledWith(summary().invoice_id,{expected_settlement_version:1,tax_exempt:true,shop_supplies_enabled:true,support_reference:null},expect.any(String))
    expect(tax).toHaveAttribute('aria-checked','false')
    expect(screen.queryByRole('button',{name:'Update invoice'})).not.toBeInTheDocument()
    expect(screen.queryByRole('button',{name:'Discard changes'})).not.toBeInTheDocument()
    await userEvent.click(tax)
    await waitFor(()=>expect(tax).toBeEnabled())
    expect(api.adjustInvoiceCharges.mock.calls[1][1]).toEqual({expected_settlement_version:2,tax_exempt:false,shop_supplies_enabled:true,support_reference:null})
    const supplies=screen.getByRole('switch',{name:'Shop supplies'})
    await userEvent.click(supplies)
    await waitFor(()=>expect(supplies).toBeEnabled())
    expect(supplies).toHaveAttribute('aria-checked','false')
    await userEvent.click(supplies)
    await waitFor(()=>expect(supplies).toBeEnabled())
    expect(api.adjustInvoiceCharges.mock.calls[3][1]).toEqual({expected_settlement_version:4,tax_exempt:false,shop_supplies_enabled:true,support_reference:null})
    expect(editing).toHaveBeenLastCalledWith(false)
  })
  it('serializes rapid clicks and does not change money before server confirmation', async () => {
    let resolve!:(next:InvoiceSettlementSummary)=>void
    api.adjustInvoiceCharges.mockReturnValue(new Promise<InvoiceSettlementSummary>(done=>{resolve=done}))
    show()
    const supplies=screen.getByRole('switch',{name:'Shop supplies'})
    fireEvent.click(supplies);fireEvent.click(supplies)
    expect(api.adjustInvoiceCharges).toHaveBeenCalledTimes(1)
    for(const control of screen.getAllByRole('switch')) expect(control).toBeDisabled()
    expect(screen.getByText('Updating invoice…')).toBeInTheDocument()
    expect(editing).toHaveBeenLastCalledWith(true)
    expect(screen.getByText(summary().principal_total)).toBeInTheDocument()
    await act(async()=>resolve({...summary(),version:2,principal_total:'810.00',charge_controls:{...summary().charge_controls!,shop_supplies_enabled:false}}))
    expect(screen.getByText('810.00')).toBeInTheDocument()
    expect(supplies).toBeEnabled()
  })
  it('keeps certificate optional and saves its trimmed reference on blur or Enter', async () => {
    successfulSaves()
    show()
    await userEvent.click(screen.getByRole('switch',{name:'Sales tax'}))
    await waitFor(()=>expect(screen.getByRole('switch',{name:'Sales tax'})).toBeEnabled())
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button',{name:'Add certificate/reference'}))
    const input=screen.getByRole('textbox')
    await userEvent.type(input,' CERT-01 ')
    expect(api.adjustInvoiceCharges).toHaveBeenCalledTimes(1)
    await userEvent.tab()
    await waitFor(()=>expect(api.adjustInvoiceCharges).toHaveBeenCalledTimes(2))
    expect(api.adjustInvoiceCharges.mock.calls[1][1].support_reference).toBe('CERT-01')
    await waitFor(()=>expect(input).toBeEnabled())
    await userEvent.clear(input)
    await userEvent.type(input,'CERT-02{Enter}')
    await waitFor(()=>expect(api.adjustInvoiceCharges).toHaveBeenCalledTimes(3))
    expect(api.adjustInvoiceCharges.mock.calls[2][1].support_reference).toBe('CERT-02')
  })
  it('combines a reference edit and direct toggle click instead of creating competing saves', async () => {
    successfulSaves()
    show({...summary(),charge_controls:{...summary().charge_controls!,tax_exempt:true}})
    await userEvent.click(screen.getByRole('button',{name:'Add certificate/reference'}))
    await userEvent.type(screen.getByRole('textbox'),'CERT-CLICK')
    await userEvent.click(screen.getByRole('switch',{name:'Shop supplies'}))
    await waitFor(()=>expect(screen.getByRole('switch',{name:'Shop supplies'})).toBeEnabled())
    expect(api.adjustInvoiceCharges).toHaveBeenCalledTimes(1)
    expect(api.adjustInvoiceCharges.mock.calls[0][1]).toEqual({expected_settlement_version:1,tax_exempt:true,shop_supplies_enabled:false,support_reference:'CERT-CLICK'})
  })
  it('waits for pointer release before combining the reference and toggle', async () => {
    successfulSaves()
    show({...summary(),charge_controls:{...summary().charge_controls!,tax_exempt:true}})
    const user=userEvent.setup()
    await user.click(screen.getByRole('button',{name:'Add certificate/reference'}))
    await user.type(screen.getByRole('textbox'),'CERT-HOLD')
    const supplies=screen.getByRole('switch',{name:'Shop supplies'})
    await user.pointer({target:supplies,keys:'[MouseLeft>]'})
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,20))})
    expect(api.adjustInvoiceCharges).not.toHaveBeenCalled()
    expect(supplies).toBeEnabled()
    await user.pointer({target:supplies,keys:'[/MouseLeft]'})
    await waitFor(()=>expect(api.adjustInvoiceCharges).toHaveBeenCalledTimes(1))
    expect(api.adjustInvoiceCharges.mock.calls[0][1]).toEqual({expected_settlement_version:1,tax_exempt:true,shop_supplies_enabled:false,support_reference:'CERT-HOLD'})
  })
  it('does not save a toggle when a pressed pointer is released away from it', async () => {
    successfulSaves()
    show({...summary(),charge_controls:{...summary().charge_controls!,tax_exempt:true}})
    const user=userEvent.setup()
    await user.click(screen.getByRole('button',{name:'Add certificate/reference'}))
    await user.type(screen.getByRole('textbox'),'CERT-CANCEL')
    await user.pointer({target:screen.getByRole('switch',{name:'Shop supplies'}),keys:'[MouseLeft>]'})
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,20))})
    await user.pointer({target:document.body,keys:'[/MouseLeft]'})
    expect(api.adjustInvoiceCharges).not.toHaveBeenCalled()
    expect(screen.getByRole('switch',{name:'Shop supplies'})).toHaveAttribute('aria-checked','true')
    await user.tab()
    await waitFor(()=>expect(api.adjustInvoiceCharges).toHaveBeenCalledTimes(1))
    expect(api.adjustInvoiceCharges.mock.calls[0][1].shop_supplies_enabled).toBe(true)
  })
  it('restores the saved switch on a definite rejection and allows another attempt', async () => {
    api.adjustInvoiceCharges.mockRejectedValue(failure('invoice_busy'))
    show()
    const supplies=screen.getByRole('switch',{name:'Shop supplies'})
    await userEvent.click(supplies)
    await screen.findByRole('alert')
    expect(supplies).toHaveAttribute('aria-checked','true')
    expect(supplies).toBeEnabled()
    expect(editing).toHaveBeenLastCalledWith(false)
    await userEvent.click(supplies)
    expect(api.adjustInvoiceCharges).toHaveBeenCalledTimes(2)
  })
  it('freezes uncertain saves and retries the exact body/key without a second invoice change', async () => {
    api.adjustInvoiceCharges.mockRejectedValue(new Error('Connection lost'))
    show()
    await userEvent.click(screen.getByRole('switch',{name:'Shop supplies'}))
    await screen.findByRole('alert')
    expect(screen.getByRole('switch',{name:'Shop supplies'})).toBeDisabled()
    expect(editing).toHaveBeenLastCalledWith(true)
    const first=api.adjustInvoiceCharges.mock.calls[0]
    await userEvent.click(screen.getByRole('button',{name:'Retry update'}))
    expect(api.adjustInvoiceCharges.mock.calls[1]).toEqual(first)
  })
  it('does not overwrite a stale invoice and offers refresh', async () => {
    api.adjustInvoiceCharges.mockRejectedValue(failure('stale_settlement_version',409,2))
    show()
    await userEvent.click(screen.getByRole('switch',{name:'Shop supplies'}))
    await screen.findByRole('alert')
    for(const control of screen.getAllByRole('switch')) expect(control).toBeDisabled()
    expect(screen.getByRole('button',{name:'Refresh invoice'})).toBeInTheDocument()
    expect(editing).toHaveBeenLastCalledWith(true)
  })
  it('keeps unsafe invoice controls disabled without making a request', () => {
    const value=summary();value.charge_controls={...value.charge_controls!,tax_exempt:true,can_adjust:false,unavailable_reason:'Resolve the pending payment first.'}
    show(value)
    for(const control of screen.getAllByRole('switch')) expect(control).toBeDisabled()
    expect(screen.getByText('Resolve the pending payment first.')).toBeInTheDocument()
    expect(api.adjustInvoiceCharges).not.toHaveBeenCalled()
  })
})
