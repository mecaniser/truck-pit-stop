import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import TenantBrandLogo from '../components/brand/TenantBrandLogo'

describe('TenantBrandLogo', () => {
  it('renders the platform logo when no tenant logo exists', () => {
    render(<TenantBrandLogo tenantLogoUrl={null} alt="Diesel Bridge Network" />)

    const image = screen.getByRole('img', { name: 'Diesel Bridge Network' })
    expect(image.getAttribute('src')).toContain('/DB_bridge_logo_favi_figma_admin.png')
  })

  it('renders the tenant logo when a tenant logo url exists', () => {
    render(
      <TenantBrandLogo
        tenantLogoUrl="https://cdn.example.com/tenant-logo.png"
        tenantName="Truck Pit Stop"
      />
    )

    const image = screen.getByRole('img', { name: 'Truck Pit Stop logo' })
    expect(image.getAttribute('src')).toBe('https://cdn.example.com/tenant-logo.png')
  })

  it('falls back to the platform logo when the tenant image fails to load', () => {
    render(
      <TenantBrandLogo
        tenantLogoUrl="https://cdn.example.com/broken-logo.png"
        tenantName="Truck Pit Stop"
        alt="Truck Pit Stop"
      />
    )

    fireEvent.error(screen.getByRole('img', { name: 'Truck Pit Stop' }))

    const fallbackImage = screen.getByRole('img', { name: 'Truck Pit Stop' })
    expect(fallbackImage.getAttribute('src')).toContain('/DB_bridge_logo_favi_figma_admin.png')
  })
})
