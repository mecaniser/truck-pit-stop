import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Vehicle } from '@/types'
import PortalVehicleScope from '../PortalVehicleScope'
const vehicle = { id: 'one', unit_number: '1047', year: 2022, make: 'Volvo', license_plate: 'ABC123' } as Vehicle
afterEach(cleanup)
describe('vehicle scope for a single authorized choice', () => {
  it.each([null, 'one'])('shows identity without redundant selection for requested %s', requested => {
    render(<PortalVehicleScope vehicles={[vehicle]} requested={requested} onChange={vi.fn()} />)
    expect(screen.getByText('Unit #1047 · 2022 Volvo · ABC123')).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'All vehicles' })).not.toBeInTheDocument()
  })
  it('retains a recovery selector when the requested vehicle is unavailable', () => {
    render(<PortalVehicleScope vehicles={[vehicle]} requested="foreign" onChange={vi.fn()} />)
    expect(screen.getByRole('combobox', { name: 'Vehicle scope' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'All vehicles' })).toBeInTheDocument()
  })
})
