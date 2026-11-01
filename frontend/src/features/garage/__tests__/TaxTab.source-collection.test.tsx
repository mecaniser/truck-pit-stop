import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get } }))
import { TaxTab } from '../GarageAnalyticsPage'

const note = 'Tax associated with linked ETS invoices requires external reconciliation and is not included in this report total.'
beforeEach(() => mocks.get.mockReset())
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
function show(metadata?: { receipt_count: number; required: boolean; accounting_owner: string; note: string }) {
  mocks.get.mockResolvedValue({ data: { rows: [], source_collection_tax_reconciliation: metadata } })
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><TaxTab range={{ range: 'this_month' }} /></QueryClientProvider>)
}

describe('tax report scope for source collection receipts', () => {
  it('does not claim zero tax collected when linked ETS tax needs external reconciliation, including CSV', async () => {
    let exported: Blob | undefined
    const OriginalURL = URL
    vi.stubGlobal('URL', class extends OriginalURL {
      static createObjectURL(blob: Blob) { exported = blob; return 'blob:fictional-tax-export' }
      static revokeObjectURL() {}
    })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    show({ receipt_count: 2, required: true, accounting_owner: 'external_manual', note })
    expect(await screen.findByText(note)).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('2 linked ETS collection receipts require external tax reconciliation')
    expect(screen.getByRole('columnheader', { name: 'Tax recorded here' })).toBeInTheDocument()
    expect(screen.getByText('No tax recorded in this report. Tax for linked ETS collection receipts requires external reconciliation.')).toBeInTheDocument()
    expect(screen.queryByText('No tax collected in this range')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Export' }))
    expect(exported).toBeDefined()
    const csv = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = reject
      reader.readAsText(exported!)
    })
    expect(csv).toContain('Tax recorded here')
    expect(csv).toContain(note)
    expect(csv).toContain('Linked ETS collection receipts,2,External tax reconciliation required')
  })

  it.each([undefined, { receipt_count: 0, required: false, accounting_owner: 'external_manual', note }])('preserves the ordinary report when no source receipt falls in the period', async metadata => {
    show(metadata)
    expect(await screen.findByText('Total Tax Collected')).toBeInTheDocument()
    expect(screen.getByText('No tax collected in this range')).toBeInTheDocument()
    expect(screen.queryByText(note)).not.toBeInTheDocument()
  })
})
