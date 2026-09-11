import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import api from '@/lib/api'
import GarageAnalyticsPage from '../GarageAnalyticsPage'

vi.mock('@/lib/api', () => ({ default: { get: vi.fn() } }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 500: '#087252' } }) }))
vi.mock('../../analytics/ChartKit', () => ({ ChartCard: () => null, ProfitabilityScatter: () => null, QuoteFunnel: () => null, RankedBar: () => null, ParetoChart: () => null }))
vi.mock('recharts', () => ({ BarChart: () => null, Bar: () => null, XAxis: () => null, YAxis: () => null, Tooltip: () => null, ResponsiveContainer: () => null }))
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
    expect(screen.getByRole('list', { name: 'Cash receipts' })).toHaveTextContent('Example Logistics')
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
