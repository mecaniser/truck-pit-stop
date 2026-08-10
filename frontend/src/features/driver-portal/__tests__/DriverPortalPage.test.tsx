import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}))

vi.mock('../../../lib/api', () => ({ default: apiMocks }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

import DriverPortalPage from '../DriverPortalPage'

const profile = { id: 'driver-1', first_name: 'Andre', last_name: 'Wilson' }
const equipment = {
  asset_id: 'asset-1', custody_session_id: 'custody-1', custody_status: 'active',
  equipment_role: 'power_unit', vehicle_id: 'vehicle-1', unit_number: 'TPS-105',
  vin: '1FUJGGOE85E7H470E', make: 'International', model: 'LT 625', year: 2023,
  odometer: 751_604,
}
const emptyScorecard = {
  custody_miles: 0, incidents_during_custody: 0, finalized_reviews: 0,
  confirmed_driver_duty_issues: 0, not_attributable_findings: 0,
  disputed_or_pending_reviews: 0, scoring_ready: false,
}

function mockHome(overrides: Record<string, unknown> = {}) {
  const assignedEquipment = [{ ...equipment, ...overrides }]
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/fleet-identity/me') return Promise.resolve({ data: profile })
    if (url === '/fleet-identity/me/equipment') return Promise.resolve({ data: assignedEquipment })
    if (url === '/fleet-identity/me/inspections') return Promise.resolve({ data: [] })
    if (url === '/fleet-identity/me/incidents') return Promise.resolve({ data: [] })
    if (url === '/fleet-identity/me/scorecard') return Promise.resolve({ data: emptyScorecard })
    return Promise.reject(new Error(`Unexpected GET ${url}`))
  })
}

function renderRoute(path = '/driver') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/driver/*" element={<DriverPortalPage />} /></Routes>
    </MemoryRouter>,
  )
}

describe('Driver Workspace shape and hardening', () => {
  afterEach(() => {
    Object.values(apiMocks).forEach((mock) => mock.mockReset())
    document.body.style.overflow = ''
  })

  it('gates PTI and incident actions until custody is confirmed', async () => {
    mockHome()
    renderRoute()

    expect(await screen.findByRole('button', { name: 'Confirm this equipment' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start PTI' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Report incident' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Your operating record starts here' })).toBeInTheDocument()
    expect(screen.queryByText('Custody miles')).not.toBeInTheDocument()
  })

  it('reveals the operational actions after custody confirmation', async () => {
    mockHome({ custody_acknowledged_at: '2026-08-10T12:00:00Z' })
    renderRoute()

    expect(await screen.findByRole('button', { name: 'Start PTI' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Report incident' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirm this equipment' })).not.toBeInTheDocument()
  })

  it('shows a truthful load failure with a working retry', async () => {
    const user = userEvent.setup()
    apiMocks.get.mockRejectedValue(new Error('offline'))
    renderRoute()

    expect(await screen.findByRole('heading', { name: 'Driver Workspace unavailable' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'No equipment assigned' })).not.toBeInTheDocument()

    mockHome({ custody_acknowledged_at: '2026-08-10T12:00:00Z' })
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'Unit TPS-105' })).toBeInTheDocument()
  })

  it('protects incident input, reports an inline failure, and restores focus on close', async () => {
    const user = userEvent.setup()
    mockHome({ custody_acknowledged_at: '2026-08-10T12:00:00Z' })
    apiMocks.post.mockRejectedValue({ response: { data: { detail: 'Fleet service is temporarily unavailable' } } })
    renderRoute()

    const reportButton = await screen.findByRole('button', { name: 'Report incident' })
    await user.click(reportButton)
    const description = screen.getByLabelText('What happened?')
    await waitFor(() => expect(description).toHaveFocus())
    expect(document.body.style.overflow).toBe('hidden')

    await user.type(description, 'Air line is leaking at the trailer connection')
    await user.click(screen.getByRole('button', { name: 'Send incident report' }))
    expect(await screen.findByText('Fleet service is temporarily unavailable')).toBeInTheDocument()
    expect(description).toHaveValue('Air line is leaking at the trailer connection')

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Report an incident' })).not.toBeInTheDocument()
    expect(document.body.style.overflow).toBe('')
    expect(reportButton).toHaveFocus()
  })

  it('requires a condition note for a failed PTI check', async () => {
    const user = userEvent.setup()
    const pendingInspection = {
      id: 'inspection-1', vehicle_id: 'vehicle-1', status: 'scheduled',
      vehicle_unit_number: 'TPS-105', vehicle_make: 'International', vehicle_model: 'LT 625',
      odometer: 751_604,
      items: [{ id: 'item-1', category: 'Brakes', label: 'Service brake', result: 'pending', note: null }],
    }
    const failedInspection = {
      ...pendingInspection,
      items: [{ ...pendingInspection.items[0], result: 'fail' }],
    }
    apiMocks.get.mockResolvedValue({ data: pendingInspection })
    apiMocks.patch.mockResolvedValue({ data: failedInspection })
    renderRoute('/driver/inspections/inspection-1')

    await user.click(await screen.findByRole('button', { name: 'Fail' }))
    const submit = screen.getByRole('button', { name: 'Confirm and submit PTI' })
    expect(screen.getByLabelText('What is wrong?')).toBeInTheDocument()
    expect(submit).toBeDisabled()

    await user.type(screen.getByLabelText('What is wrong?'), 'Air pressure drops during hold test')
    await waitFor(() => expect(submit).toBeEnabled())
  })

  it('shows a retry state when a PTI cannot be opened', async () => {
    apiMocks.get.mockRejectedValue({ response: { data: { detail: 'Inspection not found' } } })
    renderRoute('/driver/inspections/missing')

    expect(await screen.findByRole('heading', { name: 'PTI unavailable' })).toBeInTheDocument()
    expect(screen.getByText('Inspection not found')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
