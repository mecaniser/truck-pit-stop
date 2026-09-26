import { useState, type ComponentProps } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import FleetBoard from '../FleetBoard'
import type { BoardTruck } from '../types'

vi.mock('../FleetActivity', () => ({ default: () => <div>Recent activity</div> }))

/* Choosing "PM soonest" should order the whole board by PM urgency. The
   sections exist to triage the default view; once a manager names an order,
   splitting the list into sections contradicts it - a truck due today rendered
   below trucks due next week because it sat in a later section. */

function truck(over: Partial<BoardTruck> & { id: string; unit_number: string }): BoardTruck {
  return {
    make: 'Volvo', model: 'VNL', year: 2021, status: 'active', odometer: 500000,
    pm_interval_miles: 25000, moving: false, open_work_order_count: 0, open_incident_count: 0,
    display_unit_number: over.unit_number, ...over,
  } as BoardTruck
}

const fleet = [
  truck({ id: 'a', unit_number: 'OVERDUE-1D', pm_days_remaining: -1, pm_remaining: 500 }),
  truck({ id: 'b', unit_number: 'DUE-TODAY', pm_days_remaining: 0, pm_remaining: 20000 }),
  truck({ id: 'c', unit_number: 'DUE-7D', pm_days_remaining: 7, pm_remaining: 21000 }),
  truck({ id: 'd', unit_number: 'FAR', pm_days_remaining: 60, pm_remaining: 19000 }),
  truck({ id: 'e', unit_number: 'UNSCHEDULED' }),
]

const stats = { total: 5, active: 5, shop: 0, pm: 0, parts: 0, open_wo: 0, incidents_total: 0 }

function Board({ sort = 'pm', trucks = fleet }: { sort?: string; trucks?: BoardTruck[] }) {
  const [filter, setFilter] = useState<ComponentProps<typeof FleetBoard>['filter']>('all')
  return (
    <QueryClientProvider client={new QueryClient()}>
      <FleetBoard
        data={{ trucks, stats: { ...stats, total: trucks.length } }}
        onOpen={vi.fn()} onOpenRepairOrder={vi.fn()}
        filter={filter} setFilter={setFilter} query="" setQuery={vi.fn()}
        sort={sort as ComponentProps<typeof FleetBoard>['sort']} setSort={vi.fn()}
      />
    </QueryClientProvider>
  )
}

function renderedOrder() {
  return screen.getAllByRole('button', { name: /Open .* truck details/ })
    .map((el) => el.getAttribute('aria-label')!.replace('Open ', '').replace(' truck details', ''))
}

