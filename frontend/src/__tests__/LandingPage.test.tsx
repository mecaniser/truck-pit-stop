import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ThemeProvider } from '../contexts/ThemeContext'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
}))

vi.mock('../lib/api', () => ({
  default: {
    get: apiMocks.get,
    defaults: { headers: { common: {} } },
  },
}))

import LandingPage from '../features/landing/LandingPage'

interface LandingPartnerFixture {
  id: string
  name: string
  slug: string
  address: string | null
  website: string | null
  logo_url: string | null
  partner_summary: string | null
  partner_services: string | null
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <MemoryRouter>
          <LandingPage />
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>
  )
}

describe('LandingPage shop workflow', () => {
  beforeEach(() => {
    apiMocks.get.mockReset()
    apiMocks.get.mockImplementation(async (url: string) => {
      if (url === '/auth/platform-contact') {
        return {
          data: {
            support_name: 'Diesel Bridge Support',
            support_email: 'support@example.com',
            support_phone: null,
          },
        }
      }

      if (url === '/auth/landing-partners') {
        return {
          data: [
            {
              id: 'p-1',
              name: 'Truck Sparking Hub Application',
              slug: 'truck-sparking-hub-application',
              address: 'Charlotte, NC',
              website: 'https://trucksparkinghub.example.com',
              logo_url: null,
              partner_summary: 'Mobile repair and diagnostics across I-95.',
              partner_services: 'Roadside repair, diagnostics',
            },
            {
              id: 'p-2',
              name: 'McDiesel',
              slug: 'mcdiesel',
              address: 'Greenville, SC',
              website: 'https://mcdiesel.example.com',
              logo_url: null,
              partner_summary: 'Fleet PM and bay service for regional carriers.',
              partner_services: 'Fleet PM, in-shop repair',
            },
          ],
        }
      }

      throw new Error(`Unexpected API URL: ${url}`)
    })
  })

  it('presents the shop-first workflow and concise approved-shop proof', async () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Every repair, moving in one clear flow.' })).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /apply for founding shop access/i }).length).toBeGreaterThan(0)
    expect((await screen.findAllByText(/truck sparking hub application/i)).length).toBeGreaterThan(0)
    expect((await screen.findAllByText(/mcdiesel/i)).length).toBeGreaterThan(0)
    expect(await screen.findByText('Roadside repair, diagnostics')).toBeInTheDocument()
    expect(await screen.findByText('Fleet PM, in-shop repair')).toBeInTheDocument()
  })

  it('keeps product-stage changes interactive and explicit', async () => {
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'Invoice' }))

    expect(screen.getByRole('button', { name: 'Invoice' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('heading', { name: 'Carry completed work into the invoice.' })).toBeInTheDocument()
    expect(screen.getByText('Next action')).toBeInTheDocument()
    expect(screen.getByText('Create invoice')).toBeInTheDocument()
  })

  it('distinguishes partner loading failure and offers recovery', async () => {
    apiMocks.get.mockImplementation(async (url: string) => {
      if (url === '/auth/platform-contact') {
        return { data: { support_name: 'Support', support_email: 'support@example.com', support_phone: null } }
      }
      if (url === '/auth/landing-partners') throw new Error('Network unavailable')
      throw new Error(`Unexpected API URL: ${url}`)
    })

    renderPage()

    expect(await screen.findByRole('alert', {}, { timeout: 3000 })).toHaveTextContent('Approved shops could not be loaded.')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
  })

  it('names the partner loading and empty states', async () => {
    let releasePartners: ((value: { data: LandingPartnerFixture[] }) => void) | undefined
    apiMocks.get.mockImplementation(async (url: string) => {
      if (url === '/auth/platform-contact') {
        return { data: { support_name: 'Support', support_email: 'support@example.com', support_phone: null } }
      }
      if (url === '/auth/landing-partners') {
        return new Promise<{ data: LandingPartnerFixture[] }>((resolve) => { releasePartners = resolve })
      }
      throw new Error(`Unexpected API URL: ${url}`)
    })

    renderPage()
    expect(screen.getByRole('status')).toHaveTextContent('Loading approved shops…')

    releasePartners?.({ data: [] })
    expect(await screen.findByText('Approved shop profiles will appear here as they go live.')).toBeInTheDocument()
  })

  it('retries a failed partner request and renders the recovered shop', async () => {
    let partnerAttempts = 0
    apiMocks.get.mockImplementation(async (url: string) => {
      if (url === '/auth/platform-contact') {
        return { data: { support_name: 'Support', support_email: 'support@example.com', support_phone: null } }
      }
      if (url === '/auth/landing-partners') {
        partnerAttempts += 1
        if (partnerAttempts <= 2) throw new Error('Network unavailable')
        return {
          data: [{
            id: 'recovered-shop',
            name: 'Recovered Diesel Shop',
            slug: 'recovered-diesel-shop',
            address: 'Charlotte, NC',
            website: null,
            logo_url: null,
            partner_summary: null,
            partner_services: 'Heavy-duty repair',
          }],
        }
      }
      throw new Error(`Unexpected API URL: ${url}`)
    })

    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }, { timeout: 3000 }))

    expect(await screen.findByText('Recovered Diesel Shop')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
