import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Quote } from '@/types'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  default: {
    get: apiMocks.get,
    post: apiMocks.post,
    defaults: { headers: { common: {} } },
  },
}))

vi.mock('@/components/brand/TenantBrandLogo', () => ({
  default: () => <div>DieselBridge</div>,
}))

vi.mock('@/hooks/usePlatformContact', () => ({
  usePlatformContact: () => ({
    supportEmail: null,
    supportPhoneDisplay: null,
    mailtoHref: null,
    telHref: null,
  }),
}))

import QuoteApprovalPage from '../QuoteApprovalPage'

const quote = (overrides: Partial<Quote> = {}): Quote => ({
  id: 'quote-2', tenant_id: 'tenant-1', repair_order_id: 'order-1', quote_number: 'Q-000002',
  total_amount: '1450.00', notes: null, expires_at: null, is_approved: false, is_declined: false,
  decline_notes: null, sent_to_customer: true, sent_at: '2026-08-11T14:00:00Z',
  created_at: '2026-08-11T13:55:00Z', updated_at: '2026-08-11T14:00:00Z',
  revision: 2, authorization_type: 'additional_work', previously_authorized_amount: '1000.00',
  delta_amount: '450.00', ...overrides,
})

const detail = (quoteOverrides: Partial<Quote> = {}) => ({
  quote: quote(quoteOverrides),
  order_number: 'RO-000001', order_description: 'No-start diagnosis',
  vehicle_year: 2022, vehicle_make: 'Freightliner', vehicle_model: 'Cascadia', vehicle_vin: 'VIN123456',
  customer_first_name: 'Casey', services: [], parts: [], labor_total: '1000.00', parts_total: '450.00',
  labor_discount_amount: '0.00', order_discount_amount: '0.00', shop_supplies_amount: '0.00',
  service_fee_amount: '0.00', tax_amount: '0.00', estimated_card_total: '1450.00',
  estimated_zelle_total: '1450.00', zelle_savings_amount: '0.00', shop_name: 'North Shop',
  shop_logo_url: null, shop_phone: null, shop_email: null, has_portal_account: true,
  requires_password_setup: false, revision: 2, authorization_type: 'additional_work',
  previously_authorized_amount: '1000.00', additional_amount: '450.00', resulting_authorized_amount: '1450.00',
})

const renderPage = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/quote/token-1']}>
        <Routes>
          <Route path="/quote/:token" element={<QuoteApprovalPage />} />
          <Route path="/portal" element={<div>Portal</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('QuoteApprovalPage authorization contract', () => {
  afterEach(() => {
    apiMocks.get.mockReset()
    apiMocks.post.mockReset()
  })

  it('renders and submits an additional-work decision against the exact token', async () => {
    apiMocks.get.mockResolvedValue({ data: detail() })
    apiMocks.post.mockResolvedValue({ data: quote({ is_approved: true }) })
    renderPage()

    expect(await screen.findByText('Additional work authorization')).toBeInTheDocument()
    expect(screen.getByText('$1,000.00')).toBeInTheDocument()
    expect(screen.getByText('+$450.00')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Authorize Additional Work' }))

    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/quotes/token/token-1/approve'))
  })

  it('does not offer a forbidden decision reversal after decline', async () => {
    apiMocks.get.mockResolvedValue({ data: detail({ is_declined: true, decline_notes: 'Defer it.' }) })
    renderPage()

    expect(await screen.findByRole('heading', { name: 'Additional Work Declined' })).toBeInTheDocument()
    expect(screen.getByText(/earlier approved amount remains valid/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /changed my mind/i })).not.toBeInTheDocument()
    expect(apiMocks.post).not.toHaveBeenCalled()
  })
})
