import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import WorkspaceActionOverflow from '../WorkspaceActionOverflow'
import StartWorkAction from '@/features/repair-orders/StartWorkAction'
import CustomerDetailFooter from '@/features/customers/CustomerDetailFooter'
import CustomerVehicleFooter from '@/features/customers/CustomerVehicleFooter'
import type { Customer, Vehicle } from '@/types'

function phone() {
  vi.spyOn(window, 'matchMedia').mockImplementation(query => ({
    matches: query.includes('max-width: 639px'), media: query, onchange: null,
    addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
  }))
}
afterEach(() => vi.restoreAllMocks())

describe('compact workspace actions', () => {
  it('keeps Edit directly accessible and restores focus after Escape without acting', async () => {
    phone()
    const user = userEvent.setup()
    const customer = { id: 'customer-a' } as Customer
    const edit = vi.fn(), merge = vi.fn(), remove = vi.fn()
    render(<CustomerDetailFooter selectedCustomer={customer} handleEditFromDetail={edit} onMerge={merge} handleDeleteClick={remove} />)
    await user.click(screen.getByRole('button', { name: 'Edit Customer' }))
    expect(edit).toHaveBeenCalledOnce()
    expect(screen.queryByRole('button', { name: 'Delete', exact: true })).not.toBeInTheDocument()
    const more = screen.getByRole('button', { name: 'Customer actions', exact: true })
    more.focus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('button', { name: 'Merge', exact: true })).toBeVisible()
    await user.keyboard('{Escape}')
    expect(more).toHaveFocus()
    expect(merge).not.toHaveBeenCalled()
    await user.click(more)
    await user.click(screen.getByRole('button', { name: 'Merge', exact: true }))
    expect(merge).toHaveBeenCalledOnce()
    expect(more).toHaveAttribute('aria-expanded', 'false')
    await user.click(more)
    await user.click(screen.getByRole('button', { name: 'Delete', exact: true }))
    expect(remove).toHaveBeenCalledWith(customer)
  })

  it('keeps a nested technician picker open when focus moves to its portal', async () => {
    phone()
    const user = userEvent.setup(), assign = vi.fn()
    render(<WorkspaceActionOverflow label="Repair order actions"><StartWorkAction mode="reassign" technicians={[{ mechanic_id: 'tech-a', mechanic_name: 'Alex', load: 0 }]} onAssign={assign} assignmentPending={false} startPending={false} /></WorkspaceActionOverflow>)
    await user.click(screen.getByRole('button', { name: 'Repair order actions', exact: true }))
    await user.click(screen.getByRole('button', { name: 'Change technician…' }))
    expect(screen.getByRole('button', { name: 'Close change technician options' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Alex 0% load' }))
    expect(assign).toHaveBeenCalledWith('tech-a')
    expect(screen.queryByRole('button', { name: 'Alex 0% load' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change technician…' })).toHaveFocus()
  })

  it('preserves vehicle identity and disabled merge guards in More', async () => {
    phone()
    const vehicle = { id: 'truck-a', vin: 'short' } as Vehicle
    const onManage = vi.fn()
    const user = userEvent.setup()
    render(<CustomerVehicleFooter vehicle={vehicle} canMerge onManage={onManage} onEdit={vi.fn()} onDelete={vi.fn()} onMerge={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Edit vehicle' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Vehicle actions', exact: true }))
    expect(screen.getByRole('button', { name: 'Merge duplicate' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Manage connections' }))
    expect(onManage).toHaveBeenCalledWith(vehicle)
    expect(screen.queryByRole('button', { name: 'Merge duplicate' })).not.toBeInTheDocument()
  })
})
