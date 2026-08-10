import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import DriverLoginPage from '../DriverLoginPage'

describe('DriverLoginPage', () => {
  it('provides a dedicated WorkOS driver entry without garage credentials', () => {
    render(<DriverLoginPage />)

    const entry = screen.getByRole('link', { name: 'Continue to Driver Portal' })
    expect(entry).toHaveAttribute('href', expect.stringContaining('/auth/workos/login?return_to=%2Fdriver'))
    expect(screen.queryByLabelText(/email address/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument()
  })

  it('explains invitation-based access and driver tasks', () => {
    render(<DriverLoginPage />)

    expect(screen.getByText(/email address that received your invitation/i)).toBeInTheDocument()
    expect(screen.getByText(/complete your pre-trip inspection/i)).toBeInTheDocument()
    expect(screen.getByText(/without assigning fault/i)).toBeInTheDocument()
  })
})
