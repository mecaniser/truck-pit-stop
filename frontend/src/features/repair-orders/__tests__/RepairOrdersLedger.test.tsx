import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import RepairOrdersLedger, { type RepairOrdersLedgerRow } from '../RepairOrdersLedger'
import SlidePanel from '../../../components/SlidePanel'
import { accentRampsFor } from '../../../contexts/appearanceTokens'
import LEDGER_CSS from '../../../index.css?inline'

const rgbFromHex = (value: string) => {
  const hex = value.replace('#', '')
  return [0, 2, 4].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16))
}

const relativeLuminance = (value: string) => {
  const [red, green, blue] = rgbFromHex(value).map((channel) => {
    const normalized = channel / 255
    return normalized <= 0.03928 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4
  })
  return red * 0.2126 + green * 0.7152 + blue * 0.0722
}

const contrastRatio = (foreground: string, background: string) => {
  const foregroundLuminance = relativeLuminance(foreground)
  const backgroundLuminance = relativeLuminance(background)
  const [lighter, darker] = foregroundLuminance > backgroundLuminance
    ? [foregroundLuminance, backgroundLuminance]
    : [backgroundLuminance, foregroundLuminance]
  return (lighter + 0.05) / (darker + 0.05)
}

const mix = (foreground: string, percentage: number, background: string) => {
  const foregroundRgb = rgbFromHex(foreground)
  const backgroundRgb = rgbFromHex(background)
  const alpha = percentage / 100
  return `#${foregroundRgb.map((channel, index) => Math.round(channel * alpha + backgroundRgb[index] * (1 - alpha)).toString(16).padStart(2, '0')).join('')}`
}

const ledgerSurfaces = {
  light: {
    text: '#14243a',
    muted: '#5b6d82',
    overlay: '#ffffff',
    raised: '#f6f8fb',
    states: ['#ffffff', mix('#f6f8fb', 68, '#ffffff'), mix('#f6f8fb', 88, '#ffffff'), mix('#f6f8fb', 78, '#ffffff')],
  },
  dark: {
    text: '#f6f8fb',
    muted: '#b8c5d5',
    overlay: '#111f33',
    raised: '#0d1a2a',
    states: ['#111f33', mix('#0d1a2a', 76, '#111f33'), mix('#0d1a2a', 90, '#111f33'), mix('#0d1a2a', 86, '#111f33')],
  },
  high_contrast: {
    text: '#ffffff',
    muted: '#e5e7eb',
    overlay: '#000000',
    raised: '#080808',
    states: ['#000000', '#080808'],
  },
} as const

const ledgerAppearanceModes = ['light', 'dark', 'high_contrast'] as const

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
    customerName: 'Northline Logistics',
    vehicleYear: 2022,
    vehicleMake: 'Freightliner',
    vehicleModel: 'Cascadia',
    vehicleUnitNumber: '218',
    technicianName: 'Riley Lopez',
    quoteSent: true,
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
    loadedCount: 0,
    hasMore: false,
    isLoadingMore: false,
    onSearchChange: vi.fn(),
    onStatusChange: vi.fn(),
    onOpenOrder: vi.fn(),
    onCreateOrder: vi.fn(),
    onShowAllOrders: vi.fn(),
    onLoadMore: vi.fn(),
    ...overrides,
  }
  return { props, ...render(<RepairOrdersLedger {...props} />) }
}

