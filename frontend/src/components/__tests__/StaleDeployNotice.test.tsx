import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { markStaleDeploy, resetStaleDeploy } from '../../lib/staleDeploy'
import StaleDeployNotice from '../StaleDeployNotice'

describe('stale deploy notice', () => {
  afterEach(() => { cleanup(); resetStaleDeploy(); vi.restoreAllMocks() })

  it('stays out of the way until a stale deploy is detected', () => {
    render(<StaleDeployNotice />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('explains that a new version shipped without blaming the user', () => {
    markStaleDeploy()
    render(<StaleDeployNotice />)
    expect(screen.getByRole('status')).toHaveTextContent('A new version of DieselBridge is available')
    expect(screen.getByRole('status')).not.toHaveTextContent(/error|failed|expired/i)
  })

  it('reloads the page when the reload action is taken', () => {
    const reload = vi.fn()
    vi.spyOn(window, 'location', 'get').mockReturnValue({ ...window.location, reload } as Location)
    markStaleDeploy()
    render(<StaleDeployNotice />)
    fireEvent.click(screen.getByRole('button', { name: 'Reload now' }))
    expect(reload).toHaveBeenCalledTimes(1)
  })
})
