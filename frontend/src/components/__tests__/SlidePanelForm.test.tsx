import { useState } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({ accentColors: { 500: '#a53f2f' } }),
}))

import SlidePanelForm from '../SlidePanelForm'

function PanelHarness() {
  const [open, setOpen] = useState(false)
  return <>
    <button type="button" onClick={() => setOpen(true)}>Open drawer</button>
    <SlidePanelForm isOpen={open} onClose={() => setOpen(false)} title="Add Part" onSubmit={(event) => event.preventDefault()} submitLabel="Add Part">
      <label>Part name<input autoFocus /></label>
    </SlidePanelForm>
  </>
}

describe('SlidePanelForm', () => {
  it('names the modal close control and keeps keyboard focus inside the drawer', async () => {
    const user = userEvent.setup()
    render(<PanelHarness />)

    const opener = screen.getByRole('button', { name: 'Open drawer' })
    await user.click(opener)
    const dialog = screen.getByRole('dialog', { name: 'Add Part' })
    const close = screen.getByRole('button', { name: 'Close Add Part' })
    const submit = screen.getByRole('button', { name: 'Add Part' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')

    submit.focus()
    await user.tab()
    expect(close).toHaveFocus()
    await user.tab({ shift: true })
    expect(submit).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Add Part' })).not.toBeInTheDocument()
    await waitFor(() => expect(opener).toHaveFocus())
  })
})
