import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import DriverLoginPage from '../DriverLoginPage'

function renderDriverLogin(path = '/driver/login?tenant_id=tenant-1') {
  return render(<MemoryRouter initialEntries={[path]}><DriverLoginPage /></MemoryRouter>)
}

describe('DriverLoginPage', () => {
  it('provides a dedicated WorkOS driver entry without garage credentials', () => {
    renderDriverLogin()

    const entry = screen.getByRole('link', { name: 'Continue to Driver Portal' })
    expect(entry).toHaveAttribute('href', expect.stringContaining('/auth/workos/login?return_to=%2Fdriver'))
    expect(entry).toHaveAttribute('href', expect.stringContaining('tenant_id=tenant-1'))
    expect(screen.queryByLabelText(/email address/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument()
  })

  it('supports generic entry for an account with authoritative organization memberships', () => {
    renderDriverLogin('/driver/login')

    const entry = screen.getByRole('link', { name: 'Continue to Driver Portal' })
    expect(entry).toHaveAttribute('href', '/api/v1/auth/workos/login?return_to=%2Fdriver')
  })

  it('explains invitation-based access and driver tasks', () => {
    renderDriverLogin()

    expect(screen.getByText(/email address that received your invitation/i)).toBeInTheDocument()
    expect(screen.getByText(/complete your pre-trip inspection/i)).toBeInTheDocument()
    expect(screen.getByText(/without assigning fault/i)).toBeInTheDocument()
  })

  it('stops callback retry and explains identity review without exposing another account', () => {
    renderDriverLogin('/driver/login?reason=identity_review_required&tenant_id=tenant-1')

    expect(screen.getByRole('alert')).toHaveTextContent(/access needs review/i)
    expect(screen.getByText(/cannot be connected to the account you used/i)).toBeInTheDocument()
    expect(screen.getByText(/driver-controlled email/i)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Continue to Driver Portal' })).not.toBeInTheDocument()
  })

  it('explains stale one-time callbacks and offers a fresh tenant-bound sign-in', () => {
    renderDriverLogin('/driver/login?reason=workos_state_expired&tenant_id=tenant-1')

    expect(screen.getByRole('alert')).toHaveTextContent(/sign-in link has expired/i)
    expect(screen.getByRole('link', { name: 'Continue to Driver Portal' })).toHaveAttribute('href', expect.stringContaining('tenant_id=tenant-1'))
  })
})
