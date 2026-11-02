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
  it('keeps icon actions named and refresh text-free', async () => {
    const user = userEvent.setup()
    const { props } = renderLedger({ activeWork: <div>Active panel</div> })
    const refresh = screen.getByRole('button', { name: 'Refresh Shop Work, Updated just now' })
    expect(refresh).toHaveTextContent('')
    expect(refresh.querySelector('span')).toBeNull()
    await user.click(refresh)
    await user.click(screen.getByRole('button', { name: 'Lightning Order' }))
    await user.click(screen.getByRole('button', { name: 'Full Order' }))
    expect(props.onRefresh).toHaveBeenCalledOnce()
    expect(props.onToggleQuickOrder).toHaveBeenCalledOnce()
    expect(props.onFullOrder).toHaveBeenCalledOnce()
  })

  it('shows unique pending closeout before opening it and updates after refresh', () => {
    const pending = order('payment', 'RO-PAY', 'invoiced', 'Fictional shop', 'Truck', { pending_zelle_confirmation: true })
    const { props, rerender } = renderLedger({ activeWork: <div>Active panel</div>, projection: {
      ...projection,
      orders_needing_action: [...projection.orders_needing_action, pending, projection.orders_ready_to_close[0]],
      orders_ready_to_close: [...projection.orders_ready_to_close, pending],
      orders_closed_today: [order('closed', 'RO-CLOSED', 'paid', 'Fictional shop', 'Truck')],
    } })
    expect(screen.getByRole('button', { name: 'Closeout 2' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.queryByRole('button', { name: 'Open RO-PAY in Repair Orders' })).not.toBeInTheDocument()
    rerender(<ShopCockpitActionLedger {...props} queueView="activity" projection={{ ...projection, orders_ready_to_close: [] }} />)
    expect(screen.getByRole('button', { name: 'Closeout 0' })).toBeInTheDocument()
  })

  it.each([
    ['ready overflow', { orders_ready_to_close_has_more: true }, '1+'],
    ['unrelated action overflow', { orders_needing_action_has_more: true }, '1'],
    ['payment overflow', { orders_needing_action_has_more: true, orders_needing_action: [order('payment', 'RO-PAY', 'invoiced', 'Fictional shop', 'Truck', { pending_zelle_confirmation: true })] }, '2+'],
  ])('keeps Closeout count honest for %s', (_, override, label) => {
    renderLedger({ activeWork: <div>Active panel</div>, projection: { ...projection, ...override } })
    expect(screen.getByRole('button', { name: `Closeout ${label}` })).toBeInTheDocument()
  })

  it('does not apply nonpayment overflow to the payment-review subset', () => {
    renderLedger({ activeWork: <div>Active panel</div>, workView: 'closeout', projection: { ...projection, orders_needing_action_has_more: true } })
    expect(screen.getByRole('tab', { name: 'Payment review 0' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Payment review 0+' })).not.toBeInTheDocument()
  })

  it.each(['completed', 'invoiced'])('labels imported %s history without a native billing instruction', (status) => {
    renderLedger({ projection: { ...projection, orders_ready_to_close: [
      order('ets-history', 'ETS-EXAMPLE', status, 'Synthetic carrier', 'Synthetic truck', { source: 'easy_truck_shop_import', pending_zelle_confirmation: true }),
    ] } })
    expect(screen.getByText('ETS history')).toBeInTheDocument()
    expect(screen.queryByText('Invoice Customer')).not.toBeInTheDocument()
    expect(screen.queryByText('Payment Due')).not.toBeInTheDocument()
    expect(screen.queryByText('Zelle Review')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open ETS-EXAMPLE in Repair Orders' })).toBeInTheDocument()
  })

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

  it('shows the server-authoritative work value and reports lane/search scope changes', async () => {
    const user = userEvent.setup()
    const onValueScopeChange = vi.fn()
    renderLedger({
      valueSummary: { order_count: 61, order_value: '81234.56' },
      onValueScopeChange,
    })

    expect(screen.getByText('$81,234.56')).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'On the Floor 1' }))
    await user.type(screen.getByRole('searchbox', { name: 'Search work queue' }), 'NorthStar')

    expect(onValueScopeChange).toHaveBeenLastCalledWith({ lane: 'on_floor', search: 'NorthStar' })
  })

  it('keeps closeout value out of Activity and absent values unknown', () => {
    const { props, rerender } = renderLedger({ activeWork: <div>Active work</div>, workView: 'closeout' })
    expect(screen.getByText('Closeout work value').parentElement).toHaveTextContent('—')
    rerender(<ShopCockpitActionLedger {...props} queueView="activity" valueSummary={{ order_count: 2, order_value: '100.00' }} />)
    expect(screen.queryByText('Closeout work value')).not.toBeInTheDocument()
    expect(screen.queryByText('$100.00')).not.toBeInTheDocument()
  })
  it('shows lane labels only when multiple lanes share the list', async () => {
    const user = userEvent.setup()
    renderLedger()
    const row = screen.getByRole('button', { name: 'Open RO-2026-0103 in Repair Orders' })
    expect(within(row).getByText('Ready to Close')).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Ready to Close 1' }))
    expect(within(row).queryByText('Ready to Close')).not.toBeInTheDocument()
    expect(within(row).getByText('Payment Due')).toBeInTheDocument()
  })
  it('distinguishes calculating, unavailable, and genuine zero work values', () => {
    const { rerender, props } = renderLedger({ valueSummaryLoading: true })
    expect(screen.getByText('Calculating…')).toBeInTheDocument()

    rerender(<ShopCockpitActionLedger {...props} valueSummaryLoading={false} valueSummaryError />)
    expect(screen.getByText('Unavailable')).toBeInTheDocument()

    rerender(
      <ShopCockpitActionLedger
        {...props}
        valueSummaryLoading={false}
        valueSummaryError={false}
        valueSummary={{ order_count: 0, order_value: '0.00' }}
      />,
    )
    expect(screen.getByText('$0.00')).toBeInTheDocument()
  })
})
