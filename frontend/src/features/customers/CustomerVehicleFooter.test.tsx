import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import CustomerVehicleFooter from './CustomerVehicleFooter'
import type { Vehicle } from '@/types'

const vehicle = { id: 'truck-a', vin: '1FUJGLDR9CLBP0001' } as Vehicle

describe('customer truck actions', () => {
  it('keeps every action attached to the displayed truck', async () => {
    const actions = { onDelete: vi.fn(), onMerge: vi.fn(), onManage: vi.fn(), onEdit: vi.fn() }
    render(<CustomerVehicleFooter vehicle={vehicle} canMerge {...actions} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Delete vehicle' }))
    await user.click(screen.getByRole('button', { name: 'Manage connections' }))
    await user.click(screen.getByRole('button', { name: 'Edit vehicle' }))
    await user.click(screen.getByRole('button', { name: 'Merge duplicate' }))
    expect(actions.onDelete).toHaveBeenCalledWith(vehicle)
    expect(actions.onManage).toHaveBeenCalledWith(vehicle)
    expect(actions.onEdit).toHaveBeenCalledWith(vehicle)
    expect(actions.onMerge).toHaveBeenCalledOnce()
  })

  it('preserves the complete VIN and role restrictions on merging', () => {
    const actions = { onDelete: vi.fn(), onMerge: vi.fn(), onManage: vi.fn(), onEdit: vi.fn() }
    const { rerender } = render(<CustomerVehicleFooter vehicle={{ ...vehicle, vin: 'short' }} canMerge {...actions} />)
    expect(screen.getByRole('button', { name: 'Merge duplicate' })).toBeDisabled()
    rerender(<CustomerVehicleFooter vehicle={vehicle} canMerge={false} {...actions} />)
    expect(screen.queryByRole('button', { name: 'Merge duplicate' })).not.toBeInTheDocument()
  })
})