describe('DB-035 Stage 4 Repair Orders presentation', () => {
  it('renders the complete filtered server value independently from loaded rows', () => {
    renderLedger({
      loadedCount: 1,
      totalOrders: 63,
      valueSummary: { order_count: 63, order_value: '102345.67' },
    })

    expect(screen.getByText('Filtered order value')).toBeInTheDocument()
    expect(screen.getByText('$102,345.67')).toBeInTheDocument()
  })
  it('distinguishes calculating, unavailable, and genuine zero order values', () => {
    const { rerender, props } = renderLedger({ valueSummaryLoading: true })
    expect(screen.getByText('Calculating…')).toBeInTheDocument()

    rerender(<RepairOrdersLedger {...props} valueSummaryLoading={false} valueSummaryError />)
    expect(screen.getByText('Unavailable')).toBeInTheDocument()

    rerender(
      <RepairOrdersLedger
        {...props}
        valueSummaryLoading={false}
        valueSummaryError={false}
        valueSummary={{ order_count: 0, order_value: '0.00' }}
      />,
    )
    expect(screen.getByText('$0.00')).toBeInTheDocument()
  })
  it('binds work-request and Vehicle facts to ledger appearance roles instead of light-only ink', () => {
    const workRequestRules = LEDGER_CSS.match(/\.db-presentation-new \.db-staff-content \.db-repair-orders-ledger \.db-repair-orders-ledger__work-request h3 \{[^}]+\}\s*\.db-repair-orders-ledger__work-request p \{[^}]+\}/)?.[0]

    expect(workRequestRules).toContain('color: var(--db-ledger-metadata)')
    expect(workRequestRules).toContain('color: var(--db-ledger-text)')
    expect(workRequestRules).not.toMatch(/color:\s*#[0-9a-f]{3,8}/i)
    expect(LEDGER_CSS).toContain(".db-staff-shell[data-appearance-mode='dark'] .db-repair-orders-ledger")
    expect(LEDGER_CSS).toContain(".db-staff-shell[data-appearance-mode='high_contrast'] .db-repair-orders-ledger")
    expect(LEDGER_CSS).toContain('--db-ledger-disclosure: ButtonText')
    expect(LEDGER_CSS).toContain('--db-ledger-focus: HighlightText')
    expect(LEDGER_CSS).toContain('--db-ledger-metadata: CanvasText')
    expect(LEDGER_CSS).toContain('--db-ledger-metadata: HighlightText')
  })

  it.each(ledgerAppearanceModes)('keeps ledger fact text and focus accents above their contrast floors in %s mode', (mode) => {
    const palette = ledgerSurfaces[mode]

    for (const surface of palette.states) {
      expect(contrastRatio(palette.text, surface)).toBeGreaterThanOrEqual(4.5)
      expect(contrastRatio(palette.muted, surface)).toBeGreaterThanOrEqual(4.5)
    }

    for (const accent of Object.values(accentRampsFor(mode))) {
      for (const surface of palette.states) {
        expect(contrastRatio(accent[400], surface)).toBeGreaterThanOrEqual(3)
      }
    }
  })
  it('renders the canonical ledger and treats queue origin as navigation context', () => {
    renderLedger()

    expect(screen.getByRole('heading', { name: 'Repair Orders' })).toBeInTheDocument()
    expect(screen.getByText('Review and update repair work from check-in through payment.')).toBeInTheDocument()
    expect(screen.queryByText('One canonical record from check-in through paid invoice.')).not.toBeInTheDocument()
    expect(screen.queryByText('Shop Work handoff')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Repair Orders scope: On the Floor, 1 order' })).toBeInTheDocument()
    expect(screen.getByRole('article', { name: 'Repair order RO-1017' })).toHaveAttribute('data-order-id', 'ro-real-17')
  })

  it.each([
    ['needs_action', 'Needs Action'],
    ['on_floor', 'On the Floor'],
    ['ready_to_close', 'Ready to Close'],
  ] as const)('preserves the %s queue origin without converting it into order state', (queueOrigin, label) => {
    renderLedger({ queueOrigin })

    expect(screen.getByRole('button', { name: `Repair Orders scope: ${label}, 1 order` })).toBeInTheDocument()
  })

  it('preserves search, status, explicit workspace opening, create, paging and the deliberate scope change', async () => {
    const user = userEvent.setup()
    const { props } = renderLedger({ hasMore: true, totalOrders: 30 })

    await user.type(screen.getByRole('searchbox', { name: 'Search repair orders' }), 'RO-1017')
    expect(props.onSearchChange).toHaveBeenLastCalledWith('7')
    await user.click(screen.getByRole('button', { name: 'In Progress' }))
    expect(props.onStatusChange).toHaveBeenCalledWith('in_progress')
    // The compact control is a listbox now, not a native select: it names the
    // active status on its face instead of only inside the popup.
    await user.click(screen.getByRole('button', { name: 'Order status' }))
    await user.click(within(screen.getByRole('listbox', { name: 'Order status options' }))
      .getByRole('option', { name: 'In Progress' }))
    expect(props.onStatusChange).toHaveBeenLastCalledWith('in_progress')
    await user.click(screen.getByRole('button', { name: 'Show details for RO-1017' }))
    expect(props.onOpenOrder).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Open repair order RO-1017 from details' }))
    expect(props.onOpenOrder).toHaveBeenCalledWith('ro-real-17')
    await user.click(screen.getByRole('button', { name: 'New repair order' }))
    expect(props.onCreateOrder).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Repair Orders scope: On the Floor, 30 orders' }))
    expect(screen.getByRole('menu', { name: 'Repair Orders scope' })).toBeInTheDocument()
    await user.click(screen.getByRole('menuitem', { name: 'All repair orders' }))
    expect(props.onShowAllOrders).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: /Load more repair orders/ }))
    expect(props.onLoadMore).toHaveBeenCalledOnce()
  })

  // The list loads as it is scrolled, but the control has to stay reachable
  // without a pointer: an observer that only fires on scroll leaves keyboard
  // and screen-reader users with no way to reach the rest of the set.
  it('states how much of the set is loaded and offers an explicit way to load the rest', async () => {
    const user = userEvent.setup()
    const { props } = renderLedger({ loadedCount: 25, totalOrders: 60, hasMore: true })

    expect(screen.getByText('25 of 60 loaded')).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Load more repair orders, 25 of 60 loaded' })
    await user.click(button)
    expect(props.onLoadMore).toHaveBeenCalledOnce()
  })

  it('stops offering more once the whole set is loaded', () => {
    renderLedger({ loadedCount: 60, totalOrders: 60, hasMore: false })

    expect(screen.queryByRole('button', { name: /Load more/ })).not.toBeInTheDocument()
    expect(screen.getByText('60 orders')).toBeInTheDocument()
  })

  it('does not offer to load more while a load is already running', () => {
    renderLedger({ loadedCount: 25, totalOrders: 60, hasMore: true, isLoadingMore: true })

    expect(screen.getByRole('button', { name: /Load more repair orders/ })).toBeDisabled()
  })

  // On localhost the fetch is a blink and none of this is visible. On a shop's
  // connection it is the whole experience, and a disabled button on its own
  // leaves the operator unsure the press registered.
  it('shows the rows that are arriving, in the place they will arrive', () => {
    const { container } = renderLedger({ loadedCount: 25, totalOrders: 60, hasMore: true, isLoadingMore: true })

    const pending = container.querySelector('.db-repair-orders-ledger__pending')
    expect(pending).toBeInTheDocument()
    expect(container.querySelectorAll('.db-repair-orders-ledger__skeleton')).toHaveLength(3)
    // Placeholders carry no information, so they must not be announced as rows.
    expect(pending).toHaveAttribute('aria-hidden', 'true')
  })

  it('renders no placeholders when nothing is loading', () => {
    const { container } = renderLedger({ loadedCount: 25, totalOrders: 60, hasMore: true })

    expect(container.querySelectorAll('.db-repair-orders-ledger__skeleton')).toHaveLength(0)
  })

  // No progress bar: the line already says "25 of 2737 loaded". A bar restates
  // that same ratio a third way, and at 25 of 2737 it renders as a sliver that
  // reads as empty rather than as one percent.
  it('states the counts once, without a bar restating them', () => {
    renderLedger({ loadedCount: 25, totalOrders: 60, hasMore: true })

    expect(screen.getByText('25 of 60 loaded')).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('uses the canonical focus-safe staff search field', () => {
    renderLedger()

    const search = screen.getByRole('searchbox', { name: 'Search repair orders' })
    expect(search.closest('.db-staff-search-field')).not.toBeNull()
    expect(search.closest('.db-staff-search-field-inset')).toHaveClass('db-repair-orders-new__search')
    expect(LEDGER_CSS).toContain('border: 1px solid var(--workspace-muted) !important')
    expect(LEDGER_CSS).toContain('width: 20px; height: 20px')
  })

  it('aligns the selected-record header and filter controls to shared dimensions', () => {
    expect(LEDGER_CSS).toContain('--db-repair-orders-control-height: 44px')
    expect(LEDGER_CSS).toContain('--db-repair-orders-side-control-width: 184px')
    expect(LEDGER_CSS).toContain('.db-presentation-new .db-repair-orders-new__search { height: var(--db-repair-orders-control-height); align-self: stretch; padding: 0; }')
    expect(LEDGER_CSS).toContain('.db-repair-orders-new__status-select { position: relative; display: none; min-width: 0; height: var(--db-repair-orders-control-height); }')
    expect(LEDGER_CSS).toContain('grid-template-columns: minmax(0, 1fr) var(--db-repair-orders-side-control-width)')
    expect(LEDGER_CSS).toContain('width: var(--db-repair-orders-side-control-width); min-height: var(--db-repair-orders-control-height); margin-inline-end: 3px')
    expect(LEDGER_CSS).toContain('.db-repair-orders-new__create { width: 100%; margin-top: 13px; }')
  })

  it('keeps Details in the navigator and opens the workspace only from the record or explicit secondary action', async () => {
    const user = userEvent.setup()
    const { props } = renderLedger()
    const details = screen.getByRole('button', { name: 'Show details for RO-1017' })

    await user.click(details)
    expect(props.onOpenOrder).not.toHaveBeenCalled()

    const openRecord = screen.getByRole('button', { name: 'Open repair order RO-1017' })
    await user.click(openRecord)
    expect(props.onOpenOrder).toHaveBeenLastCalledWith('ro-real-17')
    openRecord.focus()
    await user.keyboard('{Enter}')
    expect(props.onOpenOrder).toHaveBeenCalledTimes(2)
    expect(props.onOpenOrder).toHaveBeenLastCalledWith('ro-real-17', { focusWorkspace: true })
  })

  it('removes a closed brief from the document once its exit has played', async () => {
    const user = userEvent.setup()
    renderLedger()

    await user.click(screen.getByRole('button', { name: 'Show details for RO-1017' }))
    expect(screen.getByRole('region', { name: 'Order brief for RO-1017' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Hide details for RO-1017' }))
    // It stays mounted to play the exit, but stops being announced while it does.
    const closing = document.querySelector('.db-repair-orders-ledger__brief-reveal')
    expect(closing).toHaveAttribute('data-closing')
    expect(closing).toHaveAttribute('aria-hidden', 'true')

    // transitionend never fires under jsdom, so this also proves the floor that
    // guarantees the brief leaves even when the event is missed.
    await waitFor(() => {
      expect(screen.queryByRole('region', { name: 'Order brief for RO-1017' })).not.toBeInTheDocument()
    }, { timeout: 2000 })
  })

  it('keeps the disclosure plane inert and protects Details from canonical row activation', async () => {
    const user = userEvent.setup()
    const { props } = renderLedger()
    const details = screen.getByRole('button', { name: 'Show details for RO-1017' })

    await user.click(details)
    const brief = screen.getByRole('region', { name: 'Order brief for RO-1017' })
    await user.click(brief)
    expect(props.onOpenOrder).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Open repair order RO-1017 from details' }))
    expect(props.onOpenOrder).toHaveBeenCalledTimes(1)
    expect(props.onOpenOrder).toHaveBeenLastCalledWith('ro-real-17')
  })

  it('keeps canonical status wording in a single-line chip associated with order identity', () => {
    renderLedger({ rows: [{ ...rows[0], status: 'Authorization Pending' }] })

    const row = screen.getByRole('article', { name: 'Repair order RO-1017' })
    const identity = row.querySelector('.db-repair-orders-ledger__order-line')
    const status = within(row).getByText('Authorization Pending')
    expect(identity).toContainElement(status)
    expect(LEDGER_CSS).toContain('white-space: nowrap')
    expect(LEDGER_CSS).toContain('width: max-content')
    expect(LEDGER_CSS).toContain('min-height: 20px')
  })

  it('keeps pointer disclosure separate from the keyboard focus affordance', async () => {
    const user = userEvent.setup()
    renderLedger()
    const ledger = screen.getByRole('region', { name: 'Repair order ledger' })
    const details = screen.getByRole('button', { name: 'Show details for RO-1017' })

    await user.click(details)
    expect(ledger).toHaveAttribute('data-pointer-interaction', 'true')

    details.focus()
    await user.keyboard('{Tab}')
    expect(ledger).not.toHaveAttribute('data-pointer-interaction')
  })

  it('keeps collapsed records to their operational overview without duplicating the work request', () => {
    renderLedger({ selectedId: 'ro-real-17' })

    const row = screen.getByRole('article', { name: 'Repair order RO-1017' })
    expect(row).toHaveAttribute('data-selected', 'true')
    expect(row).toHaveTextContent('RO-1017')
    expect(row).toHaveTextContent('In Progress')
    expect(row).toHaveTextContent('$4,280.50')
    expect(row).toHaveTextContent('Aug 12, 3:00 PM')
    // The request is not previewed on the row: truncated to a single narrow
    // column it said less than nothing, and the brief right beneath carries it
    // in full.
    expect(row).not.toHaveTextContent('Diagnose intermittent no-start with a deliberately long source description')
    expect(screen.getByRole('region', { name: 'Scrollable repair-order results' })).toHaveAttribute('tabindex', '0')
    // The shop identifies work by customer and truck, so a collapsed row leads
    // with both and keeps the order number as reference. The work request still
    // belongs to the expanded brief, which the assertion above guards.
    expect(row).toHaveTextContent('Northline Logistics')
    expect(row).toHaveTextContent('2022 Freightliner Cascadia · Unit 218')
  })

  it('keeps the daily Shop Work navigator compact without hiding operational overview facts', () => {
    renderLedger({
      compact: true,
      queueOrigin: null,
      sectionTitle: 'Needs Action · today',
    })

    const row = screen.getByRole('article', { name: 'Repair order RO-1017' })
    expect(screen.getByRole('heading', { name: 'Needs Action · today' })).toBeInTheDocument()
    expect(row).toHaveTextContent('In Progress')
    expect(row).toHaveTextContent('$4,280.50')
    expect(row).toHaveTextContent('Aug 12, 3:00 PM')
    // The request is not previewed on the row: truncated to a single narrow
    // column it said less than nothing, and the brief right beneath carries it
    // in full.
    expect(row).not.toHaveTextContent('Diagnose intermittent no-start with a deliberately long source description')
    expect(screen.queryByRole('group', { name: 'Filter repair orders by status' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Order status')).not.toBeInTheDocument()
  })

  it('reveals one source-projected order brief at a time without changing the selected workspace', async () => {
    const user = userEvent.setup()
    const secondRow: RepairOrdersLedgerRow = {
      ...rows[0],
      id: 'ro-real-18',
      orderNumber: 'RO-1018',
      customerName: 'Allied Freight',
    vehicleYear: 2024,
    vehicleMake: 'Volvo',
    vehicleModel: 'VNL 760',
    vehicleUnitNumber: '402',
      description: 'Replace air dryer cartridge',
      total: '$680.00',
      quoteSent: false,
    }
    const { props } = renderLedger({ rows: [...rows, secondRow], totalOrders: 2, selectedId: 'ro-real-17' })

    await user.click(screen.getByRole('button', { name: 'Show details for RO-1018' }))
    const brief = screen.getByRole('region', { name: 'Order brief for RO-1018' })
    // The brief carries only what the row cannot: the full request and the
    // operational facts. Customer and vehicle title the row, so repeating them
    // here split the card into columns too narrow to hold "VOLVO TRUCK".
    expect(within(brief).queryByRole('region', { name: 'Vehicle' })).not.toBeInTheDocument()
    expect(brief).not.toHaveTextContent('Unit number')
    expect(screen.getByRole('article', { name: 'Repair order RO-1018' })).toHaveTextContent('2024 Volvo VNL 760 · Unit 402')
    expect(brief).toHaveTextContent('Work requested')
    expect(brief).toHaveTextContent('Replace air dryer cartridge')
    expect(brief).toHaveTextContent('Not sent')
    expect(within(brief).queryByText('Repair order')).not.toBeInTheDocument()
    expect(within(brief).queryByText('Order status')).not.toBeInTheDocument()
    expect(within(brief).queryByText('Updated')).not.toBeInTheDocument()
    expect(within(brief).queryByText('Order total')).not.toBeInTheDocument()
    expect(screen.getAllByText('Replace air dryer cartridge')).toHaveLength(1)
    expect(props.onOpenOrder).not.toHaveBeenCalled()
    expect(screen.getByRole('article', { name: 'Repair order RO-1017' })).toHaveAttribute('data-selected', 'true')
    expect(screen.getByRole('article', { name: 'Repair order RO-1017' })).not.toHaveAttribute('data-inspected')
    expect(screen.getByRole('article', { name: 'Repair order RO-1018' })).toHaveAttribute('data-inspected', 'true')

    // The selected row offers no brief of its own: the workspace beside the list
    // is already that order's detail, so a second copy on the row repeated the
    // customer, truck and work request rather than adding anything.
    expect(screen.queryByRole('button', { name: 'Show details for RO-1017' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Order brief for RO-1017' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open repair order RO-1017 from details' })).not.toBeInTheDocument()
    // Inspecting another row still works and still leaves the selection alone.
    expect(screen.getByRole('region', { name: 'Order brief for RO-1018' })).toBeInTheDocument()
    expect(screen.getByRole('article', { name: 'Repair order RO-1017' })).toHaveAttribute('data-selected', 'true')
  })

  it('omits the Vehicle group when no safe vehicle fact is present', async () => {
    const user = userEvent.setup()
    const noVehicleRow: RepairOrdersLedgerRow = {
      ...rows[0],
      id: 'ro-real-19',
      orderNumber: 'RO-1019',
      vehicleYear: null,
      vehicleMake: null,
      vehicleModel: null,
      vehicleUnitNumber: null,
      vehicleInfo: null,
    }
    renderLedger({ rows: [noVehicleRow] })

    await user.click(screen.getByRole('button', { name: 'Show details for RO-1019' }))
    const brief = screen.getByRole('region', { name: 'Order brief for RO-1019' })
    expect(within(brief).queryByRole('region', { name: 'Vehicle' })).not.toBeInTheDocument()
  })

  it('falls back to the raw vehicle label on the row when no structured fields exist', async () => {
    const user = userEvent.setup()
    const fallbackVehicleRow: RepairOrdersLedgerRow = {
      ...rows[0],
      id: 'ro-real-20',
      orderNumber: 'RO-1020',
      vehicleYear: null,
      vehicleMake: null,
      vehicleModel: null,
      vehicleUnitNumber: null,
      vehicleInfo: '2020 Volvo VNL 760',
    }
    renderLedger({ rows: [fallbackVehicleRow] })

    // With no structured year/make/model the row falls back to the raw label,
    // and it reads on the row rather than in a Vehicle block inside the brief.
    const row = screen.getByRole('article', { name: 'Repair order RO-1020' })
    expect(row).toHaveTextContent('2020 Volvo VNL 760')
    await user.click(screen.getByRole('button', { name: 'Show details for RO-1020' }))
    expect(screen.queryByRole('region', { name: 'Vehicle' })).not.toBeInTheDocument()
    expect(screen.getAllByText('2020 Volvo VNL 760')).toHaveLength(1)
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
    const trigger = screen.getByRole('button', { name: 'Order status' })

    // The trigger states the active filter without being opened.
    expect(trigger).toHaveTextContent('All')

    fireEvent.click(trigger)
    const list = screen.getByRole('listbox', { name: 'Order status options' })
    for (const option of statusOptions) {
      expect(quickFilterGroup).toContainElement(screen.getByRole('button', { name: option.label }))
      expect(within(list).getByRole('option', { name: option.label })).toBeInTheDocument()
    }
    expect(within(list).getByRole('option', { name: 'All' })).toHaveAttribute('aria-selected', 'true')
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
