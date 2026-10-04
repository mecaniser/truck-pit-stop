import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import FleetMapCanvas from '../FleetMapCanvas'
import type { BoardTruck } from '../types'

const mock = vi.hoisted(() => ({ pins: [] as { element: HTMLElement; point?: number[]; popup?: HTMLElement }[], fit: vi.fn(), lines: vi.fn(), remove: vi.fn(), markerRemove: vi.fn(), sources: new Set<string>(), handlers: {} as Record<string, () => void> }))
vi.mock('mapbox-gl', () => ({ default: {
  Map: class { on(event: string, cb: () => void) { mock.handlers[event] = cb; if (event === 'load') queueMicrotask(cb) } addControl() {} resize() {} fitBounds(...args: unknown[]) { mock.fit(...args) } getSource(id: string) { return mock.sources.has(id) ? { setData: mock.lines } : undefined } addSource(id: string, source: { data: unknown }) { mock.sources.add(id); mock.lines(source.data) } addLayer() {} remove() { mock.remove() } },
  Marker: class {
    pin: { element: HTMLElement; point?: number[]; popup?: HTMLElement }
    constructor({ element }: { element: HTMLElement }) { element.classList.add('mapboxgl-marker'); this.pin = { element }; mock.pins.push(this.pin) }
    setLngLat(point: number[]) { this.pin.point = point; return this }
    setPopup(popup: { content: HTMLElement }) { this.pin.popup = popup.content; return this }
    getPopup() { return { remove: vi.fn() } }
    addTo() { return this } remove() { mock.markerRemove(this.pin.element) }
  },
  Popup: class { content?: HTMLElement; setDOMContent(content: HTMLElement) { this.content = content; return this } },
  NavigationControl: class {}, LngLatBounds: class { extend() { return this } },
} }))
const now = Date.now()
function truck(id: string, lng: number, old = false) {
  return { id, unit_number: id, status: 'out_of_service', telemetry: { location: { lat: 0, lng, observed_at: new Date(now - (old ? 3600000 : 0)).toISOString(), captured_at: new Date(now).toISOString() } } } as BoardTruck
}
beforeEach(() => { mock.pins.length = 0; mock.sources.clear(); vi.clearAllMocks(); vi.stubEnv('VITE_MAPBOX_TOKEN', 'synthetic') })
afterEach(() => vi.unstubAllEnvs())
it('selects pins in place and draws supplied road geometry with status and stale styling', async () => {
  const select = vi.fn()
  render(<FleetMapCanvas trucks={[truck('Down', 0), truck('Old', 1, true)]} route={{ type: 'LineString', coordinates: [[0, 0], [.3, .4], [1, 0]] }} focusId="Down" nearbyIds={['Old']} now={now} recenter={0} onFocus={select} />)
  await waitFor(() => expect(mock.pins).toHaveLength(2))
  expect(mock.pins[0].element).toHaveClass('is-selected', 'mapboxgl-marker')
  expect(mock.pins[0].element).toHaveAccessibleName('Down, Out of service')
  expect(mock.pins[1].element).toHaveClass('is-last-known')
  fireEvent.click(mock.pins[1].element)
  expect(select).toHaveBeenCalledWith('Old')
  expect(mock.lines.mock.calls[0][0].features[0].geometry.coordinates).toEqual([[0, 0], [.3, .4], [1, 0]])
})
it('groups coincident pins without moving coordinates and lets each truck be selected', async () => {
  const select = vi.fn()
  render(<FleetMapCanvas trucks={[truck('A', 0), truck('B', 0)]} nearbyIds={[]} now={now} recenter={0} onFocus={select} />)
  await waitFor(() => expect(mock.pins).toHaveLength(1))
  expect(mock.pins[0].point).toEqual([0, 0])
  expect(mock.lines.mock.calls[0][0].features).toEqual([])
  expect(mock.pins[0].element).toHaveAccessibleName('2 trucks at this position')
  fireEvent.click(mock.pins[0].popup!.querySelectorAll('button')[1])
  expect(select).toHaveBeenCalledWith('B')
})
it('preserves viewport on location polling, recenters on demand and cleans up', async () => {
  const props = { trucks: [truck('A', 0)], nearbyIds: [], now, recenter: 0, onFocus: vi.fn() }
  const result = render(<FleetMapCanvas {...props} />)
  await waitFor(() => expect(mock.fit).toHaveBeenCalledTimes(1))
  result.rerender(<FleetMapCanvas {...props} trucks={[truck('A', 1)]} />)
  expect(mock.fit).toHaveBeenCalledTimes(1)
  result.rerender(<FleetMapCanvas {...props} recenter={1} />)
  expect(mock.fit).toHaveBeenCalledTimes(2)
  act(() => mock.handlers.error())
  expect(screen.getByRole('status')).toHaveTextContent('Map could not load')
  result.unmount()
  expect(mock.remove).toHaveBeenCalledTimes(1)
})

