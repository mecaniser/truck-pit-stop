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
