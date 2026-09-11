import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import CustomerTaxExemptionControl from './CustomerTaxExemptionControl'

const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), user: {id:'owner',tenant_id:'shop',role:'garage_owner'} as {id:string;tenant_id:string;role:string}|null }))
vi.mock('@/lib/api', () => ({default:{get:mocks.get,put:mocks.put}}))
vi.mock('@/stores/authStore', () => ({useAuthStore:(select:(state:{user:typeof mocks.user})=>unknown)=>select({user:mocks.user})}))
const baseline = {tax_exempt:false,support_reference:null,version:0,updated_at:null}
function show(customerId='customer-1', client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})) {
  return render(<QueryClientProvider client={client}><CustomerTaxExemptionControl customerId={customerId}/></QueryClientProvider>)
}

describe('Customer tax exemption profile setting', () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.user={id:'owner',tenant_id:'shop',role:'garage_owner'}; mocks.get.mockResolvedValue({data:baseline}) })

  it('keeps the default taxable and saves explicit exemption without requiring a reference', async () => {
    mocks.put.mockResolvedValue({data:{...baseline,tax_exempt:true,version:1}})
    show()
    const checkbox=await screen.findByRole('checkbox',{name:/Customer is tax exempt/})
    expect(checkbox).not.toBeChecked()
    expect(screen.queryByLabelText(/Certificate/)).not.toBeInTheDocument()
    await userEvent.click(checkbox)
    expect(mocks.put).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button',{name:'Save tax setting'}))
    await screen.findByText('Tax setting saved.')
    expect(mocks.put).toHaveBeenCalledWith('/customers/customer-1/tax-exemption',{tax_exempt:true,support_reference:null,expected_version:0},{headers:{'Idempotency-Key':expect.any(String)}})
    expect(screen.queryByLabelText(/reason/i)).not.toBeInTheDocument()
  })

  it('trims an optional reference and keeps the issued-invoice boundary visible', async () => {
    mocks.put.mockResolvedValue({data:{...baseline,tax_exempt:true,support_reference:'CERT-123',version:1}})
    show(); await userEvent.click(await screen.findByRole('checkbox'))
    await userEvent.type(screen.getByLabelText(/Certificate/),'  CERT-123  ')
    await userEvent.click(screen.getByRole('button',{name:'Save tax setting'}))
    await waitFor(()=>expect(mocks.put).toHaveBeenCalled())
    expect(mocks.put.mock.calls[0][1].support_reference).toBe('CERT-123')
    expect(screen.getByText(/Issued invoices stay unchanged/)).toBeInTheDocument()
  })

  it('turns exemption off explicitly without retaining a stale reference', async () => {
    mocks.get.mockResolvedValue({data:{...baseline,tax_exempt:true,support_reference:'CERT',version:7}})
    mocks.put.mockResolvedValue({data:{...baseline,version:8}})
    show(); await userEvent.click(await screen.findByRole('checkbox'))
    await userEvent.click(screen.getByRole('button',{name:'Save tax setting'}))
    await waitFor(()=>expect(mocks.put).toHaveBeenCalled())
    expect(mocks.put.mock.calls[0][1]).toEqual({tax_exempt:false,support_reference:null,expected_version:7})
  })

  it('preserves request identity and locks inputs after an uncertain save', async () => {
    mocks.put.mockRejectedValue(new Error('offline'))
    show(); await userEvent.click(await screen.findByRole('checkbox'))
    await userEvent.click(screen.getByRole('button',{name:'Save tax setting'}))
    await screen.findByRole('alert')
    expect(screen.getByRole('checkbox')).toBeDisabled()
    await userEvent.click(screen.getByRole('button',{name:'Retry tax setting'}))
    await waitFor(()=>expect(mocks.put).toHaveBeenCalledTimes(2))
    expect(mocks.put.mock.calls[0]).toEqual(mocks.put.mock.calls[1])
  })

  it('reloads the saved state after failure even when its version did not change', async () => {
    mocks.put.mockRejectedValue(new Error('offline'))
    show(); await userEvent.click(await screen.findByRole('checkbox'))
    await userEvent.click(screen.getByRole('button',{name:'Save tax setting'})); await screen.findByRole('alert')
    await userEvent.click(screen.getByRole('button',{name:'Reload saved tax setting'}))
    await waitFor(()=>expect(screen.getByRole('checkbox')).toBeEnabled())
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('does not request sensitive settings for customer or receptionist roles', () => {
    mocks.user={...mocks.user!,role:'customer'}; const view=show(); expect(mocks.get).not.toHaveBeenCalled(); view.unmount()
    mocks.user={...mocks.user!,role:'receptionist'}; show(); expect(mocks.get).not.toHaveBeenCalled()
  })

  it('does not reuse a cached setting across tenants', async () => {
    const client=new QueryClient({defaultOptions:{queries:{retry:false}}})
    const view=show('same-id',client); await screen.findByRole('checkbox'); view.unmount()
    mocks.user={...mocks.user!,tenant_id:'other-shop'}
    mocks.get.mockResolvedValue({data:{...baseline,tax_exempt:true,version:2}})
    show('same-id',client)
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(await screen.findByRole('checkbox')).toBeChecked()
    expect(mocks.get).toHaveBeenCalledTimes(2)
  })

  it('shows load failure without displaying a fabricated taxable value', async () => {
    mocks.get.mockRejectedValue(new Error('denied')); show(); await screen.findByRole('alert')
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(mocks.put).not.toHaveBeenCalled()
  })
})
