import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '../../stores/authStore'
import { setSessionRecovering } from '../../lib/sessionRecovery'
import SessionRecoveryNotice from '../SessionRecoveryNotice'

const mocks = vi.hoisted(() => ({ renewSessionNow: vi.fn().mockResolvedValue(undefined) }))
vi.mock('../../lib/sessionKeepAlive', () => ({ ...mocks, startSessionKeepAlive: vi.fn(), stopSessionKeepAlive: vi.fn() }))

describe('session recovery notice', () => {
  afterEach(() => { cleanup(); setSessionRecovering(false); useAuthStore.setState({ isAuthenticated: false }); vi.clearAllMocks() })
  it('announces temporary recovery and offers retry without claiming logout', async () => {
    useAuthStore.setState({ isAuthenticated: true, logoutInProgress: false })
    setSessionRecovering(true)
    render(<SessionRecoveryNotice />)
    expect(screen.getByRole('status')).toHaveTextContent('We’ll retry automatically')
    expect(screen.getByRole('status')).not.toHaveTextContent(/expired|inactivity/i)
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Retry now' })) })
    expect(mocks.renewSessionNow).toHaveBeenCalledTimes(1)
    await screen.findByRole('button', { name: 'Retry now' })
  })
  it('does not show a recovery notice to a signed-out user', () => {
    useAuthStore.setState({ isAuthenticated: false })
    setSessionRecovering(true)
    render(<SessionRecoveryNotice />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
