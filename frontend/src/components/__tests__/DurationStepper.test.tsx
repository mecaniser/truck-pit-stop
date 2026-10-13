import { useState } from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DurationStepper from '../DurationStepper'

function setup(props: Partial<React.ComponentProps<typeof DurationStepper>> = {}) {
  const change = vi.fn()
  function Harness() {
    const [hours, setHours] = useState(1)
    return <DurationStepper hours={hours} ariaLabel="Labor duration" onChange={h => { change(h); setHours(h) }} {...props} />
  }
  const view = render(<Harness />)
  return { change, ...view }
}

const field = () => screen.getByRole('textbox', { name: 'Labor duration' })
async function typeDuration(value: string) {
  const user = userEvent.setup()
  await user.click(field())
  await user.clear(field())
  await user.type(field(), value)
  return user
}

afterEach(() => vi.useRealTimers())

describe('DurationStepper manual entry', () => {
  it.each([['1:20', 1.33], ['1.5', 1.5], ['1.01', 1.01], ['1.99', 1.99], ['90m', 1.5], ['1h 20m', 1.33]])('saves %s on Enter without rounding to a quarter hour', async (text, hours) => {
    const { change } = setup()
    const user = await typeDuration(text)
    expect(change).not.toHaveBeenCalled()
    await user.keyboard('{Enter}')
    expect(change).toHaveBeenCalledExactlyOnceWith(hours)
  })
  it('selects the displayed duration so typing replaces it immediately', async () => {
    const { change } = setup()
    const user = userEvent.setup()
    await user.click(field())
    await user.keyboard('1:20{Enter}')
    expect(change).toHaveBeenCalledExactlyOnceWith(1.33)
  })
  it('saves when leaving the field', async () => {
    const { change } = setup()
    const user = await typeDuration('2.25')
    await user.tab()
    expect(change).toHaveBeenCalledExactlyOnceWith(2.25)
    expect(field()).toHaveValue('2h 15m')
  })
  it('cancels with Escape without propagating to the containing dialog', async () => {
    const escape = vi.fn()
    render(<div onKeyDown={escape}><DurationStepper hours={1} ariaLabel="Labor duration" onChange={vi.fn()} /></div>)
    const user = await typeDuration('2.5')
    escape.mockClear()
    await user.keyboard('{Escape}')
    expect(escape).not.toHaveBeenCalled()
    expect(field()).toHaveValue('1h')
  })
  it.each(['-1', '1:75', 'abc', '0.1', 'Infinity', ''])('keeps invalid input %j visible without saving', async (value) => {
    const { change } = setup()
    const user = userEvent.setup()
    await user.click(field())
    await user.clear(field())
    if (value) await user.type(field(), value)
    await user.tab()
    expect(change).not.toHaveBeenCalled()
    expect(field()).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toBeVisible()
  })
  it('permits zero when the caller allows it', async () => {
    const { change } = setup({ minMinutes: 0 })
    const user = await typeDuration('0')
    await user.keyboard('{Enter}')
    expect(change).toHaveBeenCalledExactlyOnceWith(0)
    expect(screen.getByRole('button', { name: 'Decrease duration' })).toBeDisabled()
  })
  it('steps from the typed duration, preserving non-quarter minutes', async () => {
    const { change } = setup()
    const user = await typeDuration('1:20')
    await user.click(screen.getByRole('button', { name: 'Increase duration' }))
    expect(change).toHaveBeenLastCalledWith(1.58)
    expect(field()).toHaveValue('1h 35m')
  })
  it('does not write when merely focusing and leaving the field', async () => {
    const { change } = setup({ hours: 1.33 })
    const user = userEvent.setup()
    await user.click(field())
    await user.tab()
    expect(change).not.toHaveBeenCalled()
  })
  it('disables typing and both buttons when locked', () => {
    setup({ disabled: true })
    expect(field()).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Increase duration' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Decrease duration' })).toBeDisabled()
  })
  it('persists when the parent reflects optimistic hours immediately', () => {
    vi.useFakeTimers()
    const saved = vi.fn()
    function OptimisticParent() {
      const [hours, setHours] = useState(1)
      return <DurationStepper hours={hours} onChange={saved} onLocalChange={setHours} commitDebounceMs={500} ariaLabel="Labor duration" />
    }
    render(<OptimisticParent />)
    fireEvent.focus(field())
    fireEvent.change(field(), { target: { value: '1:20' } })
    fireEvent.blur(field())
    act(() => { vi.advanceTimersByTime(500) })
    expect(saved).toHaveBeenCalledExactlyOnceWith(1.33)
  })
  it('debounces typed entries and subsequent steps into one persisted value', () => {
    vi.useFakeTimers()
    const localChange = vi.fn()
    const { change } = setup({ commitDebounceMs: 400, onLocalChange: localChange })
    fireEvent.focus(field())
    fireEvent.change(field(), { target: { value: '1:20' } })
    fireEvent.blur(field())
    fireEvent.click(screen.getByRole('button', { name: 'Increase duration' }))
    expect(change).not.toHaveBeenCalled()
    expect(localChange).toHaveBeenLastCalledWith(1.58)
    act(() => { vi.advanceTimersByTime(400) })
    expect(change).toHaveBeenCalledExactlyOnceWith(1.58)
  })
})
