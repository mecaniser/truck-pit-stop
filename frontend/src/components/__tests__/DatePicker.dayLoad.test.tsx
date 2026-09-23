import { render, screen, waitFor, within } from '@testing-library/react'
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

describe('DatePicker total shop load', () => {
  const mixed = [
    { day: '2026-11-04', count: 2, units: ['603', '412'], booked_count: 1, booked_units: ['118'] },
    { day: '2026-11-06', count: 0, units: [], booked_count: 3, booked_units: ['77', '88', '99'] },
  ]

  it('adds booked repair work into the day total', async () => {
    const user = open({ dayLoad: mixed })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const day = within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ })
    expect(day).toHaveTextContent('3')
  })

  it('separates PM load from repair load so the reason is visible', async () => {
    const user = open({ dayLoad: mixed })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const day = within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ })
    expect(day).toHaveAccessibleName(expect.stringContaining('2 PMs'))
    expect(day).toHaveAccessibleName(expect.stringContaining('1 repair'))
  })

  it('marks a day that carries only repair work', async () => {
    const user = open({ dayLoad: mixed })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const day = within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 6, 2026/ })
    expect(day).toHaveClass('has-load')
    expect(day).toHaveTextContent('3')
    expect(day).toHaveAccessibleName(expect.stringContaining('3 repair'))
  })

  it('does not mention repair work on a PM-only day', async () => {
    const user = open({ dayLoad: [{ day: '2026-11-04', count: 1, units: ['603'] }] })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const day = within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ })
    expect(day).toHaveAccessibleName(expect.not.stringContaining('repair'))
  })
})

describe('DatePicker day detail footer', () => {
  const busy = [
    { day: '2026-11-04', count: 3, units: ['603', '412', '118'] },
    { day: '2026-11-06', count: 0, units: [], booked_count: 2, booked_units: ['77', '88'] },
  ]

  it('shows the detail below the grid, not over it', async () => {
    const user = open({ dayLoad: busy })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const dialog = screen.getByRole('dialog')
    await user.hover(within(dialog).getByRole('button', { name: /Nov 4, 2026/ }))
    const detail = await screen.findByTestId('day-detail')
    const grid = dialog.querySelector('.db-datepicker__days')!
    // The detail must follow the grid in document order, so it cannot cover the
    // weeks a manager is comparing against.
    expect(grid.compareDocumentPosition(detail) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('reserves its space so the grid never shifts', async () => {
    const user = open({ dayLoad: busy })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    // Present and occupying layout even with nothing selected, so appearing
    // later cannot move the days under the pointer.
    expect(screen.getByTestId('day-detail')).toBeInTheDocument()
  })

  it('opens on tap, for touch screens with no hover', async () => {
    const user = open({ dayLoad: busy })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const day = within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ })
    // A tap selects the date and must also reveal what is already on that day.
    await user.click(day)
    expect(screen.getByTestId('day-detail')).toHaveTextContent('603')
  })

  it('prompts when nothing is highlighted', async () => {
    const user = open({ dayLoad: busy })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    expect(screen.getByTestId('day-detail')).toHaveTextContent(/select a day|no pm/i)
  })

  it('names the trucks and the day', async () => {
    const user = open({ dayLoad: busy })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    await user.hover(within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ }))
    const detail = await screen.findByTestId('day-detail')
    expect(detail).toHaveTextContent('Nov 4, 2026')
    expect(detail).toHaveTextContent('603')
    expect(detail).toHaveTextContent('412')
  })

  it('separates repair work from PMs', async () => {
    const user = open({ dayLoad: busy })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    await user.hover(within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 6, 2026/ }))
    const detail = await screen.findByTestId('day-detail')
    expect(detail).toHaveTextContent(/repair/i)
    expect(detail).toHaveTextContent('77')
  })

  it('says a highlighted free day is free', async () => {
    const user = open({ dayLoad: busy })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    await user.hover(within(screen.getByRole('dialog')).getByRole('button', { name: /^Nov 5, 2026$/ }))
    expect(screen.getByTestId('day-detail')).toHaveTextContent(/nothing scheduled|free/i)
  })
})

describe('DatePicker day detail replaces the native tooltip', () => {
  it('does not fall back to the browser tooltip', async () => {
    const user = open({ dayLoad: [{ day: '2026-11-04', count: 2, units: ['603', '412'] }] })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const day = within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ })
    // title cannot be styled, is ~1s delayed, never fires on touch and is
    // invisible to keyboard users.
    expect(day).not.toHaveAttribute('title')
  })

  it('reports the day on keyboard focus, so it is not pointer-only', async () => {
    // The calendar opens with the selected day focused; arrow keys move between
    // days, which is how a keyboard user reaches one.
    const user = open({ value: '2026-11-05', dayLoad: [{ day: '2026-11-04', count: 2, units: ['603', '412'] }] })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const day = within(screen.getByRole('dialog')).getByRole('button', { name: /^Nov 5, 2026$/ })
    day.focus()
    await user.keyboard('{ArrowLeft}')
    // focusDay moves focus inside requestAnimationFrame, so wait for it.
    await waitFor(() => expect(screen.getByTestId('day-detail')).toHaveTextContent('603'))
  })

  it('keeps the full description on the day for screen readers', async () => {
    const user = open({ dayLoad: [{ day: '2026-11-04', count: 3, units: ['603', '412', '118'] }] })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const day = within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ })
    expect(day).toHaveAccessibleName(expect.stringContaining('3 PMs'))
  })
})
