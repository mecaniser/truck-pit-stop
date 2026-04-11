import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
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

describe('LandingPage approved partners', () => {
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

  it('renders approved businesses from the landing partners endpoint', async () => {
    renderPage()

    expect((await screen.findAllByText(/truck sparking hub application/i)).length).toBeGreaterThan(0)
    expect((await screen.findAllByText(/mcdiesel/i)).length).toBeGreaterThan(0)
    expect(await screen.findByText('Mobile repair and diagnostics across I-95.')).toBeInTheDocument()
    expect(await screen.findByText('Roadside repair, diagnostics')).toBeInTheDocument()
    expect(screen.getAllByText('trucksparkinghub.example.com').length).toBeGreaterThan(0)
  })
})
