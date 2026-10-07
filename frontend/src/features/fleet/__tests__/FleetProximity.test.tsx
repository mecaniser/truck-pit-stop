import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import FleetMap from '../FleetMap'
import type { BoardTruck } from '../types'
import { positionAge, recentPosition } from '../proximity'
import { roadCandidates } from '../roadProximity'
vi.mock('../FleetMapCanvas', () => ({ default: ({ onFocus }: { onFocus: (id: string) => void }) => <button onClick={() => onFocus('Near')}>Select map truck</button> }))

const now = new Date('2026-10-04T12:00:00Z').getTime()
function truck(id: string, longitude = 0, ageMinutes: number | null = 0): BoardTruck {
  return { id, unit_number: id, make: 'Test', model: 'Truck', status: 'available', pm_interval_miles: 10000, moving: false, open_work_order_count: 0, open_incident_count: 0,
    telemetry: { location: { lat: 0, lng: longitude, label: `${id} location`, observed_at: ageMinutes === null ? null : new Date(now - ageMinutes * 60000).toISOString(), captured_at: new Date(now).toISOString(), source: 'motive_api', freshness: 'fresh', snapshot_id: null, source_age_text: null }, speed: null, fuel: null, odometer: null, engine_hours: null, fault_count: null, motion: 'unknown' },
  }
}
const origin = { ...truck('Down'), status: 'out_of_service' as const }
const near = truck('Near', .1), old = truck('Old', .01, 60), undated = truck('Undated', .001, null)
const missing = { ...truck('Missing'), telemetry: null, lat: 0, lng: .001 }
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(now); vi.stubEnv('VITE_MAPBOX_TOKEN', 'test-token'); vi.stubGlobal('fetch', vi.fn(async (url: string) => {
  if (url.includes('/geocode/')) return { ok: true, json: async () => ({ features: [{ geometry: { coordinates: [.3, 0] } }] }) }
  if (url.includes('/directions/v5/')) return { ok: true, json: async () => ({ code: 'Ok', routes: [{ geometry: { type: 'LineString', coordinates: [[0, 0], [.1, .05], [.2, 0]] } }] }) }
  const points = new URL(url).pathname.split('/').pop()!.split(';').map(point => point.split(',').map(Number))
  const destinations = new URL(url).searchParams.get('destinations')!.split(';').map(index => points[Number(index)])
  return { ok: true, json: async () => ({ code: 'Ok', distances: [destinations.map(point => Math.abs(point[0] - points[0][0]) * 111000)], durations: [destinations.map(() => 600)] }) }
})) })
afterEach(() => { vi.useRealTimers(); vi.unstubAllEnvs(); vi.unstubAllGlobals() })

async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(251) }) }

describe('proximity eligibility', async () => {
  it('excludes old, unknown, absent and legacy positions by default', async () => {
    expect(roadCandidates([origin, old, undated, missing, near], origin, now, false).map(row => row.id)).toEqual(['Near'])
    expect(roadCandidates([old, undated, missing, near], origin, now, true).map(row => row.id)).toEqual(['Near', 'Old', 'Undated'])
    expect(positionAge(undated, now)).toBe('Time unknown')
    expect(positionAge(old, now)).toBe('Last known · 1h ago')
  })
  it('marks minute precision without changing freshness or unknown-time eligibility', () => {
    const minute = (age: number | null) => { const row = truck('Minute', 0, age); row.telemetry!.location!.observed_precision = 'minute'; return row }
    expect(positionAge(minute(5), now)).toBe('~5m ago')
    expect(positionAge(minute(60), now)).toBe('Last known · ~1h ago')
    expect(positionAge(minute(.5), now)).toBe('<1m ago')
    expect(positionAge(minute(null), now)).toBe('Time unknown')
    expect(positionAge(minute(-6), now)).toBe('No coordinates')
    expect(positionAge(minute(31 * 1440), now)).toBe('No coordinates')
    expect(recentPosition(minute(15), now)).toBe(true)
    expect(recentPosition(minute(15), now + 1)).toBe(false)
    for (const observed_precision of [undefined, null, 'second'] as const) {
      const row = minute(5); row.telemetry!.location!.observed_precision = observed_precision
      expect(positionAge(row, now)).toBe('5m ago')
    }
  })
  it('requires an eligible origin and never resurrects expired or invalid coordinates', async () => {
    expect(roadCandidates([near], old, now, false)).toEqual([])
    expect(roadCandidates([near], missing, now, true)).toEqual([])
    expect(roadCandidates([truck('Expired', .01, 31 * 1440), truck('Invalid', 181)], origin, now, true)).toEqual([])
    expect(recentPosition(truck('Boundary', 0, 15), now)).toBe(true)
    expect(recentPosition(truck('Boundary', 0, 15), now + 1)).toBe(false)
    expect(recentPosition(truck('Future', 0, -6), now)).toBe(false)
  })
})

