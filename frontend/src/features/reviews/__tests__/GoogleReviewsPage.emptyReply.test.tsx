import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import GoogleReviewsPage from '../GoogleReviewsPage'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get, post: mocks.post, put: mocks.put } }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const base = { id: 'r1', reviewer_name: 'trrohin', rating: 5, review_text: null, review_created_at: '2026-09-20T10:00:00Z', reply_text: null, status: 'awaiting_approval', requires_approval: true, publish_failure_reason: null, published_at: null }
const metricCalls = () => mocks.get.mock.calls.filter(([url]) => url === '/google-reviews/metrics').length

function serve(review: typeof base) {
  mocks.get.mockImplementation(async (url: string) => url.endsWith('/metrics')
    ? { data: { new_reviews: 0, unreplied_reviews: 1, average_rating: 5, average_response_time_hours: null } }
    : { data: { items: [review], total: 1, limit: 50, offset: 0 } })
}

function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><GoogleReviewsPage /></MemoryRouter></QueryClientProvider>)
}

/**
 * DB-093. In production a rating-only review was approved with an empty reply and its
 * publish then failed with a generic 502; the Unreplied card also stayed stale after
 * four successful publishes because only the list was refreshed.
 */
describe('GoogleReviewsPage empty replies and live counts', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('cannot approve an empty reply', async () => {
    serve(base)
    show()
    await userEvent.click(await screen.findByRole('button', { name: /trrohin/ }))
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Public reply'), 'Thanks for the stars!')
    expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled()
  })

  it('cannot publish an approved reply that is empty', async () => {
    serve({ ...base, requires_approval: false })
    show()
    await userEvent.click(await screen.findByRole('button', { name: /trrohin/ }))
    expect(screen.getByRole('button', { name: 'Publish' })).toBeDisabled()
  })

  it('refreshes the Unreplied and other counts after an action', async () => {
    serve({ ...base, reply_text: 'Thanks for the stars!' })
    mocks.post.mockResolvedValue({ data: { ...base, reply_text: 'Thanks for the stars!', requires_approval: false } })
    show()
    await userEvent.click(await screen.findByRole('button', { name: /trrohin/ }))
    const before = metricCalls()
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(metricCalls()).toBeGreaterThan(before))
  })
})
