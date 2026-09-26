import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import GoogleReviewsSettingsPage from '../GoogleReviewsSettingsPage'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get, post: mocks.post, put: mocks.put, delete: mocks.delete } }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const pendingConnection = { configured: true, is_connected: false, status: 'location_selection_required', location_name: null, last_sync_at: null, last_sync_error: null }
const settings = { brand_voice_prompt: '', reply_policy: '', auto_publish_five_star: false, alert_recipients: [] }

// The backend replaces every 5xx detail with "Internal server error" (app/main.py), so the page
// can only tell failures apart by status code.
function locationsFailWith(status: number) {
  mocks.get.mockImplementation(async (url: string) => {
    if (url === '/google-reviews/connection/status') return { data: pendingConnection }
    if (url === '/google-reviews/settings') return { data: settings }
    if (url === '/google-reviews/connection/locations') throw { response: { status, data: { detail: 'Internal server error' } } }
    throw new Error(`unexpected GET ${url}`)
  })
}

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter><GoogleReviewsSettingsPage /></MemoryRouter></QueryClientProvider>)
}

describe('GoogleReviewsSettingsPage location loading failure', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('offers a reconnect when Google cannot load locations for a stale connection', async () => {
    locationsFailWith(502)
    mocks.post.mockResolvedValue({ data: { url: 'https://accounts.google.com/o/oauth2/auth' } })
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    show()
    expect(await screen.findByText(/Google could not load this account's Business Profile locations/)).toBeInTheDocument()
    expect(screen.queryByText('Internal server error')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Reconnect Google account/ }))
    expect(mocks.post).toHaveBeenCalledWith('/google-reviews/connection/authorize')
    vi.unstubAllGlobals()
  })

  it('does not offer a reconnect while Google has not granted the platform quota', async () => {
    locationsFailWith(503)
    show()
    expect(await screen.findByText(/API access is still pending/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Reconnect Google account/ })).not.toBeInTheDocument()
  })
})
