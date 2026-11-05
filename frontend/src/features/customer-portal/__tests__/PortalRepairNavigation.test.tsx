import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import PortalRepairNavigation from '../PortalRepairNavigation'

describe('repair section navigation', () => {
  it.each([
    ['/portal/repairs?vehicle_id=truck&view=active', 'Current repairs'],
    ['/portal/repairs?view=active&vehicle_id=truck', 'Current repairs'],
    ['/portal/repairs?vehicle_id=truck', 'Repair history'],
    ['/portal/appointments?appointment_id=visit&vehicle_id=truck', 'Appointments'],
    ['/portal/appointments?request_id=request&vehicle_id=truck', 'Appointments'],
  ])('marks the destination independently of query ordering: %s', (path, label) => {
    render(<MemoryRouter initialEntries={[path]}><PortalRepairNavigation vehicleId="truck"/></MemoryRouter>)
    expect(screen.getByRole('link', { name: label })).toHaveAttribute('aria-current', 'page')
    expect(screen.getAllByRole('link').filter(link => link.getAttribute('aria-current') === 'page')).toHaveLength(1)
    expect(screen.getByRole('link', { name: 'Current repairs' })).toHaveAttribute('href', '/portal/repairs?view=active&vehicle_id=truck')
    expect(screen.getByRole('link', { name: 'Appointments' })).toHaveAttribute('href', '/portal/appointments?vehicle_id=truck')
  })
})
