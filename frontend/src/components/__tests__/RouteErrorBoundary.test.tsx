import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { resetStaleDeploy, useStaleDeploy } from '../../lib/staleDeploy'
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
