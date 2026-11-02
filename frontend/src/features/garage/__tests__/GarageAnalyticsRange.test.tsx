import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import api from '@/lib/api'
import GarageAnalyticsPage from '../GarageAnalyticsPage'

vi.mock('@/lib/api', () => ({ default: { get: vi.fn() } }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 500: '#087252' } }) }))
vi.mock('../../analytics/ChartKit', () => ({ ChartCard: () => null, ProfitabilityScatter: () => null, QuoteFunnel: () => null, RankedBar: () => null, ParetoChart: () => null }))
vi.mock('recharts', () => ({
  BarChart: ({ children }: { children: ReactNode }) => <>{children}</>,
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <>{children}</>,
  Bar: ({ name }: { name: string }) => <div data-testid="revenue-series" data-name={name} />, XAxis: () => null, YAxis: () => null, Tooltip: () => null,
  ReferenceLine: ({ y }: { y: number }) => <div data-testid="average-line" data-y={y} />,
}))
const metric = { value: '0', trend: [] }
const report = {
  range_start: '2024-02-29', range_end: '2024-03-10', rows: [], summary: {},
  revenue: metric, labor_revenue: metric, part_revenue: metric, fees_revenue: metric,
  parts_profit: metric, inventory_value: metric, invoiced_hours: metric, part_sales_finalized: metric, services_finalized: metric,
  ros: [], accounts: [], trucks: [], sent: 0, approved: 0, invoiced: 0,
  service_rows: [], invoice_rows: [],
}
beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })
  vi.mocked(api.get).mockReset().mockResolvedValue({ data: report })
})
function show(tab: string) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[`/?tab=${tab}&range=custom&from_date=2024-02-29&to_date=2024-03-10`]}><GarageAnalyticsPage /></MemoryRouter></QueryClientProvider>)
}
describe('Analytics report date contract', () => {
  it('keeps unverified gross source money separate from the verified net revenue subtotal', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {
      ...report, revenue: { value: '100.00', trend: [{ label: 'W1', value: '100.00' }] },
      source_collection_unallocated_receipts: '300.00',
      source_collection_attribution_note: 'Additional gross source receipts await net sales, tax and cost attribution and are not included in the verified net total.',
      source_collection_parts_profit_attribution_pending: true,
    } })
    show('dashboard')
    expect(await screen.findByText('$100.00')).toBeVisible()
    expect(screen.getByText('Verified net revenue (partial)')).toBeVisible()
    expect(screen.getByRole('status')).toHaveTextContent('Additional gross source receipts: $300.00')
    expect(screen.getByRole('status')).toHaveTextContent('not included in the verified net total')
    expect(screen.getByText('Verified parts profit (partial)')).toBeVisible()
    expect(screen.queryByText('$400.00')).not.toBeInTheDocument()
    expect(screen.getByText('Average weekly verified net revenue (partial) $100.00')).toBeVisible()
    expect(screen.getByTestId('revenue-series')).toHaveAttribute('data-name', 'Verified net revenue (partial)')
    expect(screen.getByText('Verified net revenue each week; additional gross source receipts await attribution.')).toBeVisible()
  })

  it.each([
    ['day', 'daily'], ['week', 'weekly'], ['month', 'monthly'],
  ] as const)('labels the %s bucket average from displayed revenue, including zero periods', async (interval, adjective) => {
    vi.mocked(api.get).mockResolvedValue({ data: {
      ...report,
      revenue_interval: interval,
      revenue: { value: '70000', trend: [
        { label: 'P1', value: '0' }, { label: 'P2', value: '10000' },
        { label: 'P3', value: '20000' }, { label: 'P4', value: '40000' },
      ] },
    } })
    show('dashboard')
    expect(await screen.findByText(`Average ${adjective} revenue $17,500.00`)).toBeVisible()
    expect(screen.getByTestId('average-line')).toHaveAttribute('data-y', '17500')
  })

  it('keeps the weekly label while an older API response has no interval field', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {
      ...report,
      revenue: { value: '4000', trend: [{ label: 'W1', value: '1000' }, { label: 'W2', value: '3000' }] },
    } })
    show('dashboard')
    expect(await screen.findByText('Average weekly revenue $2,000.00')).toBeVisible()
    expect(screen.getByTestId('average-line')).toHaveAttribute('data-y', '2000')
  })

  it('shows cash received separately with expandable receipt evidence, without changing sales totals', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { ...report,
      summary: { net_sales: '1000.00' }, cash_received: '224.62',
      cash_receipts: [{ payment_id: 'cash-1', payment_number: 'PAY-001', invoice_number: 'INV-001', customer_name: 'Example Logistics', received_at: '2024-03-01T18:00:00Z', amount: '224.62' }],
    } })
    show('sales')
    const label = await screen.findByText('Cash received')
    const details = label.closest('details')!
    expect(details.open).toBe(false)
    expect(screen.getByText('$1,000.00')).toBeInTheDocument()
    expect(screen.queryByText('$1,224.62')).not.toBeInTheDocument()
    expect(screen.queryByText(/Cash on hand/i)).not.toBeInTheDocument()
    await userEvent.click(label)
    expect(details.open).toBe(true)
    expect(screen.getByRole('list', { name: 'Cash receipts by customer' })).toHaveTextContent('Example Logistics')
    expect(screen.getByText('PAY-001 · INV-001')).toBeInTheDocument()
    expect(screen.getByText('Mar 1, 2024 UTC')).toHaveAttribute('datetime', '2024-03-01T18:00:00Z')
    await userEvent.click(label)
    expect(details.open).toBe(false)
  })
  it('shows an explicit zero and empty receipt state', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { ...report, cash_received: '0.00', cash_receipts: [] } })
    show('sales')
    const label = await screen.findByText('Cash received')
    expect(label.closest('summary')).toHaveTextContent('$0.00')
    await userEvent.click(label)
    expect(screen.getByText('No cash receipts in this date range.')).toBeVisible()
  })
  it('does not invent a zero cash total when an older API lacks reporting fields', async () => {
    show('sales')
    const label = await screen.findByText('Cash received')
    expect(label.closest('summary')).toHaveTextContent('—')
    await userEvent.click(label)
    expect(screen.getByText('Cash receipt reporting is unavailable.')).toBeVisible()
  })
  it.each(['dashboard', 'sales', 'fees', 'tax', 'parts', 'service-types', 'internal'])('passes exact inclusive date-only params to %s', async tab => {
    show(tab)
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(`/reports/${tab}`, { params: { range: 'custom', from_date: '2024-02-29', to_date: '2024-03-10' } }))
    if (tab === 'dashboard') {
      await waitFor(() => expect(api.get).toHaveBeenCalledWith('/reports/analytics/quote-funnel', { params: { range: 'custom', from_date: '2024-02-29', to_date: '2024-03-10' } }))
    }
  })
  it('does not date-filter current inventory valuation', async () => {
    show('inventory')
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/reports/inventory'))
    expect(screen.queryByRole('button', { name: /Custom range/ })).not.toBeInTheDocument()
    expect(api.get).not.toHaveBeenCalledWith('/reports/dashboard', expect.anything())
  })
  it('preserves dates when switching report tabs', async () => {
    show('sales')
    await userEvent.click(screen.getByRole('button', { name: 'Sales Tax' }))
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/reports/tax', { params: { range: 'custom', from_date: '2024-02-29', to_date: '2024-03-10' } }))
  })
})
