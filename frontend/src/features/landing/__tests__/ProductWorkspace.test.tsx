import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ProductWorkspace from '../ProductWorkspace'

const MODULES = [
  ['Repair Orders', 'lucide-clipboard-list'],
  ['Customers', 'lucide-users'],
  ['Shop Work', 'lucide-wrench'],
  ['Invoices', 'lucide-file-text'],
  ['Vehicle History', 'lucide-history'],
] as const

describe('ProductWorkspace', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      disconnect() {}
    })
    vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1))
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    })
  })

  afterEach(() => {
    act(() => { vi.runOnlyPendingTimers() })
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('uses the exact product rail, roving focus, and one silent-on-load live region', () => {
    render(<ProductWorkspace />)

    const tabs = screen.getAllByRole('tab', { hidden: true }).filter((tab) =>
      MODULES.some(([label]) => label === tab.textContent),
    )
    expect(tabs.map((tab) => tab.textContent)).toEqual(MODULES.map(([label]) => label))
    MODULES.forEach(([label, iconClass], index) => {
      const tab = screen.getByRole('tab', { name: label })
      expect(tab.querySelector(`.${iconClass}`)).toBeInTheDocument()
      expect(tab).toHaveAttribute('tabindex', index === 0 ? '0' : '-1')
    })

    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('')
    expect(status).toHaveAttribute('aria-live', 'polite')
    expect(status).toHaveAttribute('aria-atomic', 'true')

    const first = screen.getByRole('tab', { name: 'Repair Orders' })
    first.focus()
    fireEvent.keyDown(first, { key: 'End' })
    expect(screen.getByRole('tab', { name: 'Vehicle History' })).toHaveFocus()
    expect(screen.getByRole('tab', { name: 'Vehicle History' })).toHaveAttribute('aria-selected', 'true')

    act(() => { vi.advanceTimersByTime(120) })
    expect(status).toHaveTextContent(/Vehicle History preview selected/)
  })

  it('preserves authentic local selections and announces only the latest rapid change', () => {
    render(<ProductWorkspace />)

    fireEvent.click(screen.getByRole('tab', { name: 'Customers' }))
    fireEvent.click(screen.getByRole('button', { name: 'Riverbend Freight' }))
    fireEvent.click(screen.getByRole('tab', { name: 'History' }))
    fireEvent.click(screen.getByRole('tab', { name: 'Shop Work' }))
    fireEvent.click(screen.getByRole('tab', { name: 'Activity' }))
    fireEvent.click(screen.getByRole('tab', { name: 'Invoices' }))
    fireEvent.click(screen.getByRole('button', { name: /Invoice INV-2025-0419/i }))
    fireEvent.click(screen.getByRole('tab', { name: 'Customers' }))

    expect(screen.getByRole('tab', { name: 'History' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getAllByRole('heading', { name: 'Riverbend Freight' }).length).toBeGreaterThan(0)

    ;['Repair Orders', 'Customers', 'Shop Work', 'Invoices', 'Vehicle History', 'Repair Orders', 'Customers', 'Shop Work', 'Invoices', 'Vehicle History']
      .forEach((label) => fireEvent.click(screen.getByRole('tab', { name: label })))
    act(() => { vi.advanceTimersByTime(120) })

    expect(screen.getByRole('tab', { name: 'Vehicle History' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('status')).toHaveTextContent(/Vehicle History preview selected/)
    expect(screen.getByRole('status')).not.toHaveTextContent(/Invoices preview selected/)
  })

  it('keeps controls functional without enhancement APIs and performs no application side effects', () => {
    vi.unstubAllGlobals()
    Object.defineProperty(window, 'matchMedia', { configurable: true, value: undefined })
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('preview must not fetch'))
    const storageSpy = vi.spyOn(Storage.prototype, 'setItem')
    const WebSocketSpy = vi.fn()
    vi.stubGlobal('WebSocket', WebSocketSpy)

    render(<ProductWorkspace />)
    const customers = screen.getByRole('tab', { name: 'Customers' })
    fireEvent.pointerDown(customers)
    expect(customers).toHaveAttribute('data-pressed', 'true')
    fireEvent.pointerCancel(customers)
    expect(customers).not.toHaveAttribute('data-pressed')
    fireEvent.click(customers)
    fireEvent.click(screen.getByRole('button', { name: 'Riverbend Freight' }))
    fireEvent.click(screen.getByRole('tab', { name: 'History' }))

    expect(screen.getAllByRole('complementary')).toHaveLength(2)
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(storageSpy).not.toHaveBeenCalled()
    expect(WebSocketSpy).not.toHaveBeenCalled()
  })

  it('omits unselected vehicle evidence and restores it only after a repair is opened', () => {
    render(<ProductWorkspace />)

    expect(screen.getAllByRole('complementary')).toHaveLength(2)
    fireEvent.click(screen.getByRole('tab', { name: 'Vehicle History' }), { detail: 1 })
    expect(screen.getAllByRole('complementary')).toHaveLength(1)
    expect(screen.queryByLabelText(/^Selected evidence:/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /RO-2025-0417/i }), { detail: 1 })
    expect(screen.getAllByRole('complementary')).toHaveLength(2)
    expect(screen.getByLabelText(/Selected evidence: RO-2025-0417/)).toBeInTheDocument()
  })

  it('commits keyboard selections without spatial WAAPI while pointer selections remain animated', () => {
    const animate = vi.fn(() => ({
      cancel: vi.fn(),
      commitStyles: vi.fn(),
    }))
    const originalAnimate = Element.prototype.animate
    Object.defineProperty(Element.prototype, 'animate', { configurable: true, value: animate })

    try {
      render(<ProductWorkspace />)
      fireEvent.click(screen.getByRole('tab', { name: 'Customers' }), { detail: 1 })
      animate.mockClear()

      const history = screen.getByRole('tab', { name: 'History' })
      history.focus()
      fireEvent.click(history, { detail: 0 })
      expect(history).toHaveFocus()
      expect(history).toHaveAttribute('aria-selected', 'true')
      expect(animate).not.toHaveBeenCalled()

      act(() => { vi.advanceTimersByTime(120) })
      expect(screen.getByRole('status')).toHaveTextContent(/Customers: NorthStar Logistics history selected/)

      fireEvent.click(screen.getByRole('button', { name: 'Riverbend Freight' }), { detail: 1 })
      expect(animate).toHaveBeenCalled()
    } finally {
      Object.defineProperty(Element.prototype, 'animate', { configurable: true, value: originalAnimate })
    }
  })
})
