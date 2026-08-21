import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'

import ShopCockpitActionLedger, {
  type ActionQueueOrder,
  type ActionQueueProjection,
} from '../ShopCockpitActionLedger'

const order = (
  id: string,
  orderNumber: string,
  status: string,
  customer: string,
  vehicle: string,
  overrides: Partial<ActionQueueOrder> = {},
): ActionQueueOrder => ({
  id,
  order_number: orderNumber,
  status,
  pending_zelle_confirmation: false,
  description: 'Source-grounded projected work description',
  customer_name: customer,
  vehicle_info: vehicle,
  total_cost: '1285.00',
  updated_at: '2026-08-12T12:00:00Z',
  mechanic_name: null,
  work_started_at: null,
  hold_reason: null,
  held_at: null,
  quote_sent: null,
  ...overrides,
})

const projection: ActionQueueProjection = {
  orders_needing_action: [
    order('ro-needs', 'RO-2026-0101', 'pending_review', 'NorthStar Logistics', '2021 Freightliner Cascadia 126', { quote_sent: true }),
  ],
  orders_needing_action_has_more: false,
  orders_on_floor: [
    order('ro-floor', 'RO-2026-0102', 'in_progress', 'A Very Long Customer Name That Must Remain Readable', '2023 Freightliner Cascadia 126 · Unit 998877', { mechanic_name: 'M. Reyes' }),
  ],
  orders_on_floor_has_more: false,
  orders_ready_to_close: [
    order('ro-close', 'RO-2026-0103', 'invoiced', 'Long Haul Transportation', '2020 Volvo VNR 640'),
  ],
  orders_ready_to_close_has_more: false,
}

const renderLedger = (overrides: Partial<ComponentProps<typeof ShopCockpitActionLedger>> = {}) => {
  const props: ComponentProps<typeof ShopCockpitActionLedger> = {
    projection,
    isManager: true,
    canViewActivity: true,
    queueView: 'queue',
    activityCount: 2,
    isRefreshing: false,
    lastUpdatedLabel: 'Updated just now',
    quickOrderExpanded: false,
    notificationRegion: null,
    quickOrderForm: null,
    activityFeed: <div>Authentic activity feed</div>,
    onQueueViewChange: vi.fn(),
    onToggleQuickOrder: vi.fn(),
    onFullOrder: vi.fn(),
    onRefresh: vi.fn(),
    onOpenRecord: vi.fn(),
    ...overrides,
  }
  return { props, ...render(<ShopCockpitActionLedger {...props} />) }
}

describe('DB-035 Stage 3 Action Ledger', () => {
  it('uses operator-facing guidance instead of implementation terminology', () => {
    renderLedger()

    expect(screen.getByText('Open a repair order to review work, approvals, history, and payment.')).toBeInTheDocument()
    expect(screen.queryByText('Three canonical queues. One connected repair record.')).not.toBeInTheDocument()
  })

  it('renders the three canonical lanes and projected scanning fields without a Dashboard detail imitation', () => {
    renderLedger()

    const tabs = screen.getByRole('tablist', { name: 'Work queues' })
    expect(within(tabs).getByRole('tab', { name: 'Needs Action 1' })).toBeInTheDocument()
    expect(within(tabs).getByRole('tab', { name: 'On the Floor 1' })).toBeInTheDocument()
    expect(within(tabs).getByRole('tab', { name: 'Ready to Close 1' })).toBeInTheDocument()
    expect(document.querySelector('[data-order-id="ro-needs"]')).toHaveAttribute('data-lane', 'needs_action')
    expect(screen.getByRole('button', { name: 'Open RO-2026-0101 in Repair Orders' })).toBeInTheDocument()
    expect(screen.queryByText('Selected repair record · read only')).not.toBeInTheDocument()
    expect(screen.queryByText('Not included in Shop Work')).not.toBeInTheDocument()
  })

  it('opens the latest requested projected record from keyboard and rapid pointer input', async () => {
    const user = userEvent.setup()
    const onOpenRecord = vi.fn()
    renderLedger({ onOpenRecord })

    const floorRow = screen.getByRole('button', { name: 'Open RO-2026-0102 in Repair Orders' })
    floorRow.focus()
    await user.keyboard('{Enter}')
    expect(onOpenRecord).toHaveBeenLastCalledWith('ro-floor', 'on_floor')

    await user.click(screen.getByRole('button', { name: 'Open RO-2026-0101 in Repair Orders' }))
    await user.click(screen.getByRole('button', { name: 'Open RO-2026-0103 in Repair Orders' }))
    expect(onOpenRecord).toHaveBeenLastCalledWith('ro-close', 'ready_to_close')
  })

  it('hands the exact order ID and canonical lane to Repair Orders in one action', async () => {
    const user = userEvent.setup()
    const onOpenRecord = vi.fn()
    renderLedger({ onOpenRecord })

    await user.click(screen.getByRole('button', { name: 'Open RO-2026-0102 in Repair Orders' }))
    expect(onOpenRecord).toHaveBeenCalledWith('ro-floor', 'on_floor')
  })

  it('restores the originating canonical lane when Repair Orders returns to Shop Work', () => {
    renderLedger({ initialLaneFilter: 'on_floor' })

    expect(screen.getByRole('tab', { name: 'On the Floor 1' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('button', { name: 'Open RO-2026-0102 in Repair Orders' })).toBeInTheDocument()
    expect(document.querySelector('[data-order-id="ro-needs"]')).not.toBeInTheDocument()
  })

  it('adopts a returned lane after the cockpit has already mounted', () => {
    const { rerender, props } = renderLedger()

    expect(screen.getByRole('tab', { name: 'All work 3' })).toHaveAttribute('aria-selected', 'true')

    rerender(<ShopCockpitActionLedger {...props} initialLaneFilter="on_floor" />)

    expect(screen.getByRole('tab', { name: 'On the Floor 1' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'All work 3' })).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByRole('button', { name: 'Open RO-2026-0102 in Repair Orders' })).toBeInTheDocument()
  })

  it('supports canonical filtering, search, empty state and the authentic Activity alternate', async () => {
    const user = userEvent.setup()
    const { rerender, props } = renderLedger()

    await user.click(screen.getByRole('tab', { name: 'On the Floor 1' }))
    expect(document.querySelector('[data-order-id="ro-floor"]')).toBeInTheDocument()
    expect(document.querySelector('[data-order-id="ro-needs"]')).not.toBeInTheDocument()

    await user.type(screen.getByRole('searchbox', { name: 'Search work queue' }), 'no matching record')
    expect(screen.getByText('No work matches this view')).toBeInTheDocument()

    const emptyProjection: ActionQueueProjection = {
      orders_needing_action: [], orders_needing_action_has_more: false,
      orders_on_floor: [], orders_on_floor_has_more: false,
      orders_ready_to_close: [], orders_ready_to_close_has_more: false,
    }
    rerender(<ShopCockpitActionLedger {...props} projection={emptyProjection} />)
    expect(screen.getByText('No work is waiting')).toBeInTheDocument()
    expect(screen.queryByLabelText('Connected repair record')).not.toBeInTheDocument()

    rerender(<ShopCockpitActionLedger {...props} queueView="activity" />)
    expect(screen.getByText('Authentic activity feed')).toBeInTheDocument()
  })
})
