import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import GoogleReviewsPage from '../GoogleReviewsPage'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get, post: mocks.post, put: mocks.put } }))

const review = (i: number, extra: Record<string, unknown> = {}) => ({ id: `r${i}`, reviewer_name: `Driver ${i}`, rating: 5, review_text: `Review ${i}`, review_created_at: '2026-09-12T10:00:00Z', reply_text: null, status: 'awaiting_approval', requires_approval: true, publish_failure_reason: null, published_at: null, ...extra })
const shortDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })

function serve(all: ReturnType<typeof review>[]) {
  mocks.get.mockImplementation(async (url: string, config?: { params?: { offset?: number; limit?: number } }) => {
    if (url.endsWith('/metrics')) return { data: { new_reviews: 0, unreplied_reviews: 0, average_rating: 5, average_response_time_hours: null } }
    const offset = config?.params?.offset ?? 0; const limit = config?.params?.limit ?? 50
    return { data: { items: all.slice(offset, offset + limit), total: all.length, limit, offset } }
  })
}

function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><GoogleReviewsPage /></MemoryRouter></QueryClientProvider>)
}

/**
 * DB-092. Production syncs ~300-350 reviews but the inbox showed only the newest 200,
 * with no dates, raw status names, and a replied review's public reply sitting in the
 * same editable box as an unsent draft.
 */
describe('GoogleReviewsPage history and replied reviews', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('shows each review date and a readable status', async () => {
    serve([review(1, { status: 'published', reply_text: 'Thanks!', requires_approval: false })])
    show()
    const item = await screen.findByRole('button', { name: /Driver 1/ })
    expect(item).toHaveTextContent(shortDate('2026-09-12T10:00:00Z'))
    expect(item).toHaveTextContent('Replied')
    expect(item).not.toHaveTextContent('published')
  })

  it('loads the rest of the history on demand', async () => {
    serve(Array.from({ length: 60 }, (_, i) => review(i)))
    show()
    expect(await screen.findByText('Showing 50 of 60')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Load more' }))
    expect(await screen.findByText('Showing 60 of 60')).toBeInTheDocument()
    expect(mocks.get).toHaveBeenCalledWith('/google-reviews', { params: { limit: 50, offset: 50 } })
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })

  it('shows a reply already on Google read-only until the owner chooses to replace it', async () => {
    serve([review(1, { status: 'published', reply_text: 'Thanks for coming in!', requires_approval: false, published_at: '2026-09-13T09:00:00Z' })])
    show()
    await userEvent.click(await screen.findByRole('button', { name: /Driver 1/ }))

    const reply = screen.getByLabelText('Public reply on Google')
    expect(reply).toHaveAttribute('readonly')
    expect(screen.queryByRole('button', { name: /Regenerate AI/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Publish/ })).not.toBeInTheDocument()
    expect(screen.getByText(new RegExp(`Replied ${shortDate('2026-09-13T09:00:00Z')}`))).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Edit public reply' }))
    expect(screen.getByText(/replace your current reply on Google/)).toBeInTheDocument()
    await waitFor(() => expect(reply).not.toHaveAttribute('readonly'))
    expect(screen.getByRole('button', { name: 'Save edit' })).toBeInTheDocument()
  })
})
