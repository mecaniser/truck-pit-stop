import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { markStaleDeploy, resetStaleDeploy, useStaleDeploy } from '../../lib/staleDeploy'
import RouteErrorBoundary from '../RouteErrorBoundary'
import StaleDeployNotice from '../StaleDeployNotice'

function Boom({ error }: { error: Error }): JSX.Element {
  throw error
}

describe('route error boundary', () => {
  beforeEach(() => { vi.spyOn(console, 'error').mockImplementation(() => {}) })
  afterEach(() => { cleanup(); resetStaleDeploy(); vi.restoreAllMocks() })

  it('renders its children when nothing throws', () => {
    render(<RouteErrorBoundary><p>the app</p></RouteErrorBoundary>)
    expect(screen.getByText('the app')).toBeInTheDocument()
  })

  it('flags a stale deploy when a route chunk is gone', () => {
    render(
      <RouteErrorBoundary>
        <Boom error={new TypeError('Failed to fetch dynamically imported module: /assets/MyGaragePage-BqMbfKJl.js')} />
      </RouteErrorBoundary>,
    )
    expect(useStaleDeploy.getState().stale).toBe(true)
  })

  it('offers a reload instead of leaving a blank page when a chunk is gone', () => {
    render(
      <RouteErrorBoundary>
        <Boom error={new TypeError('Failed to fetch dynamically imported module: /assets/MyGaragePage-BqMbfKJl.js')} />
      </RouteErrorBoundary>,
    )
    expect(screen.getByRole('button', { name: 'Reload now' })).toBeInTheDocument()
  })

  it('does not claim a new version shipped for an ordinary app crash', () => {
    render(<RouteErrorBoundary><Boom error={new Error('boom in module body')} /></RouteErrorBoundary>)
    expect(useStaleDeploy.getState().stale).toBe(false)
    expect(screen.queryByText(/A new version of DieselBridge is available/)).not.toBeInTheDocument()
  })

  it('still tells the person something went wrong on an ordinary app crash', () => {
    render(<RouteErrorBoundary><Boom error={new Error('boom in module body')} /></RouteErrorBoundary>)
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong')
  })
})

describe('stale deploy messaging is not duplicated', () => {
  beforeEach(() => { vi.spyOn(console, 'error').mockImplementation(() => {}) })
  afterEach(() => { cleanup(); resetStaleDeploy(); vi.restoreAllMocks() })

  it('shows the new-version message once when the boundary has taken over the page', () => {
    // Mirrors App.tsx: the notice is a sibling of the boundary, so it
    // survives the unmount and would otherwise say the same thing twice.
    render(
      <>
        <StaleDeployNotice />
        <RouteErrorBoundary>
          <Boom error={new TypeError('Failed to fetch dynamically imported module: /assets/MyGaragePage-BqMbfKJl.js')} />
        </RouteErrorBoundary>
      </>,
    )
    expect(screen.getAllByText('A new version of DieselBridge is available')).toHaveLength(1)
  })
})

describe('confirmed updates take priority over generic crashes', () => {
  beforeEach(() => { vi.spyOn(console, 'error').mockImplementation(() => {}) })
  afterEach(() => { cleanup(); resetStaleDeploy(); vi.restoreAllMocks() })

  it.each(['before', 'after'])('shows one working update reload when detected %s a generic crash', (timing) => {
    const reload = vi.fn()
    vi.spyOn(window, 'location', 'get').mockReturnValue({ ...window.location, reload } as Location)
    if (timing === 'before') markStaleDeploy()
    render(
      <>
        <StaleDeployNotice />
        <RouteErrorBoundary><Boom error={new Error('boom in module body')} /></RouteErrorBoundary>
      </>,
    )
    if (timing === 'after') {
      expect(screen.getByText('Something went wrong')).toBeInTheDocument()
      act(() => markStaleDeploy())
    }
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument()
    expect(screen.getAllByText('A new version of DieselBridge is available')).toHaveLength(1)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Anything you have typed but not saved will be lost.')
    fireEvent.click(screen.getByRole('button', { name: 'Reload now' }))
    expect(reload).toHaveBeenCalledTimes(1)
    expect(console.error).toHaveBeenCalledWith('Route render failed', expect.any(Error), expect.any(String))
  })

  it('keeps healthy routes visible when an update is available', () => {
    markStaleDeploy()
    render(<><StaleDeployNotice /><RouteErrorBoundary><p>the app</p></RouteErrorBoundary></>)
    expect(screen.getByText('the app')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('A new version of DieselBridge is available')
    expect(screen.getAllByRole('button', { name: 'Reload now' })).toHaveLength(1)
    expect(useStaleDeploy.getState().handled).toBe(false)
  })
})
