import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
import ViewToggle from '../ViewToggle'
import { ThemeProvider } from '../../contexts/ThemeContext'

function renderToggle(props?: Partial<ComponentProps<typeof ViewToggle>>) {
  const onChange = props?.onChange ?? vi.fn()
  render(
    <ThemeProvider>
      <ViewToggle value="list" onChange={onChange} {...props} />
    </ThemeProvider>,
  )
  return onChange
}

describe('ViewToggle', () => {
  it('offers cards when the current view is list', async () => {
    const user = userEvent.setup()
    const onChange = renderToggle()

    await user.click(screen.getByRole('button', { name: 'Show cards' }))
    expect(onChange).toHaveBeenCalledWith('cards')
  })

  it('offers list when the current view is cards', async () => {
    const user = userEvent.setup()
    const onChange = renderToggle({ value: 'cards' })

    await user.click(screen.getByRole('button', { name: 'Show list' }))
    expect(onChange).toHaveBeenCalledWith('list')
  })

  it('uses native disabled buttons', () => {
    renderToggle({ disabled: true })

    expect(screen.getByRole('button', { name: 'Show cards' })).toBeDisabled()
  })
})
