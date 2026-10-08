import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import SourceFuel from '../SourceFuel'
import type { FuelDaily } from '../fuelDaily'
const record: FuelDaily = { vehicle_id: 'a', report_date: '2026-10-05', source_timezone: null, timezone_status: 'unverified', driving_fuel_gallons: 0, idling_fuel_gallons: null, reported_total_fuel_gallons: null, source_distance_miles: 0, source_driving_seconds: 0, source_idling_seconds: null }
describe('reported fuel states', () => {
  it('shows fleet medians separately from the total report detail', async () => {
    render(<SourceFuel records={[record, { ...record, vehicle_id: 'b', driving_fuel_gallons: 20, idling_fuel_gallons: 4 }]} medianVehicleIds={['a', 'b', 'missing']} />)
    expect(screen.getByText('Driving median')).toBeVisible()
    expect(screen.getByText('Idling median')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Fleet fuel median: 10 gallons driving, 4 gallons idling' }))
    expect(screen.getByRole('dialog')).toHaveTextContent('driving from 2 trucks; idling from 1 truck')
    expect(screen.getByRole('dialog')).toHaveTextContent('Driving fuel20 gal')
  })
  it('labels an absent report without making up zeros', () => {
    render(<SourceFuel records={[]} />)
    expect(screen.getByText('No fuel report')).toBeVisible()
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })
  it('distinguishes reported zero from a missing component', async () => {
    render(<SourceFuel records={[record]} />)
    await userEvent.click(screen.getByRole('button', { name: 'Motive fuel details: 0 gallons driving, Not reported idling' }))
    expect(screen.getByRole('dialog')).toHaveTextContent('Driving fuel0 gal')
    expect(screen.getByRole('dialog')).toHaveTextContent('Idling fuelNot reported')
    expect(screen.getByRole('dialog')).not.toHaveTextContent('Not reported gal')
  })
  it('labels component totals with missing report dates as partial', () => {
    render(<SourceFuel records={[record, { ...record, report_date: '2026-10-06', driving_fuel_gallons: null, idling_fuel_gallons: 2 }]} />)
    expect(screen.getByText('Driving · partial')).toBeVisible()
    expect(screen.getByText('Idling · partial')).toBeVisible()
  })
})
