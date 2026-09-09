import { useState, type ComponentProps } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import FleetBoard from '../FleetBoard'
vi.mock('../FleetActivity', () => ({ default: () => <div>Recent activity</div> }))

it('offers one repair-order entry and keeps age separate from Open/Closed state', async () => {
  function Board() {
    const [filter, setFilter] = useState<ComponentProps<typeof FleetBoard>['filter']>('all')
    return <FleetBoard data={{ trucks: [], stats: { total: 0, active: 0, shop: 0, pm: 0, parts: 0, open_wo: 0, incidents_total: 0 } }} onOpen={vi.fn()} onOpenRepairOrder={vi.fn()} filter={filter} setFilter={setFilter} query="" setQuery={vi.fn()} sort="attention" setSort={vi.fn()} />
  }
  render(<QueryClientProvider client={new QueryClient()}><Board /></QueryClientProvider>)
  expect(screen.queryByText('Repair orders to close')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('tab', { name: 'Activity' }))
  await userEvent.click(screen.getByRole('button', { name: /Repair orders/ }))
  expect(screen.getByRole('tab', { name: 'Open', exact: true })).toHaveAttribute('aria-selected', 'true')
  await userEvent.click(screen.getByRole('button', { name: /Open 3\+ days/ }))
  expect(screen.getByRole('button', { name: /Open 3\+ days/ })).toHaveAttribute('aria-pressed', 'true')
  await userEvent.click(screen.getByRole('tab', { name: 'Closed', exact: true }))
  expect(screen.getByLabelText('Truck')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Open 3\+ days/ })).not.toBeInTheDocument()
})
