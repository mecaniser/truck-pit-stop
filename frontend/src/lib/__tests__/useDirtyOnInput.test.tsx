/** DB-076: a form shell counts as unsaved work once someone types in it. */
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, describe, expect, it } from 'vitest'
import { isDirtyFormRegistered, resetStaleBuild, useDirtyOnInput } from '../staleBuild'
import { Modal } from '../../features/fleet/FleetModals'
import SlidePanel from '../../components/SlidePanel'

afterEach(() => { cleanup(); resetStaleBuild() })

function Shell({ open = true }: { open?: boolean }) {
  const onInputCapture = useDirtyOnInput(open)
  return open ? <div onInputCapture={onInputCapture}><input aria-label="notes" /></div> : null
}

describe('useDirtyOnInput', () => {
  it('stays clean while a form is merely open', () => {
    render(<Shell />)
    expect(isDirtyFormRegistered()).toBe(false)
  })

  it('registers unsaved work on the first keystroke', async () => {
    render(<Shell />)
    await userEvent.type(screen.getByLabelText('notes'), 'x')
    expect(isDirtyFormRegistered()).toBe(true)
  })

  it('releases when the form closes', async () => {
    const { rerender } = render(<Shell />)
    await userEvent.type(screen.getByLabelText('notes'), 'x')
    rerender(<Shell open={false} />)
    expect(isDirtyFormRegistered()).toBe(false)
  })

  it('releases when the form unmounts', async () => {
    const { unmount } = render(<Shell />)
    await userEvent.type(screen.getByLabelText('notes'), 'x')
    unmount()
    expect(isDirtyFormRegistered()).toBe(false)
  })

  it('registers once however much is typed, so one close releases it', async () => {
    const { rerender } = render(<Shell />)
    await userEvent.type(screen.getByLabelText('notes'), 'several words')
    rerender(<Shell open={false} />)
    expect(isDirtyFormRegistered()).toBe(false)
  })
})

describe('shells that hold fleet forms', () => {
  it('a fleet Modal becomes unsaved work once typed in', async () => {
    render(<Modal title="Log incident" icon={null} onClose={() => {}}><input aria-label="what happened" /></Modal>)
    expect(isDirtyFormRegistered()).toBe(false)
    // Modal moves focus to itself on the next animation frame. Typing before
    // that frame lands loses the keystrokes to the dialog, which made this test
    // flake under full-suite load. Wait for the modal to settle, as a person does.
    await waitFor(() => expect(screen.getByRole('dialog')).toHaveFocus())
    await userEvent.type(screen.getByLabelText('what happened'), 'air leak')
    expect(isDirtyFormRegistered()).toBe(true)
  })

  it('a SlidePanel becomes unsaved work once typed in, and releases on close', async () => {
    function Harness() {
      const [open, setOpen] = useState(true)
      return (
        <>
          <button onClick={() => setOpen(false)}>close it</button>
          <SlidePanel isOpen={open} onClose={() => setOpen(false)} title="Edit truck"><input aria-label="unit" /></SlidePanel>
        </>
      )
    }
    render(<Harness />)
    // Same settling as the Modal case: SlidePanel also takes focus on a frame.
    await waitFor(() => expect(screen.getByRole('dialog')).toHaveFocus())
    await userEvent.type(screen.getByLabelText('unit'), '42')
    expect(isDirtyFormRegistered()).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: 'close it' }))
    expect(isDirtyFormRegistered()).toBe(false)
  })
})
