import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
import PriceBuilderPanel from '../PriceBuilderPanel'

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
const line = {
  id: 'line-a', repair_order_id: 'order-a', description: 'Renamed operation', hours: '1.25', hourly_rate: '145', total_cost: '181.25',
  line_type: 'manual', recommendation_source: {
    conversion_id: 'conversion-a', recommendation_id: 'recommendation-a',
    source_order: { id: 'source-a', order_number: 'RO-SOURCE', available: true }, description: 'Original recommendation', state: 'active',
  },
}
const summary = { order_id: 'order-a', labor_total: '181.25', parts_total: '0', total_cost: '181.25',
  pricing_locked: false, can_edit_work: true, can_convert_recommendations: true, recommendation_hourly_rate: '145.00', lines: [line], parts: [], warnings: [] }
function setup(props: Partial<ComponentProps<typeof PriceBuilderPanel>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  if (props.isDeleted) client.setQueryData(['price-build', 'order-a'], summary)
  return render(<MemoryRouter><QueryClientProvider client={client}>
    <PriceBuilderPanel orderId="order-a" orderStatus="in_progress" canEdit {...props} />
  </QueryClientProvider></MemoryRouter>)
}
beforeAll(() => { vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }) })
afterAll(() => vi.unstubAllGlobals())
beforeEach(() => { api.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/price-build') ? summary : url.endsWith('/parts') ? [] : {} })) })

describe('recommendation navigation in repair workspace', () => {
  it('focuses and opens the exact operation and preserves original recommendation after rename', async () => {
    setup({ focusedOperationId: 'line-a' })
    const button = await screen.findByRole('button', { name: /Renamed operation/ })
    await waitFor(() => expect(button).toHaveAttribute('aria-expanded', 'true'))
    await waitFor(() => expect(button).toHaveFocus())
    expect(screen.getByText('Original recommendation')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open source recommendation on RO-SOURCE' })).toHaveAttribute('href', '/dashboard/repair-orders?selected=source-a&recommendation=recommendation-a')
  })

  it('shows a completed source recommendation on direct navigation without editable work controls', async () => {
    const intent = vi.fn()
    setup({ orderStatus: 'completed', focusedRecommendationId: 'recommendation-a', onRecommendedServicesOpenChange: intent,
      recommendedServices: [{ id: 'recommendation-a', repair_order_id: 'order-a', tenant_id: 'tenant-a', description: 'Original completed-order note',
        priority: 'urgent', estimated_cost: null, notes: null, is_resolved: false, resolved_by_repair_order_id: null, created_at: '2026-10-12T12:00:00Z' }] })
    expect(await screen.findByText('Original completed-order note')).toBeInTheDocument()
    expect(intent).toHaveBeenCalledWith(true)
    await waitFor(() => expect(document.getElementById('recommendation-recommendation-a')).toHaveFocus())
    expect(screen.queryByRole('button', { name: 'Add recommended service' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Resolve' })).not.toBeInTheDocument()
  })

  it.each([false, true])('uses the server conversion capability and canonical rate: %s', async (allowed) => {
    api.get.mockResolvedValue({ data: { ...summary, can_convert_recommendations: allowed } })
    setup({ recommendedWorkPanel: (context) => <output data-testid="context">{`${context.canConvert}/${context.hourlyRate}`}</output> })
    await waitFor(() => expect(screen.getByTestId('context')).toHaveTextContent(`${allowed}/145`))
  })

  it('hides conversion on a deleted target even if a stale server capability is true', async () => {
    setup({ isDeleted: true, recommendedWorkPanel: (context) => <output data-testid="context">{String(context.canConvert)}</output> })
    expect(screen.getByTestId('context')).toHaveTextContent('false')
  })
})
