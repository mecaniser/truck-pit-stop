import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Quote, RepairOrderHistoryEvent } from '@/types'
import CustomerAuthorizationCard from '../CustomerAuthorizationCard'

const quote = (overrides: Partial<Quote> = {}): Quote => ({
  id: 'quote-2',
  tenant_id: 'tenant-1',
  repair_order_id: 'order-1',
  quote_number: 'Q-000002',
  total_amount: '1450.00',
  notes: null,
  expires_at: '2026-08-20T12:00:00Z',
  is_approved: false,
  is_declined: false,
  decline_notes: null,
  sent_to_customer: true,
  sent_at: '2026-08-11T14:00:00Z',
  created_at: '2026-08-11T13:55:00Z',
  updated_at: '2026-08-11T14:00:00Z',
  revision: 2,
  authorization_type: 'additional_work',
  previously_authorized_amount: '1000.00',
  delta_amount: '450.00',
  ...overrides,
})

const historyEvent: RepairOrderHistoryEvent = {
  id: 'event-1',
  event_type: 'authorization_published',
  label: 'Authorization revision 2 published',
  actor_name: 'Olivia Owner',
  created_at: '2026-08-11T14:00:00Z',
  detail: JSON.stringify({
    revision: 2,
    previous_amount: '1000.00',
    delta_amount: '450.00',
    resulting_total: '1450.00',
    source: 'staff_publication',
  }),
}

const renderCard = (overrides: Partial<Parameters<typeof CustomerAuthorizationCard>[0]> = {}) => {
  const props = {
    quote: quote(),
    historyEvents: [historyEvent],
    approvePending: false,
    declinePending: false,
    showDeclineForm: false,
    declineNotes: '',
    onApprove: vi.fn(),
    onShowDecline: vi.fn(),
    onDeclineNotesChange: vi.fn(),
    onDecline: vi.fn(),
    onCancelDecline: vi.fn(),
    ...overrides,
  }
  render(<CustomerAuthorizationCard {...props} />)
  return props
}

describe('CustomerAuthorizationCard', () => {
  it('shows the prior ceiling, delta, resulting total, and immutable history', () => {
    renderCard()

    expect(screen.getByText(/Additional work authorization · Q-000002/)).toBeInTheDocument()
    expect(screen.getByText('$1,000.00')).toBeInTheDocument()
    expect(screen.getByText('+$450.00')).toBeInTheDocument()
    expect(screen.getByText('$1,450.00')).toBeInTheDocument()
    fireEvent.click(screen.getByText(/Authorization history · 1 event/))
    expect(screen.getByText(/Resulting total \$1,450.00/)).toBeInTheDocument()
  })

  it('keeps customer decisions explicit and separate', () => {
    const props = renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Authorize additional work' }))
    fireEvent.click(screen.getByRole('button', { name: 'Decline this revision' }))

    expect(props.onApprove).toHaveBeenCalledTimes(1)
    expect(props.onShowDecline).toHaveBeenCalledTimes(1)
  })

  it('never offers approval after an immutable decline', () => {
    renderCard({
      quote: quote({ is_declined: true, decline_notes: 'Please defer this item.' }),
    })

    expect(screen.getByRole('heading', { name: 'Additional work declined' })).toBeInTheDocument()
    expect(screen.getByText(/earlier approved amount remains authorized/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /authorize/i })).not.toBeInTheDocument()
    expect(screen.getByText(/Please defer this item/)).toBeInTheDocument()
  })

  it('uses stacked mobile-safe actions and 44px minimum targets', () => {
    renderCard()

    const approve = screen.getByRole('button', { name: 'Authorize additional work' })
    expect(approve).toHaveClass('min-h-[44px]')
    expect(approve.parentElement).toHaveClass('flex-col', 'sm:flex-row')
  })
})
