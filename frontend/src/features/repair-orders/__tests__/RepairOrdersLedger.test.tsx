import { render, screen, waitFor, within } from '@testing-library/react'
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
    await user.selectOptions(screen.getByLabelText('Order status'), 'in_progress')
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
    await user.click(screen.getByRole('button', { name: 'Next repair-order page' }))
    expect(props.onNextPage).toHaveBeenCalledOnce()
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

  it('keeps the disclosure plane inert and protects Details from canonical row activation', async () => {
    const user = userEvent.setup()
    const { props } = renderLedger()
    const details = screen.getByRole('button', { name: 'Show details for RO-1017' })

    await user.click(details)
    const brief = screen.getByRole('region', { name: 'Order brief for RO-1017' })
    await user.click(within(brief).getByText('Diagnose intermittent no-start with a deliberately long source description'))
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
    const vehicle = within(brief).getByRole('region', { name: 'Vehicle' })
    expect(brief).toHaveTextContent('Allied Freight')
    expect(vehicle).toHaveTextContent('Year')
    expect(vehicle).toHaveTextContent('2024')
    expect(vehicle).toHaveTextContent('Make')
    expect(vehicle).toHaveTextContent('Volvo')
    expect(vehicle).toHaveTextContent('Model')
    expect(vehicle).toHaveTextContent('VNL 760')
    expect(vehicle).toHaveTextContent('Unit number')
    expect(vehicle).toHaveTextContent('402')
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

    await user.click(screen.getByRole('button', { name: 'Show details for RO-1017' }))
    expect(screen.queryByRole('region', { name: 'Order brief for RO-1018' })).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Order brief for RO-1017' })).toHaveTextContent('Northline Logistics')
    expect(screen.getByRole('article', { name: 'Repair order RO-1017' })).toHaveAttribute('data-selected', 'true')
    expect(screen.getByRole('article', { name: 'Repair order RO-1017' })).toHaveAttribute('data-inspected', 'true')
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

  it('renders an unstructured vehicle fallback once beneath the Vehicle heading', async () => {
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

    await user.click(screen.getByRole('button', { name: 'Show details for RO-1020' }))
    const vehicle = screen.getByRole('region', { name: 'Vehicle' })
    expect(within(vehicle).getByRole('heading', { name: 'Vehicle' })).toBeInTheDocument()
    expect(within(vehicle).getByText('2020 Volvo VNL 760')).toBeInTheDocument()
    expect(within(vehicle).queryByText('Vehicle', { selector: 'dt' })).not.toBeInTheDocument()
    expect(within(vehicle).queryByRole('term')).not.toBeInTheDocument()
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
