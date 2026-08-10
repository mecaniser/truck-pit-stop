import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { Modal, SidekickPanel } from '../FleetModals'

beforeAll(() => vi.stubGlobal('scrollTo', vi.fn()))
afterAll(() => vi.unstubAllGlobals())

function renderModal({
  onClose = vi.fn(),
  dismissDisabled = false,
}: {
  onClose?: ReturnType<typeof vi.fn>
  dismissDisabled?: boolean
} = {}) {
  const result = render(
    <Modal
      title="Merge duplicate truck"
      icon={<span aria-hidden="true">icon</span>}
      onClose={onClose}
      dismissDisabled={dismissDisabled}
    >
      <button type="button">First action</button>
      <button type="button">Last action</button>
    </Modal>,
  )

  return { ...result, onClose }
}

describe('Fleet Modal accessibility and lifecycle', () => {
  afterEach(() => {
    document.body.style.overflow = ''
    document.documentElement.style.overflow = ''
  })

  it('exposes dialog semantics, labels the close button, and locks page scrolling', async () => {
    const { unmount } = renderModal()

    const dialog = screen.getByRole('dialog', { name: 'Merge duplicate truck' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByRole('button', { name: 'Close Merge duplicate truck' })).toBeEnabled()
    expect(document.body.style.overflow).toBe('hidden')
    expect(document.documentElement.style.overflow).toBe('hidden')
    await waitFor(() => expect(dialog).toHaveFocus())

    unmount()
    expect(document.body.style.overflow).toBe('')
    expect(document.documentElement.style.overflow).toBe('')
  })

  it('dismisses from Escape and from the backdrop, but not from dialog content', async () => {
    const user = userEvent.setup()
    const { onClose } = renderModal()
    const dialog = screen.getByRole('dialog')
    const backdrop = dialog.parentElement

    expect(backdrop).not.toBeNull()
    await user.click(screen.getByRole('button', { name: 'First action' }))
    expect(onClose).not.toHaveBeenCalled()

    fireEvent.click(backdrop!)
    expect(onClose).toHaveBeenCalledTimes(1)

    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('locks every dismissal path while a destructive action is pending', async () => {
    const user = userEvent.setup()
    const { onClose } = renderModal({ dismissDisabled: true })
    const dialog = screen.getByRole('dialog')
    const backdrop = dialog.parentElement
    const closeButton = screen.getByRole('button', { name: 'Close Merge duplicate truck' })

    expect(dialog).toHaveAttribute('aria-busy', 'true')
    expect(closeButton).toBeDisabled()
    await user.click(closeButton)
    fireEvent.click(backdrop!)
    await user.keyboard('{Escape}')

    expect(onClose).not.toHaveBeenCalled()
  })

  it('wraps keyboard focus in both directions', async () => {
    const user = userEvent.setup()
    renderModal()
    const dialog = screen.getByRole('dialog')
    const closeButton = screen.getByRole('button', { name: 'Close Merge duplicate truck' })
    const lastAction = screen.getByRole('button', { name: 'Last action' })

    await waitFor(() => expect(dialog).toHaveFocus())
    lastAction.focus()
    await user.tab()
    expect(closeButton).toHaveFocus()

    closeButton.focus()
    await user.tab({ shift: true })
    expect(lastAction).toHaveFocus()
  })

  it('restores focus to the control that opened it', async () => {
    const opener = document.createElement('button')
    opener.textContent = 'Open merge'
    document.body.appendChild(opener)
    opener.focus()

    const { unmount } = renderModal()
    await waitFor(() => expect(screen.getByRole('dialog')).toHaveFocus())
    unmount()

    expect(opener).toHaveFocus()
    opener.remove()
  })
})

describe('Fleet Sidekick shell', () => {
  it('keeps task variants inside one shared shell contract', () => {
    render(
      <SidekickPanel
        title="TPS-108"
        subtitle="Weekly inspection"
        icon={<span aria-hidden="true">inspection</span>}
        onClose={vi.fn()}
        variant="checklist"
        tone="inspection"
        headerExtra={<div>4 of 19 complete</div>}
        footer={<button type="button">Review and complete</button>}
      >
        <div>Inspection checks</div>
      </SidekickPanel>,
    )

    const dialog = screen.getByRole('dialog', { name: 'TPS-108' })
    expect(dialog).toHaveClass('fleet-sidekick-shell-checklist')
    expect(dialog).toHaveClass('fleet-sidekick-shell-tone-inspection')
    expect(dialog.querySelector('[data-sidekick-variant="checklist"]')).toHaveTextContent('Inspection checks')
    expect(screen.getByText('4 of 19 complete')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Review and complete' })).toBeInTheDocument()
  })
})
