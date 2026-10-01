import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TruckTelemetryLocation, TruckTelemetryValue } from '../TruckTelemetry'
import type { BoardTruck } from '../types'
const source = { source: 'motive_dashboard_manual' as const, observed_at: null, captured_at: new Date().toISOString(), freshness: 'unknown' as const, snapshot_id: 'test', source_age_text: '12s ago' }
const truck = { telemetry: { speed: { ...source, value: 0, unit: 'mph', basis: null }, location: { ...source, lat: null, lng: null, label: 'Test town' }, odometer: { ...source, value: 100, unit: 'mi', basis: 'virtual' } } } as BoardTruck

describe('truck header readings', () => {
  it('shows zero and only capture time on tap; Escape and outside pointer dismiss', () => {
    render(<TruckTelemetryValue truck={truck} field="speed" label="Speed" />)
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
})
