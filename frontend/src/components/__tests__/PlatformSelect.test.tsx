import { createRef, useState } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Controller, useForm } from 'react-hook-form'
import PlatformSelect from '../PlatformSelect'

describe('platform dropdown form compatibility', () => {
  it('preserves real native change events, names and form serialization', async () => {
    const change = vi.fn()
    function Form() {
      const [value, setValue] = useState('tractor')
      return <form data-testid="form"><label>Equipment<PlatformSelect name="equipment" value={value} onChange={event => { change(event.target instanceof HTMLSelectElement, event.target.name, event.target.value); setValue(event.target.value) }}>
        <option value="tractor">Tractor</option><><option value="trailer">Trailer</option><option value="old" disabled>Previous asset</option></>
      </PlatformSelect></label></form>
    }
    render(<Form />)
    const control = screen.getByRole('combobox', { name: 'Equipment' })
    await userEvent.click(control)
    expect(screen.getByRole('option', { name: 'Previous asset' })).toBeDisabled()
    await userEvent.click(screen.getByRole('option', { name: 'Trailer', exact: true }))
    expect(change).toHaveBeenCalledExactlyOnceWith(true, 'equipment', 'trailer')
    expect(new FormData(screen.getByTestId('form') as HTMLFormElement).get('equipment')).toBe('trailer')
    expect(screen.getByRole('combobox', { name: 'Equipment' })).toHaveTextContent('Trailer')
  })
  it('retains required validation and focuses the visible control', async () => {
    const submit = vi.fn(event => event.preventDefault())
    function Form() { const [value, setValue] = useState(''); return <form onSubmit={submit}><label>Occurrence<PlatformSelect name="fold" required value={value} onChange={event => setValue(event.target.value)}><option value="">Choose occurrence</option><option value="0">First occurrence</option></PlatformSelect></label><button>Save</button></form> }
    render(<Form />)
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(submit).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toBeVisible()
    expect(screen.getByRole('combobox', { name: 'Occurrence' })).toHaveFocus()
    await userEvent.keyboard('{ArrowDown}{End}{Enter}')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(submit).toHaveBeenCalledOnce()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
  it('skips disabled options and Escape dismisses only the dropdown', async () => {
    const escape = vi.fn()
    function Form() { const [value, setValue] = useState(''); return <div onKeyDown={event => { if (event.key === 'Escape') escape() }}><PlatformSelect aria-label="Truck" value={value} onChange={event => setValue(event.target.value)}><option value="" disabled>Select truck</option><option value="a" disabled>Previous truck</option><option value="b">Available truck</option></PlatformSelect></div> }
    render(<Form />)
    screen.getByRole('combobox', { name: 'Truck' }).focus()
    await userEvent.keyboard('{ArrowDown}{Enter}')
    expect(screen.getByRole('combobox', { name: 'Truck' })).toHaveTextContent('Available truck')
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Truck' })).toHaveFocus())
    await userEvent.keyboard('{ArrowDown}{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(escape).not.toHaveBeenCalled()
  })
  it('keeps forwarded focus refs and controlled form resets working', async () => {
    const ref = createRef<HTMLSelectElement>()
    function Form() { const [value, setValue] = useState('real'); return <form onReset={() => setValue('real')}><PlatformSelect aria-label="Scope" ref={ref} name="scope" value={value} onChange={event => setValue(event.target.value)}><option>all</option><option>real</option></PlatformSelect><button type="reset">Reset</button></form> }
    render(<Form />)
    expect(ref.current).toBeInstanceOf(HTMLSelectElement)
    expect(screen.getByRole('combobox', { name: 'Scope' })).toHaveTextContent('real')
    await userEvent.click(screen.getByRole('combobox', { name: 'Scope' }))
    await userEvent.click(screen.getByRole('option', { name: 'all', exact: true }))
    await userEvent.click(screen.getByRole('button', { name: 'Reset' }))
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Scope' })).toHaveTextContent('real'))
    ref.current?.focus()
    expect(screen.getByRole('combobox', { name: 'Scope' })).toHaveFocus()
  })
  it('supports react-hook-form defaults, reset, and submission through Controller', async () => {
    const save = vi.fn()
    function RegisteredForm() {
      const { control, handleSubmit, reset } = useForm({ defaultValues: { role: 'admin' } })
      return <form onSubmit={handleSubmit(save)}><label>Role<Controller control={control} name="role" render={({ field }) => <PlatformSelect {...field}><option value="mechanic">Technician</option><option value="admin">Admin</option></PlatformSelect>} /></label><button type="button" onClick={() => reset({ role: 'mechanic' })}>Reset role</button><button>Save role</button></form>
    }
    render(<RegisteredForm />)
    expect(screen.getByRole('combobox', { name: 'Role' })).toHaveTextContent('Admin')
    await userEvent.click(screen.getByRole('button', { name: 'Reset role' }))
    expect(screen.getByRole('combobox', { name: 'Role' })).toHaveTextContent('Technician')
    await userEvent.click(screen.getByRole('button', { name: 'Save role' }))
    await waitFor(() => expect(save).toHaveBeenCalledWith({ role: 'mechanic' }, expect.anything()))
  })
  it('honors disabled state and labels associated by id', () => {
    render(<><label htmlFor="select-test">Recipient</label><PlatformSelect id="select-test" name="payer" value="1" disabled onChange={vi.fn()}><option value="1">Company</option></PlatformSelect></>)
    expect(screen.getByLabelText('Recipient')).toBeDisabled()
    fireEvent.click(screen.getByLabelText('Recipient'))
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
  it('cannot change after being disabled while open', async () => {
    const change = vi.fn()
    const field = (disabled = false) => <PlatformSelect aria-label="Status" value="open" disabled={disabled} onChange={change}><option value="open">Open</option><option value="closed">Closed</option></PlatformSelect>
    const view = render(field())
    await userEvent.click(screen.getByRole('combobox'))
    view.rerender(field(true))
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(screen.getByRole('combobox')).toBeDisabled()
    expect(change).not.toHaveBeenCalled()
  })
  it('lets closed Escape reach its containing dialog', async () => {
    const escape = vi.fn()
    render(<div onKeyDown={event => { if (event.key === 'Escape') escape() }}><PlatformSelect aria-label="Status" value="open"><option value="open">Open</option></PlatformSelect></div>)
    screen.getByRole('combobox').focus()
    await userEvent.keyboard('{Escape}')
    expect(escape).toHaveBeenCalledOnce()
  })
  it('retains disabled option-group constraints', async () => {
    render(<PlatformSelect aria-label="Asset" value="current"><optgroup disabled label="Archived"><option value="old">Old asset</option></optgroup><option value="current">Current asset</option></PlatformSelect>)
    await userEvent.click(screen.getByRole('combobox'))
    expect(screen.getByRole('option', { name: 'Old asset' })).toBeDisabled()
  })

  it('honors disabled fieldsets even while its menu is portaled outside them', async () => {
    const change = vi.fn()
    const field = (disabled = false) => <fieldset disabled={disabled}><PlatformSelect aria-label="Consent" value="phone" onChange={change}><option value="phone">Phone</option><option value="in_person">In person</option></PlatformSelect></fieldset>
    const view = render(field())
    await userEvent.click(screen.getByRole('combobox'))
    const option = screen.getByRole('option', { name: 'In person' })
    view.rerender(field(true))
    fireEvent.mouseDown(option)
    expect(change).not.toHaveBeenCalled()
    await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument())
    expect(screen.getByRole('combobox')).toBeDisabled()
  })

  it('does not steal focus from the next field after choosing an option', async () => {
    function Form() { const [value, setValue] = useState('cash'); return <><PlatformSelect aria-label="Tender" value={value} onChange={event => setValue(event.target.value)}><option value="cash">Cash</option><option value="terminal">Terminal</option></PlatformSelect><label>Reference<input /></label></> }
    render(<Form />)
    await userEvent.click(screen.getByRole('combobox'))
    await userEvent.click(screen.getByRole('option', { name: 'Terminal' }))
    await userEvent.type(screen.getByLabelText('Reference'), 'TERM-44')
    expect(screen.getByLabelText('Reference')).toHaveValue('TERM-44')
    expect(screen.getByLabelText('Reference')).toHaveFocus()
  })

  it('clamps its portal to compact viewports above a high-layer modal', async () => {
    const width = Object.getOwnPropertyDescriptor(window, 'innerWidth')!
    const height = Object.getOwnPropertyDescriptor(window, 'innerHeight')!
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 220 })
    try {
      render(<div style={{ position: 'relative', zIndex: 1200 }}><PlatformSelect aria-label="Compact" value="a"><option value="a">A</option></PlatformSelect></div>)
      const field = screen.getByRole('combobox')
      vi.spyOn(field.parentElement!, 'getBoundingClientRect').mockReturnValue({ left: -10, top: 120, bottom: 164, right: 450, width: 460, height: 44, x: -10, y: 120, toJSON: () => ({}) })
      await userEvent.click(field)
      expect(screen.getByRole('listbox')).toHaveStyle({ left: '8px', width: '374px', maxHeight: '112px', zIndex: '1201' })
    } finally {
      Object.defineProperty(window, 'innerWidth', width)
      Object.defineProperty(window, 'innerHeight', height)
    }
  })

})
