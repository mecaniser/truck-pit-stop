import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import RepairOrderContextHeader from '../RepairOrderContextHeader'
import RepairOrdersLedger, { type RepairOrdersLedgerRow } from '../RepairOrdersLedger'

const rows: RepairOrdersLedgerRow[] = [
  {
    id: 'ro-real-17',
    orderNumber: 'RO-1017',
    status: 'In Progress',
    statusTone: 'active',
    description: 'Diagnose intermittent no-start with a deliberately long source description',
    customer: 'Northline Logistics',
    vehicle: '2022 Freightliner Cascadia · Unit 218',
    total: '$4,280.50',
    updated: 'Aug 12, 3:00 PM',
    internal: false,
  },
]

const renderLedger = (overrides: Partial<React.ComponentProps<typeof RepairOrdersLedger>> = {}) => {
  const props: React.ComponentProps<typeof RepairOrdersLedger> = {
    rows,
    totalOrders: 1,
    searchQuery: '',
    statusFilter: 'all',
    statusOptions: [{ value: 'all', label: 'All' }, { value: 'in_progress', label: 'In Progress' }],
    selectedId: null,
    queueOrigin: 'on_floor',
    isFetching: false,
    page: 0,
    pageSize: 25,
    hasMore: false,
    isPlaceholder: false,
    canGoPrevious: false,
    onSearchChange: vi.fn(),
    onStatusChange: vi.fn(),
    onOpenOrder: vi.fn(),
    onCreateOrder: vi.fn(),
    onReturnToShopWork: vi.fn(),
    onPreviousPage: vi.fn(),
    onNextPage: vi.fn(),
    ...overrides,
  }
  return { props, ...render(<RepairOrdersLedger {...props} />) }
}

describe('DB-035 Stage 4 Repair Orders presentation', () => {
  it('renders the canonical ledger and treats queue origin as navigation context', () => {
    renderLedger()

    expect(screen.getByRole('heading', { name: 'Repair Orders' })).toBeInTheDocument()
    expect(screen.getByText('Shop Work handoff')).toBeInTheDocument()
    expect(screen.getByText('On the Floor')).toBeInTheDocument()
    expect(screen.getByText('Queue origin is navigation context, not repair-order state.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /RO-1017/ })).toHaveAttribute('data-order-id', 'ro-real-17')
  })

  it.each([
    ['needs_action', 'Needs Action'],
    ['on_floor', 'On the Floor'],
    ['ready_to_close', 'Ready to Close'],
  ] as const)('preserves the %s queue origin without converting it into order state', (queueOrigin, label) => {
    renderLedger({ queueOrigin })

    expect(screen.getByRole('button', { name: `Return to ${label}` })).toBeInTheDocument()
    expect(screen.getByText('Queue origin is navigation context, not repair-order state.')).toBeInTheDocument()
  })

  it('preserves search, status, selection, create, paging and return callbacks', async () => {
    const user = userEvent.setup()
    const { props } = renderLedger({ hasMore: true, totalOrders: 30 })

    await user.type(screen.getByRole('searchbox', { name: 'Search repair orders' }), 'RO-1017')
    expect(props.onSearchChange).toHaveBeenLastCalledWith('7')
    await user.click(screen.getByRole('button', { name: 'In Progress' }))
    expect(props.onStatusChange).toHaveBeenCalledWith('in_progress')
    await user.click(screen.getByRole('button', { name: /RO-1017/ }))
    expect(props.onOpenOrder).toHaveBeenCalledWith('ro-real-17')
    await user.click(screen.getByRole('button', { name: 'New repair order' }))
    expect(props.onCreateOrder).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Return to On the Floor' }))
    expect(props.onReturnToShopWork).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Next repair-order page' }))
    expect(props.onNextPage).toHaveBeenCalledOnce()
  })

  it('covers loading/error, filtered empty and no-selection states without invented records', () => {
    const { rerender, props } = renderLedger({ rows: [], isFetching: true })
    expect(screen.getByText('Updating…')).toBeInTheDocument()
    expect(screen.getByText('No repair orders yet')).toBeInTheDocument()

    rerender(<RepairOrdersLedger {...props} rows={[]} isFetching={false} searchQuery="missing" />)
    expect(screen.getByText('No repair orders match this view')).toBeInTheDocument()

    rerender(<RepairOrdersLedger {...props} rows={[]} isFetching={false} errorMessage="Check the connection and try again." />)
    expect(screen.getByRole('alert')).toHaveTextContent('Repair orders could not be loaded')
  })

  it('anchors real connected detail and keeps history/return actions explicit', async () => {
    const user = userEvent.setup()
    const onHistory = vi.fn()
    const onReturn = vi.fn()
    render(
      <RepairOrderContextHeader
        orderNumber="RO-1017"
        status="In Progress"
        customer="Northline Logistics"
        vehicle="2022 Freightliner Cascadia · Unit 218"
        description="Diagnose intermittent no-start"
        laborTotal="$1,500.00"
        partsTotal="$2,780.50"
        quoteState="Customer authorized"
        invoiceState="Invoice not created"
        queueOrigin="on_floor"
        onRequestHistory={onHistory}
        onReturnToShopWork={onReturn}
      />,
    )

    expect(screen.getByText('Labor $1,500.00 · Parts $2,780.50')).toBeInTheDocument()
    expect(screen.getByText('Customer authorized')).toBeInTheDocument()
    expect(screen.getByText('Invoice not created')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Load order history' }))
    expect(onHistory).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Return to On the Floor' }))
    expect(onReturn).toHaveBeenCalledOnce()
  })
})
