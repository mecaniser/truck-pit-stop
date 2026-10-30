import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ShopSMSRegistration from './ShopSMSRegistration'
vi.mock('../../communications/SMSSetup', () => ({ default: ({tenantId, onDirtyChange}: {tenantId: string; onDirtyChange: (dirty: boolean) => void}) => <input aria-label={`Draft for ${tenantId}`} onChange={() => onDirtyChange(true)} /> }))
describe('Platform registration dialog', () => {
  it('names the selected shop and requires explicit discard of unsaved changes', () => {
    const onClose = vi.fn()
    render(<ShopSMSRegistration tenantId="a" shopName="Shop A" onClose={onClose} />)
    fireEvent.change(screen.getByLabelText('Draft for a'), {target:{value:'Unsaved'}})
    fireEvent.click(screen.getByRole('button',{name:'Close registration'}))
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button',{name:'Keep editing'}))
    expect(screen.getByLabelText('Draft for a')).toHaveValue('Unsaved')
    fireEvent.keyDown(screen.getByRole('dialog'),{key:'Escape'})
    fireEvent.click(screen.getByRole('button',{name:'Discard changes'}))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
