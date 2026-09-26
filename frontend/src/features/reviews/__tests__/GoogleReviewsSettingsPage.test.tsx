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

describe('GoogleReviewsSettingsPage location selection', () => {
  const locations = [{ account_id: 'acct-1', location_id: 'loc-9', name: 'Truck Pit Stop Truck & Trailer Repair', address: '416 Seaboard Drive, Matthews, NC 28104' }, { account_id: 'acct-1', location_id: 'loc-2', name: 'TruckPitStop', address: null }]
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.get.mockImplementation(async (url: string) => {
      if (url === '/google-reviews/connection/status') return { data: pendingConnection }
      if (url === '/google-reviews/settings') return { data: settings }
      if (url === '/google-reviews/connection/locations') return { data: locations }
      throw new Error(`unexpected GET ${url}`)
    })
  })

  it('saves the location in the shape the API accepts', async () => {
    mocks.put.mockResolvedValue({ data: { ok: true } })
    show()
    await userEvent.click(await screen.findByRole('button', { name: /Truck Pit Stop Truck & Trailer Repair/ }))
    // LocationSelection forbids extra fields and requires location_name (backend google_reviews.py).
    expect(mocks.put).toHaveBeenCalledWith('/google-reviews/connection/location', { account_id: 'acct-1', location_id: 'loc-9', location_name: 'Truck Pit Stop Truck & Trailer Repair' })
  })

  it("shows each location's address so same-named listings can be told apart", async () => {
    show()
    expect(await screen.findByText('416 Seaboard Drive, Matthews, NC 28104')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /TruckPitStop.*No storefront address/ })).toBeInTheDocument()
  })

  it('lets the owner switch to a different Google account before choosing a location', async () => {
    mocks.post.mockResolvedValue({ data: { url: 'https://accounts.google.com/o/oauth2/v2/auth' } })
    vi.stubGlobal('location', { ...window.location, assign: vi.fn() })
    show()
    await screen.findByRole('button', { name: /Truck Pit Stop Truck & Trailer Repair/ })
    await userEvent.click(screen.getByRole('button', { name: /Use a different Google account/ }))
    expect(mocks.post).toHaveBeenCalledWith('/google-reviews/connection/authorize')
    vi.unstubAllGlobals()
  })
})
