import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import GoogleReviewsPage from '../GoogleReviewsPage'

vi.mock('@/lib/api', () => ({
  default: {
    get: vi.fn(async (url: string) => ({
      data: url.endsWith('/metrics')
        ? { new_reviews: 1, unreplied_reviews: 1, average_rating: 5, average_response_time_hours: 6 }
        : [{ id: '1', reviewer_name: 'Dana K.', rating: 5, review_text: 'Fast turnaround.', reply_text: null, status: 'new', requires_approval: true, publish_failure_reason: null }],
    })),
  },
}))

/**
 * DB-080. At 375px the review list overflowed its column and clipped the star
 * ratings. The filter tabs are whitespace-nowrap in an overflow-x-auto row, but
 * the list and detail panels are grid items, and a grid item's default
 * min-width:auto will not shrink below its content, so the ~414px tab row
 * widened the whole card past the ~315px column instead of scrolling inside it.
 *
 * jsdom does no layout, so this pins the rule that makes the panels shrinkable.
 */
describe('GoogleReviewsPage layout', () => {
  it('lets both inbox panels shrink to the column so the filter tabs scroll instead of widening the card', async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <GoogleReviewsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const list = (await screen.findByRole('button', { name: 'Awaiting approval' })).closest('section')
    const grid = list?.parentElement
    const panels = [...(grid?.children ?? [])]

    expect(grid).toHaveClass('grid')
    expect(panels).toHaveLength(2)
    panels.forEach(panel => expect(panel).toHaveClass('min-w-0'))
  })
})