describe('PM soonest', () => {
  it('orders every truck by PM urgency, ignoring the triage sections', () => {
    render(<Board sort="pm" />)
    expect(renderedOrder()).toEqual(['OVERDUE-1D', 'DUE-TODAY', 'DUE-7D', 'FAR', 'UNSCHEDULED'])
  })

  it('does not split the board into sections when an order is named', () => {
    render(<Board sort="pm" />)
    expect(screen.queryByRole('heading', { name: 'Needs attention' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Maintenance to plan' })).not.toBeInTheDocument()
  })

  it('renders a truck due today above one due next week', () => {
    render(<Board sort="pm" />)
    const order = renderedOrder()
    expect(order.indexOf('DUE-TODAY')).toBeLessThan(order.indexOf('DUE-7D'))
  })

  it('keeps a truck that is in the shop in the list, in PM order', () => {
    const withShop = [...fleet, truck({ id: 'f', unit_number: 'IN-SHOP', status: 'shop', pm_days_remaining: 30, pm_remaining: 18000 })]
    render(<Board sort="pm" trucks={withShop} />)
    const order = renderedOrder()
    expect(order).toContain('IN-SHOP')
    // 30 days out: it must not float to the top just for being in the shop.
    expect(order.indexOf('DUE-TODAY')).toBeLessThan(order.indexOf('IN-SHOP'))
  })

  it('keeps the triage sections for the default attention sort', () => {
    render(<Board sort="attention" />)
    expect(screen.getByRole('heading', { name: 'Needs attention' })).toBeInTheDocument()
  })
})

describe('Truck card explains why it needs attention', () => {
  it('does not repeat the status badge as a tag', () => {
    // The badge already reads "In shop"; a second copy is noise, not signal.
    render(<Board sort="attention" trucks={[truck({ id: 's', unit_number: 'SHOP-1', status: 'shop', pm_remaining: 19000 })]} />)
    const card = screen.getByRole('button', { name: /Open SHOP-1 truck details/ })
    expect(within(card).getAllByText(/in shop/i)).toHaveLength(1)
  })

  it('tags a warning light, which nothing else on the card shows', () => {
    render(<Board sort="attention" trucks={[truck({ id: 'w', unit_number: 'WARN-1', warning_lights: ['check_engine'], pm_remaining: 19000 })]} />)
    const card = screen.getByRole('button', { name: /Open WARN-1 truck details/ })
    expect(within(card).getByText(/warning light/i)).toBeInTheDocument()
  })

  it('tags a truck with an open incident', () => {
    render(<Board sort="attention" trucks={[truck({ id: 'i', unit_number: 'INC-1', open_incident_count: 1, pm_remaining: 19000 })]} />)
    const card = screen.getByRole('button', { name: /Open INC-1 truck details/ })
    expect(within(card).getByText(/incident/i)).toBeInTheDocument()
  })

  it('does not tag a truck that is only due for PM', () => {
    render(<Board sort="attention" trucks={[truck({ id: 'p', unit_number: 'PM-1', pm_days_remaining: 0, pm_remaining: 20000 })]} />)
    const card = screen.getByRole('button', { name: /Open PM-1 truck details/ })
    expect(within(card).queryByText(/in shop|incident|warning/i)).not.toBeInTheDocument()
  })
})

describe('Truck card identity', () => {
  it('shows the company as the heading and the unit as the large mark', () => {
    render(<Board sort="attention" trucks={[truck({
      id: 'c', unit_number: '01', display_unit_number: '77 CARGO LLC 01',
      owner_company_name: '77 CARGO LLC', pm_remaining: 20000,
    } as Partial<BoardTruck> & { id: string; unit_number: string })]} />)
    const card = screen.getByRole('button', { name: /Open 77 CARGO LLC 01 truck details/ })
    expect(within(card).getByText('77 CARGO LLC')).toBeInTheDocument()
    // The unit sits beside the status badge, not appended to the company name.
    expect(within(card).getByTestId('tcard-unit-mark')).toHaveTextContent('01')
  })

  it('does not repeat the company inside the unit mark', () => {
    render(<Board sort="attention" trucks={[truck({
      id: 'c2', unit_number: '01', display_unit_number: '77 CARGO LLC 01',
      owner_company_name: '77 CARGO LLC', pm_remaining: 20000,
    } as Partial<BoardTruck> & { id: string; unit_number: string })]} />)
    const mark = screen.getByTestId('tcard-unit-mark')
    expect(mark.textContent).toBe('01')
  })

  it('still names the truck in full for assistive tech', () => {
    render(<Board sort="attention" trucks={[truck({
      id: 'c3', unit_number: '01', display_unit_number: '77 CARGO LLC 01',
      owner_company_name: '77 CARGO LLC', pm_remaining: 20000,
    } as Partial<BoardTruck> & { id: string; unit_number: string })]} />)
    expect(screen.getByRole('button', { name: 'Open 77 CARGO LLC 01 truck details' })).toBeInTheDocument()
  })

  it('shows only the unit when the truck has no company', () => {
    render(<Board sort="attention" trucks={[truck({
      id: 'c4', unit_number: 'W900', display_unit_number: 'W900', pm_remaining: 20000,
    } as Partial<BoardTruck> & { id: string; unit_number: string })]} />)
    expect(screen.getByTestId('tcard-unit-mark')).toHaveTextContent('W900')
    expect(screen.queryByTestId('tcard-company')).not.toBeInTheDocument()
  })
})
