import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import RepairOrdersLedger, { type RepairOrdersLedgerRow } from '../RepairOrdersLedger'
import SlidePanel from '../../../components/SlidePanel'

const rows: RepairOrdersLedgerRow[] = [
  {
    id: 'ro-real-17',
    orderNumber: 'RO-1017',
    status: 'In Progress',
    statusTone: 'active',
    description: 'Diagnose intermittent no-start with a deliberately long source description',
    total: '$4,280.50',
    updated: 'Aug 12, 3:00 PM',
    internal: false,
  },
]

const statusOptions = [
  { value: 'all', label: 'All' },
  { value: 'checked_in', label: 'Checked In' },
  { value: 'assigned', label: 'Assigned' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'quality_review', label: 'Quality Review' },
  { value: 'completed', label: 'Completed' },
  { value: 'invoiced', label: 'Invoiced' },
  { value: 'paid', label: 'Paid' },
  { value: 'deleted', label: 'Deleted' },
]

const renderLedger = (overrides: Partial<React.ComponentProps<typeof RepairOrdersLedger>> = {}) => {
  const props: React.ComponentProps<typeof RepairOrdersLedger> = {
    rows,
    totalOrders: 1,
    searchQuery: '',
    statusFilter: 'all',
    statusOptions,
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
    onShowAllOrders: vi.fn(),
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
    expect(screen.getByText('Review and update repair work from check-in through payment.')).toBeInTheDocument()
    expect(screen.queryByText('One canonical record from check-in through paid invoice.')).not.toBeInTheDocument()
    expect(screen.queryByText('Shop Work handoff')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Repair Orders scope: On the Floor, 1 order' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /RO-1017/ })).toHaveAttribute('data-order-id', 'ro-real-17')
  })

  it.each([
    ['needs_action', 'Needs Action'],
    ['on_floor', 'On the Floor'],
    ['ready_to_close', 'Ready to Close'],
  ] as const)('preserves the %s queue origin without converting it into order state', (queueOrigin, label) => {
    renderLedger({ queueOrigin })

    expect(screen.getByRole('button', { name: `Repair Orders scope: ${label}, 1 order` })).toBeInTheDocument()
  })

  it('preserves search, status, selection, create, paging and the deliberate scope change', async () => {
    const user = userEvent.setup()
    const { props } = renderLedger({ hasMore: true, totalOrders: 30 })

    await user.type(screen.getByRole('searchbox', { name: 'Search repair orders' }), 'RO-1017')
    expect(props.onSearchChange).toHaveBeenLastCalledWith('7')
    await user.click(screen.getByRole('button', { name: 'In Progress' }))
    expect(props.onStatusChange).toHaveBeenCalledWith('in_progress')
    await user.selectOptions(screen.getByLabelText('Order status'), 'in_progress')
    expect(props.onStatusChange).toHaveBeenLastCalledWith('in_progress')
    await user.click(screen.getByRole('button', { name: /RO-1017/ }))
    expect(props.onOpenOrder).toHaveBeenCalledWith('ro-real-17')
    await user.click(screen.getByRole('button', { name: 'New repair order' }))
    expect(props.onCreateOrder).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Repair Orders scope: On the Floor, 30 orders' }))
    expect(screen.getByRole('menu', { name: 'Repair Orders scope' })).toBeInTheDocument()
    await user.click(screen.getByRole('menuitem', { name: 'All repair orders' }))
    expect(props.onShowAllOrders).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Next repair-order page' }))
    expect(props.onNextPage).toHaveBeenCalledOnce()
  })

  it('keeps pointer selection in the ledger and moves keyboard selection into the workspace', async () => {
    const user = userEvent.setup()
    const { props } = renderLedger()
    const row = screen.getByRole('button', { name: /RO-1017/ })

    await user.click(row)
    expect(props.onOpenOrder).toHaveBeenLastCalledWith('ro-real-17')

    row.focus()
    await user.keyboard('{Enter}')
    expect(props.onOpenOrder).toHaveBeenLastCalledWith('ro-real-17', { focusWorkspace: true })
  })

  it('keeps the navigator to scan fields instead of mirroring workspace identity', () => {
    renderLedger({ selectedId: 'ro-real-17' })

    const row = screen.getByRole('button', { name: /RO-1017/ })
    expect(row).toHaveAttribute('aria-pressed', 'true')
    expect(row).toHaveTextContent('Diagnose intermittent no-start')
    expect(screen.getByRole('region', { name: 'Scrollable repair-order results' })).toHaveAttribute('tabindex', '0')
    expect(screen.queryByText('Northline Logistics')).not.toBeInTheDocument()
    expect(screen.queryByText('2022 Freightliner Cascadia · Unit 218')).not.toBeInTheDocument()
  })

  it('lands a keyboard-selected record on its heading rather than framing the entire workspace', async () => {
    render(
      <SlidePanel
        isOpen
        layout="workspace"
        workspaceFocusRequest={1}
        onClose={vi.fn()}
        title="#RO-1017"
        subtitle="Repair Order"
        headerVariant="minimal"
      >
        <button type="button">Start work</button>
      </SlidePanel>,
    )

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '#RO-1017' })).toHaveFocus()
    })
    expect(screen.getByRole('region', { name: '#RO-1017' })).not.toHaveFocus()
  })

  it('keeps every canonical status filter reachable in both the quick-filter row and compact select', () => {
    renderLedger()

    const quickFilterGroup = screen.getByRole('group', { name: 'Filter repair orders by status' })
    const select = screen.getByRole('combobox', { name: 'Order status' })

    for (const option of statusOptions) {
      expect(quickFilterGroup).toContainElement(screen.getByRole('button', { name: option.label }))
      expect(select).toHaveTextContent(option.label)
    }
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

})
