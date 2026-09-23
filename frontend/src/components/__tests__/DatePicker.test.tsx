import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import DatePicker from '../DatePicker'

/* The shared single-date control. The app previously used bare
   <input type="date"> everywhere, which hands the calendar to the browser: on
   the dark staff shell Chrome paints its own dark-on-dark popup that the user
   cannot read, and no app CSS can reach inside it. This component owns the
   calendar so the theme tokens apply. */

function Harness({ value = '', ...rest }: { value?: string } & Partial<React.ComponentProps<typeof DatePicker>>) {
  const [date, setDate] = useState(value)
  return <DatePicker label="Next PM due date" value={date} onChange={setDate} {...rest} />
}

async function open(props: Partial<React.ComponentProps<typeof DatePicker>> & { value?: string } = {}) {
  const user = userEvent.setup()
  render(<Harness {...props} />)
  await user.click(screen.getByRole('button', { name: /choose date/i }))
  return { user, calendar: within(screen.getByRole('dialog', { name: /next pm due date/i })) }
}

describe('DatePicker', () => {
  it('shows the selected date in the trigger rather than an empty control', () => {
    render(<Harness value="2026-11-04" />)
    expect(screen.getByRole('button', { name: /Nov 4, 2026/ })).toBeInTheDocument()
  })

  it('opens a calendar owned by the app, not the browser', async () => {
    const { calendar } = await open({ value: '2026-11-04' })
    expect(calendar.getByRole('button', { name: 'Nov 4, 2026' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('reports the day the user picks', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<DatePicker label="Next PM due date" value="2026-11-04" onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Nov 20, 2026' }))
    expect(onChange).toHaveBeenCalledWith('2026-11-20')
  })

  it('moves between months without changing the selection', async () => {
    const { user, calendar } = await open({ value: '2026-11-04' })
    await user.click(calendar.getByRole('button', { name: /previous month/i }))
    expect(calendar.getByRole('heading', { name: /October 2026/ })).toBeInTheDocument()
    expect(calendar.queryByRole('button', { name: 'Nov 4, 2026' })).not.toBeInTheDocument()
  })

  it('keeps a typed date authoritative over the calendar', async () => {
    const user = userEvent.setup()
    render(<Harness value="2026-11-04" />)
    const field = screen.getByLabelText(/next pm due date/i)
    await user.clear(field)
    await user.type(field, '2026-12-25')
    expect(field).toHaveValue('2026-12-25')
    // The calendar must follow what was typed, not the value it opened with.
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: 'Dec 25, 2026' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('refuses days after a max boundary so a PM cannot be recorded in the future', async () => {
    const { calendar } = await open({ value: '2026-11-04', max: '2026-11-10' })
    expect(calendar.getByRole('button', { name: 'Nov 20, 2026' })).toBeDisabled()
    expect(calendar.getByRole('button', { name: 'Nov 9, 2026' })).toBeEnabled()
  })

  it('refuses days before a min boundary', async () => {
    const { calendar } = await open({ value: '2026-11-04', min: '2026-11-03' })
    expect(calendar.getByRole('button', { name: 'Nov 1, 2026' })).toBeDisabled()
    expect(calendar.getByRole('button', { name: 'Nov 4, 2026' })).toBeEnabled()
  })

  it('closes on Escape and returns focus to the trigger', async () => {
    const { user } = await open({ value: '2026-11-04' })
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /choose date/i })).toHaveFocus()
  })

  it('does not shift a date-only value across a timezone boundary', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<DatePicker label="Next PM due date" value="2026-03-01" onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Mar 1, 2026' }))
    expect(onChange).toHaveBeenCalledWith('2026-03-01')
  })
})

describe('DatePicker in a compact filter row', () => {
  it('keeps an accessible name when the visible label is suppressed', () => {
    render(<DatePicker label="From date" value="" onChange={vi.fn()} compact />)
    expect(screen.getByLabelText('From date')).toBeInTheDocument()
    expect(screen.queryByText('From date')).not.toBeInTheDocument()
  })
})

describe('DatePicker on a light panel', () => {
  it('marks the surface so a light container does not get a dark field', () => {
    const { container } = render(<DatePicker label="Due date" value="" onChange={vi.fn()} surface="light" />)
    expect(container.querySelector('.db-datepicker--light')).toBeInTheDocument()
  })
})
