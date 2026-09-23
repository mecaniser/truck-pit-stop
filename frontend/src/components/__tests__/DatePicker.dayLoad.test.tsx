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

describe('DatePicker day load popover', () => {
  const busy = [
    { day: '2026-11-04', count: 3, units: ['603', '412', '118'] },
    { day: '2026-11-06', count: 0, units: [], booked_count: 2, booked_units: ['77', '88'] },
  ]

  it('shows the app popover on hover, not the browser tooltip', async () => {
    const user = open({ dayLoad: busy })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const day = within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ })
    // The native tooltip cannot be styled, delayed or keyboard-triggered, so the
    // day must not fall back to it.
    expect(day).not.toHaveAttribute('title')
    await user.hover(day)
    expect(await screen.findByRole('tooltip')).toBeInTheDocument()
  })

  it('lists each truck due that day', async () => {
    const user = open({ dayLoad: busy })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    await user.hover(within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ }))
    const tip = within(await screen.findByRole('tooltip'))
    expect(tip.getByText('603')).toBeInTheDocument()
    expect(tip.getByText('412')).toBeInTheDocument()
    expect(tip.getByText('118')).toBeInTheDocument()
  })

  it('names the day so the popover stands on its own', async () => {
    const user = open({ dayLoad: busy })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    await user.hover(within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ }))
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Nov 4, 2026')
  })

  it('separates booked repair work from PMs', async () => {
    const user = open({ dayLoad: busy })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    await user.hover(within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 6, 2026/ }))
    const tip = within(await screen.findByRole('tooltip'))
    expect(tip.getByText(/repair/i)).toBeInTheDocument()
    expect(tip.getByText('77')).toBeInTheDocument()
  })

  it('opens on keyboard focus so it is not mouse-only', async () => {
    const user = open({ dayLoad: busy })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const day = within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ })
    day.focus()
    expect(await screen.findByRole('tooltip')).toBeInTheDocument()
  })

  it('closes when the pointer leaves', async () => {
    const user = open({ dayLoad: busy })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const dialog = within(screen.getByRole('dialog'))
    const day = dialog.getByRole('button', { name: /Nov 4, 2026/ })
    await user.hover(day)
    expect(await screen.findByRole('tooltip')).toBeInTheDocument()
    await user.unhover(day)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('shows no popover on a free day', async () => {
    const user = open({ dayLoad: busy })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    await user.hover(within(screen.getByRole('dialog')).getByRole('button', { name: /^Nov 5, 2026$/ }))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('keeps the full description on the day for screen readers', async () => {
    const user = open({ dayLoad: busy })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const day = within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ })
    expect(day).toHaveAccessibleName(expect.stringContaining('3 PMs'))
  })
})

describe('DatePicker popover does not move the grid', () => {
  it('overlays rather than displacing the days under the cursor', async () => {
    const user = open({ dayLoad: [{ day: '2026-11-04', count: 2, units: ['603', '412'] }] })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    await user.hover(within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ }))
    const tip = await screen.findByRole('tooltip')
    // In flow, the popover would push the grid down and the day would slide out
    // from under the pointer, closing the popover and flickering.
    expect(getComputedStyle(tip).position).toBe('absolute')
  })
})

describe('DatePicker popover stability', () => {
  it('does not intercept the pointer and close itself', async () => {
    const user = open({ dayLoad: [{ day: '2026-11-04', count: 2, units: ['603', '412'] }] })
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    await user.hover(within(screen.getByRole('dialog')).getByRole('button', { name: /Nov 4, 2026/ }))
    const tip = await screen.findByRole('tooltip')
    // The popover overlays the grid. If it accepted pointer events, moving onto
    // a day beneath it would fire mouseleave on that day, closing the popover,
    // which re-exposes the day and reopens it: a flicker loop.
    expect(getComputedStyle(tip).pointerEvents).toBe('none')
  })
})
