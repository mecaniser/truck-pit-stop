import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import ConnectionNotice from '../ConnectionNotice'
import { startRequest, finishRequest, useRequestActivity } from '../../lib/requestActivity'
afterEach(() => { cleanup(); vi.useRealTimers(); useRequestActivity.setState({ slow: 0 }); Object.defineProperty(navigator, 'onLine', { configurable: true, value: true }) })
it('keeps offline guidance visible until connectivity returns', () => {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
  render(<ConnectionNotice />)
  expect(screen.getByRole('status')).toHaveTextContent('You’re offline')
  act(() => { Object.defineProperty(navigator, 'onLine', { configurable: true, value: true }); window.dispatchEvent(new Event('online')) })
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})
it('tracks each delayed request and clears on success, failure or cancellation cleanup', () => {
  vi.useFakeTimers()
  render(<ConnectionNotice />)
  const first = {}, second = {}
  act(() => { startRequest(first); startRequest(second); vi.advanceTimersByTime(7999) })
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  act(() => { vi.advanceTimersByTime(1) })
  expect(screen.getByRole('status')).toHaveTextContent('taking longer')
  act(() => finishRequest(first))
  expect(screen.getByRole('status')).toBeInTheDocument()
  act(() => { finishRequest(second); finishRequest(second) })
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})
