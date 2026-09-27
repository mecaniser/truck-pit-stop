import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import GoogleReviewsPage from '../GoogleReviewsPage'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: mocks }))

const review = { id: 'r1', reviewer_name: 'Simon Kryukov', rating: 5, review_text: 'Had an RV that needed AC charged.', reply_text: null, status: 'awaiting_approval', requires_approval: true, publish_failure_reason: null }

function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><GoogleReviewsPage /></MemoryRouter></QueryClientProvider>)
}

/**
 * DB-088. Regenerate AI waits several seconds on the model with no sign it was
 * pressed, so operators click again (a second paid call) or act on the old
 * draft. While a review action is in flight the pressed button says so and
 * every other action on that review is held.
 */
describe('GoogleReviewsPage review actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/metrics') ? {} : [review] }))
  })

  it('shows the draft is generating and holds the other actions until it returns', async () => {
    let finish: (value: unknown) => void = () => {}
    mocks.post.mockReturnValue(new Promise(resolve => { finish = resolve }))
    show()
    await userEvent.click(await screen.findByRole('button', { name: /Simon Kryukov/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Regenerate AI' }))

    expect(screen.getByRole('button', { name: 'Generating…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Save edit' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
    expect(screen.getByLabelText('Public reply')).toHaveAttribute('readonly')

    await userEvent.click(screen.getByRole('button', { name: 'Generating…' }))
    expect(mocks.post).toHaveBeenCalledTimes(1)

    finish({ data: { ...review, reply_text: 'Thanks so much, Simon!' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Regenerate AI' })).toBeEnabled())
    expect(screen.getByLabelText('Public reply')).toHaveValue('Thanks so much, Simon!')
    expect(screen.getByLabelText('Public reply')).not.toHaveAttribute('readonly')
  })

  it('keeps another review usable, and on screen, while one is still generating', async () => {
    const other = { ...review, id: 'r2', reviewer_name: 'Kimberly Joline', review_text: 'Life savers.' }
    mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/metrics') ? {} : [review, other] }))
    let finish: (value: unknown) => void = () => {}
    const simonDraft = new Promise(resolve => { finish = resolve })
    mocks.post.mockImplementation((url: string) => url.includes('/r1/') ? simonDraft : new Promise(() => {}))
    show()
    await userEvent.click(await screen.findByRole('button', { name: /Simon Kryukov/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Regenerate AI' }))
    await userEvent.click(screen.getByRole('button', { name: /Kimberly Joline/ }))

    expect(screen.getByRole('button', { name: 'Regenerate AI' })).toBeInTheDocument()
    expect(screen.getByLabelText('Public reply')).not.toHaveAttribute('readonly')
    await userEvent.click(screen.getByRole('button', { name: 'Regenerate AI' }))
    expect(mocks.post).toHaveBeenLastCalledWith('/google-reviews/r2/generate')

    finish({ data: { ...review, reply_text: 'Thanks so much, Simon!' } })
    await waitFor(() => expect(mocks.get.mock.calls.filter(([url]) => url === '/google-reviews').length).toBeGreaterThan(1))
    expect(screen.getByRole('heading', { name: 'Kimberly Joline' })).toBeInTheDocument()
    expect(screen.getByLabelText('Public reply')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Generating…' })).toBeDisabled()
  })

  it('releases the actions when generation fails', async () => {
    mocks.post.mockRejectedValue({ response: { data: { detail: 'model unavailable' } } })
    show()
    await userEvent.click(await screen.findByRole('button', { name: /Simon Kryukov/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Regenerate AI' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Regenerate AI' })).toBeEnabled())
    expect(screen.getByRole('button', { name: 'Save edit' })).toBeEnabled()
  })
})
