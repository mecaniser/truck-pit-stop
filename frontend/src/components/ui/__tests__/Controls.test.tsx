import { createRef } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ControlButton, ControlInput } from '../Controls'

describe('shared control native contracts', () => {
  it('preserves implicit submit, explicit non-submit, form data and forwarded refs', async () => {
    const user = userEvent.setup()
    const submit = vi.fn((event: React.FormEvent) => event.preventDefault())
    const button = createRef<HTMLButtonElement>()
    const input = createRef<HTMLInputElement>()
    render(<form aria-label="Editor" onSubmit={submit}>
      <ControlInput ref={input} aria-label="Name" name="name" defaultValue="Truck" required />
      <ControlButton ref={button} type="button">Refresh</ControlButton>
      <ControlButton>Save</ControlButton>
    </form>)
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    expect(submit).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(submit).toHaveBeenCalledTimes(1)
    expect(new FormData(screen.getByRole('form') as HTMLFormElement).get('name')).toBe('Truck')
    expect(button.current).toBe(screen.getByRole('button', { name: 'Refresh' }))
    input.current?.focus()
    expect(input.current).toHaveFocus()
  })

  it('preserves disabled fieldset, named icon, focus and keyboard activation', async () => {
    const user = userEvent.setup()
    const click = vi.fn()
    const { rerender } = render(<fieldset disabled><ControlButton controlKind="icon" aria-label="Refresh" onClick={click}>↻</ControlButton></fieldset>)
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    expect(click).not.toHaveBeenCalled()
    rerender(<fieldset><ControlButton controlKind="icon" aria-label="Refresh" onClick={click}>↻</ControlButton></fieldset>)
    screen.getByRole('button').focus()
    await user.keyboard('{Enter}')
    expect(click).toHaveBeenCalledTimes(1)
  })

  it('preserves controlled input events and semantic content buttons', () => {
    const change = vi.fn()
    render(<><ControlInput aria-label="Search" value="" onChange={change} /><ControlButton controlKind="content" aria-expanded={false}>Record details</ControlButton></>)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'truck' } })
    expect(change).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('button')).toHaveAttribute('data-db-control', 'content')
  })
})