it('clears the previous road geometry immediately while recalculating', async () => {
  const props = { trucks: [truck('A', 0), truck('B', 1)], focusId: 'A', nearbyIds: ['B'], now, recenter: 0, onFocus: vi.fn() }
  const result = render(<FleetMapCanvas {...props} route={{ type: 'LineString', coordinates: [[0, 0], [.3, .4], [1, 0]] }} />)
  await waitFor(() => expect(mock.lines).toHaveBeenCalled())
  expect(mock.lines.mock.lastCall![0].features).toHaveLength(1)
  result.rerender(<FleetMapCanvas {...props} focusId="B" nearbyIds={[]} />)
  expect(mock.lines.mock.lastCall![0].features).toEqual([])
})

it('uses the supplied company mark only for matching trucks and keeps the unit label', async () => {
  render(<FleetMapCanvas trucks={[{ ...truck('77-A', 0), fleet_company_name: '77 CARGO LLC' }, { ...truck('Other', 1), fleet_company_name: 'Another fleet' }]} nearbyIds={[]} now={now} recenter={0} onFocus={vi.fn()} />)
  await waitFor(() => expect(mock.pins).toHaveLength(2))
  expect(mock.pins[0].element.querySelector('img')).toHaveAttribute('src', '/fleet/77-cargo-mark.svg')
  expect(mock.pins[0].element.querySelector('.proximity-pin-label')).toHaveTextContent('77-A')
  expect(mock.pins[1].element.querySelector('img')).toBeNull()
})

it('keeps marker DOM and camera stable through selection, loading and route results', async () => {
  const props = { trucks: [truck('A', 0), truck('B', 1)], focusId: 'A', nearbyIds: ['B'], now, recenter: 0, onFocus: vi.fn() }
  const result = render(<FleetMapCanvas {...props} />)
  await waitFor(() => expect(mock.pins).toHaveLength(2))
  const firstButton = mock.pins[0].element, firstBadge = firstButton.firstChild
  result.rerender(<FleetMapCanvas {...props} focusId="B" nearbyIds={[]} />)
  result.rerender(<FleetMapCanvas {...props} focusId="B" nearbyIds={['A']} route={{ type: 'LineString', coordinates: [[1, 0], [.5, .2], [0, 0]] }} />)
  expect(mock.pins).toHaveLength(2)
  expect(mock.markerRemove).not.toHaveBeenCalled()
  expect(mock.pins[0].element).toBe(firstButton)
  expect(firstButton.firstChild).toBe(firstBadge)
  expect(firstButton).toHaveClass('mapboxgl-marker')
  expect(firstButton).not.toHaveClass('is-selected')
  expect(mock.pins[1].element).toHaveClass('is-selected')
  expect(mock.fit).toHaveBeenCalledTimes(1)
  fireEvent.click(firstButton)
  expect(props.onFocus).toHaveBeenCalledWith('A')
  result.rerender(<FleetMapCanvas {...props} focusId="B" recenter={1} />)
  expect(mock.fit).toHaveBeenCalledTimes(2)
})
it('moves existing markers, removes only missing groups and reconciles coincident trucks', async () => {
  const props = { trucks: [truck('A', 0), truck('B', 1)], nearbyIds: [], now, recenter: 0, onFocus: vi.fn() }
  const result = render(<FleetMapCanvas {...props} />)
  await waitFor(() => expect(mock.pins).toHaveLength(2))
  result.rerender(<FleetMapCanvas {...props} trucks={[truck('A', .5), truck('B', 1)]} />)
  expect(mock.pins).toHaveLength(2)
  expect(mock.pins[0].point).toEqual([.5, 0])
  result.rerender(<FleetMapCanvas {...props} trucks={[truck('A', 1), truck('B', 1)]} />)
  expect(mock.pins).toHaveLength(3)
  expect(mock.markerRemove).toHaveBeenCalledTimes(2)
  expect(mock.pins[2].element).toHaveAccessibleName('2 trucks at this position')
  result.rerender(<FleetMapCanvas {...props} trucks={[truck('B', 1)]} />)
  expect(mock.markerRemove).toHaveBeenCalledTimes(3)
  expect(mock.pins).toHaveLength(4)
  expect(mock.fit).toHaveBeenCalledTimes(1)
  result.unmount()
  expect(mock.markerRemove).toHaveBeenCalledTimes(4)
})
