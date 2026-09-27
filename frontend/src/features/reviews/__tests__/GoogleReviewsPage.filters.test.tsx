import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import GoogleReviewsPage from '../GoogleReviewsPage'

const mocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get } }))

function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><GoogleReviewsPage /></MemoryRouter></QueryClientProvider>)
}

const lastInboxStatus = () => {
  const calls = mocks.get.mock.calls.filter(([url]) => url === '/google-reviews')
  return calls[calls.length - 1]?.[1]?.params?.status
}

/**
 * DB-085. Most of the shop's reviews were already answered on Google, but the inbox
 * had no way to show only the ones still waiting on a reply, and the Unreplied card
 * did nothing when clicked.
 */
describe('GoogleReviewsPage reply filters', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/metrics') ? { new_reviews: 0, unreplied_reviews: 3, average_rating: 4.9, average_response_time_hours: null } : [] }))
  })

  it('filters to reviews that still need a reply', async () => {
    show()
    await userEvent.click(await screen.findByRole('button', { name: 'Needs reply' }))
    await waitFor(() => expect(lastInboxStatus()).toBe('needs_reply'))
  })

  it('names reviews with a public reply "Replied", whoever wrote it', async () => {
    show()
    await userEvent.click(await screen.findByRole('button', { name: 'Replied' }))
    await waitFor(() => expect(lastInboxStatus()).toBe('published'))
  })

  it('opens the needs-reply list from the Unreplied card', async () => {
    show()
    await userEvent.click(await screen.findByRole('button', { name: /Unreplied\s*3/ }))
    await waitFor(() => expect(lastInboxStatus()).toBe('needs_reply'))
  })
})
