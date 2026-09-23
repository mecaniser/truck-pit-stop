import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import DatePicker from '../DatePicker'

/* Day load: the calendar shows how many trucks are already scheduled for PM on
   each day, so a manager can spread the work instead of stacking five trucks
   onto one date. */

const load = [
  { day: '2026-11-04', count: 2, units: ['412', '603'] },
  { day: '2026-11-12', count: 1, units: ['118'] },
]

function open(props: Partial<React.ComponentProps<typeof DatePicker>> = {}) {
  const user = userEvent.setup()
  render(<DatePicker label="Next PM due date" value="2026-11-04" onChange={vi.fn()} {...props} />)
  return user
}

describe('DatePicker day load', () => {
  it('marks how many trucks are already scheduled on a day', async () => {
    const user = open({ dayLoad: load })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const day = within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ })
    expect(day).toHaveTextContent('2')
  })

  it('names the trucks so the manager knows what is already booked', async () => {
    const user = open({ dayLoad: load })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const day = within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ })
    expect(day).toHaveAccessibleName(expect.stringContaining('412'))
    expect(day).toHaveAccessibleName(expect.stringContaining('603'))
  })

  it('leaves a free day unmarked', async () => {
    const user = open({ dayLoad: load })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const free = within(screen.getByRole('dialog')).getByRole('button', { name: /^Nov 5, 2026$/ })
    expect(free).not.toHaveClass('has-load')
  })

  it('still renders a plain calendar when no load is supplied', async () => {
    const user = open()
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: 'Nov 4, 2026' }))
      .toBeInTheDocument()
  })

  it('asks for the load of the month being viewed, so navigation refetches', async () => {
    const onMonthChange = vi.fn()
    const user = open({ dayLoad: load, onMonthChange })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    onMonthChange.mockClear()
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: /next month/i }))
    expect(onMonthChange).toHaveBeenCalledWith('2026-12')
  })
})
