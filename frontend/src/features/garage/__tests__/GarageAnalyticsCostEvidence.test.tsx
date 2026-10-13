import type { ReactNode } from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import api from '@/lib/api'
import GarageAnalyticsPage from '../GarageAnalyticsPage'

vi.mock('@/lib/api', () => ({ default: { get: vi.fn() } }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 500: '#087252' } }) }))
vi.mock('../../analytics/ChartKit', () => ({
  ChartCard: ({ title, children }: { title: string; children: ReactNode }) => <section aria-label={title}>{children}</section>,
  QuoteFunnel: () => null, RankedBar: () => null,
  ParetoChart: ({ accounts }: { accounts: { name: string; revenue: number }[] }) => <div>{accounts.map(account => <p key={account.name}>{account.name}: ${account.revenue}</p>)}</div>,
}))
vi.mock('recharts', () => ({ BarChart: () => null, Bar: () => null, XAxis: () => null, YAxis: () => null, Tooltip: () => null, ResponsiveContainer: () => null }))
const metric = { value: '0', trend: [] }
const dashboard = {
  revenue: metric, labor_revenue: metric, part_revenue: metric, fees_revenue: metric,
  parts_profit: metric, inventory_value: metric, invoiced_hours: metric, part_sales_finalized: metric, services_finalized: metric,
}
beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })
  vi.mocked(api.get).mockReset().mockImplementation(async (url) => {
    if (url === '/reports/dashboard') return { data: dashboard }
    if (url === '/reports/analytics/accounts') return { data: { accounts: [{ name: 'Account A', revenue: 300, marginPct: null, cumPct: 100 }] } }
    return { data: { ros: [], accounts: [], trucks: [], sent: 0 } }
  })
})
function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={['/?tab=dashboard']}><GarageAnalyticsPage /></MemoryRouter></QueryClientProvider>)
}
describe('Analytics cost evidence integration', () => {
  it('retains account revenue with null margins and shows old-backend coverage unavailable', async () => {
    show()
    expect(await screen.findByText('Account A: $300')).toBeInTheDocument()
    expect(await screen.findByText('Cost breakdown unavailable')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Parts and sublet contribution' })).toBeInTheDocument()
    expect(screen.queryByText('Labor vs. Parts Profitability')).not.toBeInTheDocument()
  })

  it('keeps request failures distinct from empty or missing cost evidence', async () => {
    const original = vi.mocked(api.get).getMockImplementation()!
    vi.mocked(api.get).mockImplementation(async (...args) => {
      if (args[0] === '/reports/analytics/profitability') throw new Error('Report request failed')
      return original(...args)
    })
    show()
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load cost breakdown')
    expect(screen.queryByText('Cost breakdown unavailable')).not.toBeInTheDocument()
    expect(screen.queryByText('No repair orders in this date range.')).not.toBeInTheDocument()
    expect(await screen.findByText('Account A: $300')).toBeInTheDocument()
  })
})