describe('map workspace', async () => {
  it('selects in place, shows status, and opens details only on explicit action', async () => {
    const open = vi.fn()
    render(<FleetMap trucks={[origin, near, old, undated, missing]} onSelect={open} />)
    fireEvent.click(screen.getByRole('button', { name: /Down Out of service/ }))
    expect(screen.getByText('Comparing from')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include last-known' }))
    await settle()
    expect(screen.getAllByText('6.9 mi')).toHaveLength(2)
    expect(screen.queryByRole('button', { name: /Old Available/ })).not.toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Closest road route' })).getByText('10 min')).toBeInTheDocument()
    expect(open).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /Truck details/ }))
    expect(open).toHaveBeenCalledWith(origin)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include last-known' }))
    await settle()
    expect(screen.getByText('Time unknown')).toBeInTheDocument()
    expect(screen.getByTitle('Last known · 1h ago')).toBeInTheDocument()
  })
  it('expands nearest three, changes the comparison origin, and clears selection', async () => {
    render(<FleetMap focusId={origin.id} trucks={[origin, near, truck('Two', .2), truck('Three', .3), truck('Four', .4)]} />)
    await settle()
    expect(screen.queryByRole('button', { name: /Four.*Available/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show all 4' }))
    fireEvent.click(screen.getByRole('button', { name: /Four.*Available/ }))
    expect(screen.getByText('Four', { selector: '.proximity-unit' })).toBeInTheDocument()
    await settle()
    expect(screen.getByRole('button', { name: 'Show all 4' })).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(screen.getByRole('button', { name: 'Clear selected truck' }))
    expect(screen.getByText('Select a truck')).toBeInTheDocument()
  })
  it('keeps unlocated trucks searchable and never shows distance for an unlocated origin', async () => {
    render(<FleetMap focusId={origin.id} trucks={[origin, near, missing]} />)
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Missing' } })
    fireEvent.click(screen.getByRole('button', { name: /Missing Available/ }))
    expect(screen.getByText(/This truck has no verified coordinates/)).toBeInTheDocument()
    expect(screen.queryByText('6.9 mi')).not.toBeInTheDocument()
  })
  it('uses last-known positions by default and can restrict to recent positions', async () => {
    render(<FleetMap focusId={old.id} trucks={[old, near]} />)
    expect(screen.getByRole('checkbox')).toBeChecked()
    await settle()
    expect(screen.getByRole('button', { name: /Near.*Available/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox'))
    expect(screen.getByText(/position is old or undated/)).toBeInTheDocument()
  })
  it('ages out candidates and drops a selected truck removed from scope', async () => {
    const result = render(<FleetMap focusId={origin.id} trucks={[origin, truck('Aging', .1, 14.9)]} />)
    fireEvent.click(screen.getByRole('checkbox'))
    await settle()
    expect(screen.getAllByText('6.9 mi')).toHaveLength(2)
    act(() => vi.advanceTimersByTime(30000))
    expect(screen.queryByText('6.9 mi')).not.toBeInTheDocument()
    result.rerender(<FleetMap focusId={origin.id} trucks={[near]} />)
    expect(screen.getByText('Select a truck')).toBeInTheDocument()
    expect(screen.queryByText('Down')).not.toBeInTheDocument()
  })
  it('uses only supplied trucks and reflects refreshed coordinates', async () => {
    const result = render(<FleetMap trucks={[origin, near]} focusId={origin.id} />)
    expect(screen.queryByText('Old')).not.toBeInTheDocument()
    result.rerender(<FleetMap trucks={[origin, truck('Near', .2)]} focusId={origin.id} />)
    await settle()
    expect(within(screen.getByRole('region', { name: 'Closest road route' })).getByText('13.8 mi')).toBeInTheDocument()
  })
})

it('selects an individual map tag without a cluster chooser', () => {
  render(<FleetMap trucks={[origin, near]} />)
  fireEvent.click(screen.getByRole('button', { name: 'Select map truck' }))
  expect(screen.queryByRole('region', { name: 'Trucks in selected cluster' })).not.toBeInTheDocument()
  expect(screen.getByText('Near', { selector: '.proximity-unit' })).toBeInTheDocument()
})

 it('starts unselected, ranks from home, retains missing trucks and returns home after selection', async () => {
  render(<FleetMap trucks={[origin, near, missing]} homeAddress="416 Seaboard Drive, Matthews, NC" />)
  await settle()
  await settle()
  expect(screen.queryByText('Comparing from')).not.toBeInTheDocument()
  expect(screen.queryByText('To home')).not.toBeInTheDocument()
  expect(document.querySelector('.proximity-list-heading')).toBeNull()
  expect(screen.getByLabelText('Road distance to home color legend')).toHaveTextContent('Nearest to homeFarthest from home')
  const rows = document.querySelectorAll('.proximity-row')
  expect(rows[0]).toHaveTextContent('Near')
  expect(rows[1]).toHaveTextContent('Down')
  expect(rows[2]).toHaveTextContent('Missing')
  expect(rows[2].querySelector('.proximity-row-miles')).toBeNull()
  expect(screen.queryByText('416 Seaboard Drive, Matthews, NC')).not.toBeInTheDocument()
  expect(rows[0].querySelector('.proximity-row-miles')).toHaveStyle({ color: 'rgb(74, 222, 128)' })
  expect(rows[1].querySelector('.proximity-row-miles')).toHaveStyle({ color: 'rgb(248, 113, 113)' })
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Down' } })
  expect(document.querySelector('.proximity-row-miles')).toHaveStyle({ color: 'rgb(248, 113, 113)' })
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '' } })
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('/directions/v5/'))).toBe(false)
  fireEvent.click(document.querySelector('.proximity-row')!)
  expect(screen.queryByLabelText('Road distance to home color legend')).not.toBeInTheDocument()
  expect(screen.getByText('Comparing from')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Home', exact: true }))
  expect(screen.queryByText('Comparing from')).not.toBeInTheDocument()
 })
 it('keeps all trucks available when home lookup fails', async () => {
  vi.mocked(fetch).mockRejectedValue(new Error('offline'))
  render(<FleetMap trucks={[origin, missing]} homeAddress="Unresolved home" />)
  await settle()
  expect(screen.getByText('Home location unavailable')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Home', exact: true })).toBeDisabled()
  expect(document.querySelectorAll('.proximity-row')).toHaveLength(2)
  expect(document.querySelector('.proximity-row-miles')).toBeNull()
 })

it('shows shop to selected truck miles while keeping nearby trucks listed', async () => {
  render(<FleetMap trucks={[near, truck('Far', 1)]} focusId="Near" homeAddress="416 Seaboard Drive, Matthews, NC" />)
  await settle(); await settle()
  const summary = screen.getByRole('region', { name: 'Closest road route' })
  expect(summary).toHaveTextContent('Shop is closest')
  expect(summary).toHaveTextContent('Shop→Near')
  expect(summary).toHaveTextContent('13.8 mi')
  expect(screen.getByRole('button', { name: /Far Available/ })).toBeInTheDocument()
})

it('shows raw units and only cities for production-shaped labels', () => {
  const row = { ...origin, unit_number: '01', display_unit_number: '77 CARGO LLC 01', telemetry: { ...origin.telemetry!, location: { ...origin.telemetry!.location!, label: 'I 85, Belle Meade, SC 29605' } } }
  render(<FleetMap trucks={[row]} />)
  expect(screen.getByRole('button', { name: /01 Out of service Belle Meade/ })).toBeInTheDocument()
  expect(screen.queryByText('77 CARGO LLC 01')).not.toBeInTheDocument()
  expect(screen.queryByText(/I 85/)).not.toBeInTheDocument()
})
