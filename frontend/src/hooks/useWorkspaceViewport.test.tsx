import { act, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useWorkspaceViewport } from './useWorkspaceViewport'

function Harness() { useWorkspaceViewport(); return null }
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('compact workspace visible viewport', () => {
  it('follows keyboard resize and pan, preserves pinch zoom, and cleans up on unmount', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() } as unknown as MediaQueryList)
    const viewport = Object.assign(new EventTarget(), { height: 700, offsetTop: 0, scale: 1 })
    vi.stubGlobal('visualViewport', viewport)
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(cb => { cb(0); return 1 })
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
    const { unmount } = render(<Harness />)
    const style = document.documentElement.style
    expect(style.getPropertyValue('--db-workspace-viewport-height')).toBe('700px')
    act(() => { viewport.height = 380; viewport.offsetTop = 40; viewport.dispatchEvent(new Event('resize')) })
    expect(style.getPropertyValue('--db-workspace-viewport-height')).toBe('380px')
    expect(style.getPropertyValue('--db-workspace-viewport-top')).toBe('40px')
    act(() => { viewport.scale = 2; viewport.dispatchEvent(new Event('resize')) })
    expect(style.getPropertyValue('--db-workspace-viewport-height')).toBe('')
    act(() => { viewport.scale = 1; viewport.dispatchEvent(new Event('scroll')) })
    expect(style.getPropertyValue('--db-workspace-viewport-height')).toBe('380px')
    unmount()
    expect(style.getPropertyValue('--db-workspace-viewport-height')).toBe('')
    expect(style.getPropertyValue('--db-workspace-viewport-top')).toBe('')
  })
  it('leaves desktop viewport and CSS alone', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() } as unknown as MediaQueryList)
    const viewport = Object.assign(new EventTarget(), { height: 380, offsetTop: 0, scale: 1 })
    vi.stubGlobal('visualViewport', viewport)
    render(<Harness />)
    expect(document.documentElement.style.getPropertyValue('--db-workspace-viewport-height')).toBe('')
  })
})
