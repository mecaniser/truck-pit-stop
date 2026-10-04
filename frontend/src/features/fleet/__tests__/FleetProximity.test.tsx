import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import FleetMap from '../FleetMap'
import type { BoardTruck } from '../types'
import { positionAge, recentPosition } from '../proximity'
import { roadCandidates } from '../roadProximity'
vi.mock('../FleetMapCanvas', () => ({ default: () => <div>Map fixture</div> }))

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
  if (url.includes('/directions/v5/')) return { ok: true, json: async () => ({ code: 'Ok', routes: [{ geometry: { type: 'LineString', coordinates: [[0, 0], [.1, .05], [.2, 0]] } }] }) }
  const points = new URL(url).pathname.split('/').pop()!.split(';').map(point => point.split(',').map(Number))
  return { ok: true, json: async () => ({ code: 'Ok', distances: [points.slice(1).map(point => Math.abs(point[0] - points[0][0]) * 111000)], durations: [points.slice(1).map(() => 600)] }) }
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
    await settle()
    expect(screen.getByText('6.9 mi')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Old Available/ })).not.toBeInTheDocument()
    expect(open).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /Truck details/ }))
    expect(open).toHaveBeenCalledWith(origin)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include last-known' }))
    await settle()
    expect(screen.getByText('Time unknown')).toBeInTheDocument()
    expect(screen.getByText('Last known · 1h ago')).toBeInTheDocument()
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
  it('permits old-origin comparison only after explicit last-known selection', async () => {
    render(<FleetMap focusId={old.id} trucks={[old, near]} />)
    expect(screen.getByText(/position is old or undated/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox'))
    await settle()
    expect(screen.getByRole('button', { name: /Near.*Available/ })).toBeInTheDocument()
  })
  it('ages out candidates and drops a selected truck removed from scope', async () => {
    const result = render(<FleetMap focusId={origin.id} trucks={[origin, truck('Aging', .1, 14.9)]} />)
    await settle()
    expect(screen.getByText('6.9 mi')).toBeInTheDocument()
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
    expect(screen.getByText('13.8 mi')).toBeInTheDocument()
  })
})
