import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TruckTelemetryLocation, TruckTelemetryValue } from '../TruckTelemetry'
import type { BoardTruck } from '../types'
const source = { source: 'motive_dashboard_manual' as const, observed_at: null, captured_at: new Date().toISOString(), freshness: 'unknown' as const, snapshot_id: 'test', source_age_text: '12s ago' }
const truck = { telemetry: { speed: { ...source, value: 0, unit: 'mph', basis: null }, location: { ...source, lat: null, lng: null, label: 'Test town' }, odometer: { ...source, value: 100, unit: 'mi', basis: 'virtual' } } } as BoardTruck
afterEach(() => vi.useRealTimers())

describe('truck header readings', () => {
  it('shows fresh zero and capture time on tap; Escape and outside pointer dismiss', () => {
    const fresh = { ...truck, telemetry: { ...truck.telemetry!, speed: { ...truck.telemetry!.speed!, observed_at: new Date().toISOString() } } }
    render(<TruckTelemetryValue truck={fresh} field="speed" label="Speed" />)
    expect(screen.getByText('0 mph')).toBeInTheDocument()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Speed: reading information' })
    fireEvent.click(button)
    expect(screen.getByRole('tooltip').textContent).toBe(`Captured ${new Date(source.captured_at).toLocaleString()}`)
    fireEvent.keyDown(button, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    fireEvent.click(button); fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })
  it.each([null, 'invalid', new Date(Date.now() - 12 * 86400000).toISOString()])('shows unavailable for speed with observation %s', observed_at => {
    const unknown = { ...truck, telemetry: { ...truck.telemetry!, speed: { ...truck.telemetry!.speed!, value: 10, observed_at } } }
    render(<><TruckTelemetryValue truck={unknown} field="speed" label="Speed" /><TruckTelemetryLocation truck={unknown} /></>)
    expect(screen.getByLabelText('Speed unavailable')).toBeInTheDocument()
    expect(screen.queryByText('10 mph')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Speed: reading information' })).not.toBeInTheDocument()
    expect(screen.getByText('Test town')).toBeInTheDocument()
  })
  it('never infers zero from a missing speed', () => {
    render(<TruckTelemetryValue truck={{ ...truck, telemetry: { ...truck.telemetry!, speed: null } }} field="speed" label="Speed" />)
    expect(screen.getByLabelText('Speed unavailable')).toBeInTheDocument()
    expect(screen.queryByText('0 mph')).not.toBeInTheDocument()
  })
  it('expires an open current-speed tooltip when the observation becomes old', () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-15T14:00:00Z'))
    const fresh = { ...truck, telemetry: { ...truck.telemetry!, speed: { ...truck.telemetry!.speed!, value: 10, observed_at: new Date().toISOString() } } }
    render(<TruckTelemetryValue truck={fresh} field="speed" label="Speed" />)
    fireEvent.click(screen.getByRole('button', { name: 'Speed: reading information' }))
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(300000))
    expect(screen.getByText('10 mph')).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(30000))
    expect(screen.queryByText('10 mph')).not.toBeInTheDocument()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Speed unavailable')).toBeInTheDocument()
  })
  it('shows save age without presenting unknown observation time as live', () => {
    render(<TruckTelemetryLocation truck={truck} />)
    expect(screen.getByText(/Updated just now/)).toBeInTheDocument()
    expect(screen.queryByText(/live|fresh/i)).not.toBeInTheDocument()
  })
  it('omits absent or expired values and hides internal basis in the tooltip', () => {
    const view = render(<TruckTelemetryValue truck={truck} field="fuel" label="Fuel level" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    view.rerender(<TruckTelemetryValue truck={truck} field="odometer" label="Motive" />)
    fireEvent.click(screen.getByRole('button'))
    expect(screen.getByRole('tooltip').textContent).toBe(`Captured ${new Date(source.captured_at).toLocaleString()}`)
    view.rerender(<TruckTelemetryValue truck={{ telemetry: { speed: { ...truck.telemetry!.speed!, captured_at: '2020-01-01T00:00:00Z' } } } as BoardTruck} field="speed" label="Speed" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
  it('shows reported MPG with its period and touch-accessible capture time; zero is valid', () => {
    const mpgTruck = { telemetry: { fuel_economy: { ...source, value: 6.5, unit: 'mpg', basis: null, period: 'last_30_days' } } } as BoardTruck
    const view = render(<TruckTelemetryValue truck={mpgTruck} field="fuel_economy" label="Efficiency" />)
    expect(screen.getByText('6.5 MPG')).toBeInTheDocument()
    expect(screen.getByText('Last 30 days')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Efficiency: reading information' }))
    expect(screen.getByRole('tooltip')).toHaveTextContent(`Captured ${new Date(source.captured_at).toLocaleString()}`)
    mpgTruck.telemetry!.fuel_economy!.value = 0
    view.rerender(<TruckTelemetryValue truck={mpgTruck} field="fuel_economy" label="Efficiency" />)
    expect(screen.getByText('0 MPG')).toBeInTheDocument()
    view.rerender(<TruckTelemetryValue truck={truck} field="fuel_economy" label="Efficiency" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

})
