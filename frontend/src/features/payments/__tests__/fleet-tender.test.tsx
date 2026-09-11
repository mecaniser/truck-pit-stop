import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import SettlementPaymentPanel from '../SettlementPaymentPanel'
import PendingManualPaymentPanel from '../PendingManualPaymentPanel'
import type { InvoiceSettlementSummary } from '../types'
const api=vi.hoisted(()=>({createPaymentAttempt:vi.fn(),confirmPaymentAttempt:vi.fn()}))
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),...api}))
const summary:InvoiceSettlementSummary={...DB048_SETTLEMENT_FIXTURES.unpaid.summary,allowed_actions:{create_attempt:true,confirm_manual:true,rails:['card','zelle','check','ach','fleet_payment']}}
const wrap=(ui:React.ReactNode)=>render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}>{ui}</QueryClientProvider>)
describe('Restored Fleet tender',()=>{
  beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }))
  afterEach(() => vi.unstubAllGlobals())
  it('supports keyboard selection and Escape without changing the provider', async () => {
    wrap(<SettlementPaymentPanel access={{kind:'authenticated',invoiceId:summary.invoice_id}} summary={summary} audience="staff" onUpdated={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'More payment methods' }))
    await userEvent.click(screen.getByRole('radio', { name: 'Fleet Check / Code' }))
    await userEvent.click(screen.getByRole('button', { name: /^Fleet provider/ }))
    await userEvent.keyboard('{ArrowDown}{Enter}')
    expect(screen.getByRole('button', { name: /^Fleet provider/ })).toHaveTextContent('Comchek')
    await userEvent.click(screen.getByRole('button', { name: /^Fleet provider/ }))
    await userEvent.keyboard('{End}{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Fleet provider/ })).toHaveTextContent('Comchek')
  })
  it.each(['EFS','Comchek','T-Chek','Other'])('records %s against the canonical partial rail and freezes confirmation amount',async provider=>{
    api.createPaymentAttempt.mockReset()
    api.confirmPaymentAttempt.mockReset()
    api.createPaymentAttempt.mockResolvedValue({attempt_id:'fleet-one',invoice_id:summary.invoice_id,principal_amount:'50.00',card_fee_amount:'0.00',card_fee_tax_amount:'0.00',provider_charge_amount:'50.00',rail:'fleet_payment',provider:'manual',state:'pending',expires_at:null,provider_configuration_version:1,attempt_version:1,settlement:summary})
    api.confirmPaymentAttempt.mockResolvedValue({settlement:summary})
    wrap(<SettlementPaymentPanel access={{kind:'authenticated',invoiceId:summary.invoice_id}} summary={summary} audience="staff" onUpdated={vi.fn()} />)
    expect(screen.queryByRole('radio',{name:'Fleet Check / Code'})).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button',{name:'More payment methods'}))
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio',{name:'Fleet Check / Code'}))
    await userEvent.click(screen.getByRole('button', { name: /^Fleet provider/ }))
    await userEvent.click(screen.getByRole('option', { name: provider === 'EFS' ? 'EFS / MoneyCode' : provider === 'Other' ? 'Other provider' : provider }))
    await userEvent.click(screen.getByRole('button',{name:'Pay partial amount'}))
    await userEvent.clear(screen.getByLabelText('Amount applied to invoice'))
    await userEvent.type(screen.getByLabelText('Amount applied to invoice'),'50')
    await userEvent.type(screen.getByLabelText('Instrument / code reference'),'TRACE-500')
    if(provider==='Other'){
      expect(screen.getByRole('button',{name:'Record Fleet Check / Code'})).toBeDisabled()
      await userEvent.type(screen.getByLabelText('Provider name'),'Example fleet provider')
    }
    await userEvent.type(screen.getByLabelText('Approval reference (optional)'),'APPROVED-50')
    await userEvent.click(screen.getByRole('button',{name:'Record Fleet Check / Code'}))
    expect(api.createPaymentAttempt).toHaveBeenCalledWith({kind:'authenticated',invoiceId:summary.invoice_id},expect.objectContaining({amount:'50.00',rail:'fleet_payment',sender_evidence:expect.objectContaining({fleet_provider:provider,reference:'TRACE-500',authorization_number:'APPROVED-50',fleet_provider_name:provider==='Other'?'Example fleet provider':null})}),expect.any(String))
    const amount=await screen.findByLabelText(/Amount actually received/)
    expect(amount).toHaveAttribute('readonly')
    expect(amount).toHaveValue('50.00')
    await userEvent.click(screen.getByRole('button',{name:'Confirm Fleet Check / Code received'}))
    expect(api.confirmPaymentAttempt).toHaveBeenCalledWith({kind:'authenticated',invoiceId:summary.invoice_id},'fleet-one',expect.objectContaining({expected_attempt_version:1,received_amount:'50.00',reference:'TRACE-500'}),expect.any(String))
  })
  it('restores a pending Fleet instrument with its evidence and locked trace',()=>{
    wrap(<PendingManualPaymentPanel invoiceId={summary.invoice_id} summary={summary} onUpdated={vi.fn()} allocations={[{...DB048_SETTLEMENT_FIXTURES.pendingZelle500.allocations[0],attempt_version:1,rail:'fleet_payment',reference_number:'FLEET-REF',fleet_provider:'EFS',authorization_number:'APPROVAL-1'}]} />)
    expect(screen.getByText('Provider: EFS · Approval: APPROVAL-1')).toBeInTheDocument()
    expect(screen.getByLabelText('Transaction reference')).toHaveValue('FLEET-REF')
    expect(screen.getByLabelText('Transaction reference')).toHaveAttribute('readonly')
    expect(screen.getByLabelText(/Amount actually received/)).toHaveAttribute('readonly')
  })
})
