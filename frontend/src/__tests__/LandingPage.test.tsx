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

    const headerBrand = screen.getByRole('link', { name: 'Diesel Bridge Network' })
    expect(headerBrand.querySelector('.landing-wordmark--animated')).toBeInTheDocument()
    expect(headerBrand.querySelector('.landing-wordmark__name')).toBeInTheDocument()
    expect(headerBrand.querySelector('.landing-wordmark__letters')).toHaveTextContent('DieselBridge')
    expect(headerBrand.querySelectorAll('.landing-wordmark__letter')).toHaveLength(12)
    expect(headerBrand.querySelectorAll('.landing-wordmark__letter--bridge')).toHaveLength(6)
    const animatedLetters = [...headerBrand.querySelectorAll<HTMLElement>('.landing-wordmark__letter')]
    expect(new Set(animatedLetters.map((letter) => letter.style.getPropertyValue('--letter-drop-y'))).size).toBeGreaterThan(4)
    expect(new Set(animatedLetters.map((letter) => letter.style.getPropertyValue('--letter-drop-delay'))).size).toBe(12)
    expect(animatedLetters.every((letter) => !letter.style.getPropertyValue('--letter-drop-x'))).toBe(true)
    expect(document.querySelectorAll('.landing-wordmark--animated')).toHaveLength(1)
    expect(document.querySelector('.landing-footer .landing-wordmark')).not.toHaveClass('landing-wordmark--animated')
    expect(screen.getByRole('heading', { name: 'Every repair, moving in one clear flow.' })).toBeInTheDocument()
    const primaryCtas = screen.getAllByRole('link', { name: /bring dieselbridge to my shop/i })
    expect(primaryCtas.length).toBe(2)
    expect(primaryCtas.every((link) => link.getAttribute('href') === '/enroll')).toBe(true)
    expect(screen.queryByText(/illustrative|fictional/i)).not.toBeInTheDocument()
    expect(screen.queryByText('One repair order. Five connected outcomes.')).not.toBeInTheDocument()
    expect(screen.getAllByText('RO-2025-0417').length).toBeGreaterThan(0)
    expect(screen.getAllByText('NorthStar Logistics').length).toBeGreaterThan(0)
    expect(screen.getByText(/412,358 mi/)).toBeInTheDocument()
    const taxableSubtotal = 1250 + 2875.42 + 85
    const calculatedTax = Number((taxableSubtotal * 0.0675).toFixed(2))
    expect(calculatedTax).toBe(284.2)
    expect(taxableSubtotal + calculatedTax).toBeCloseTo(4494.62, 2)
    expect(screen.getAllByText('$4,494.62').length).toBeGreaterThan(0)
    expect(screen.getAllByRole('complementary')).toHaveLength(2)
    expect(screen.getByRole('tab', { name: 'Repair Orders' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getAllByRole('heading', { name: 'RO-2025-0417' }).length).toBeGreaterThan(0)
    expect(screen.getByText('Work Requested')).toBeInTheDocument()
    expect(screen.getByText('Work & Labor')).toBeInTheDocument()
    expect((await screen.findAllByText(/truck sparking hub application/i)).length).toBeGreaterThan(0)
    expect((await screen.findAllByText(/mcdiesel/i)).length).toBeGreaterThan(0)
    expect(await screen.findByText('Roadside repair, diagnostics')).toBeInTheDocument()
    expect(await screen.findByText('Fleet PM, in-shop repair')).toBeInTheDocument()
  })

  it('replaces the miniature by module, preserves local state, and keeps keyboard selection current', async () => {
    renderPage()

    fireEvent.click(screen.getByRole('tab', { name: 'Customers' }))
    expect(screen.getByRole('heading', { name: 'Customers' })).toBeInTheDocument()
    expect(screen.queryByText('Work Requested')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Riverbend Freight' }))
    fireEvent.click(screen.getByRole('tab', { name: 'History' }))
    expect(screen.getAllByText('Invoice awaiting payment · INV-2025-0412').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('tab', { name: 'Shop Work' }))
    expect(screen.getAllByText('Shop Cockpit').length).toBeGreaterThan(0)
    expect(screen.getByText('Needs Action')).toBeInTheDocument()
    expect(screen.getAllByText('On the Floor').length).toBeGreaterThan(0)
    expect(screen.getByText('Ready to Close')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Customers' }))
    expect(screen.getByRole('tab', { name: 'History' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getAllByRole('heading', { name: 'Riverbend Freight' }).length).toBeGreaterThan(0)

    fireEvent.keyDown(screen.getByRole('tab', { name: 'Customers' }), { key: 'End' })
    expect(screen.getByRole('tab', { name: 'Vehicle History' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('Repair History')).toBeInTheDocument()

    ;['Repair Orders', 'Customers', 'Shop Work', 'Invoices', 'Vehicle History', 'Repair Orders', 'Customers', 'Shop Work', 'Invoices', 'Vehicle History']
      .forEach((name) => fireEvent.click(screen.getByRole('tab', { name })))
    expect(screen.getByRole('tab', { name: 'Vehicle History' })).toHaveAttribute('aria-selected', 'true')
    expect(document.querySelector('.repair-preview')).toHaveAttribute('data-transition-epoch', '16')
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
    expect(screen.getByText('Loading approved shops…')).toBeInTheDocument()

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
