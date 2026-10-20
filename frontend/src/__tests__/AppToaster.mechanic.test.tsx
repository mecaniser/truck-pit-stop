import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import toast from 'react-hot-toast'

vi.mock('../contexts/ThemeContext', () => ({
  ThemeProvider: ({ children }: { children: React.ReactNode }) => children,
  useTheme: () => ({ notificationPosition: 'bottom', presentationVariant: 'new' }),
}))

import { AppToaster } from '../App'

beforeEach(() => {
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }))
})

afterEach(() => {
  act(() => { toast.remove() })
  cleanup()
  vi.unstubAllGlobals()
})

describe('mechanic toast placement', () => {
  it('shows a mechanic action error at the top despite a bottom notification preference', async () => {
    render(<MemoryRouter initialEntries={['/mechanic/jobs']}><AppToaster /></MemoryRouter>)

    act(() => { toast.error('Timer could not start') })

    expect(await screen.findByText('Timer could not start')).toBeInTheDocument()
    const container = document.querySelector<HTMLElement>('.db-toaster')
    expect(container?.style.top).toContain('safe-area-inset-top')
    expect((container?.firstElementChild as HTMLElement)?.style.top).toBe('0px')
  })

  it('keeps the chosen bottom position on other routes', async () => {
    render(<MemoryRouter initialEntries={['/dashboard']}><AppToaster /></MemoryRouter>)

    act(() => { toast.error('Other error') })

    expect(await screen.findByText('Other error')).toBeInTheDocument()
    const container = document.querySelector<HTMLElement>('.db-toaster')
    expect(container?.style.bottom).toContain('safe-area-inset-bottom')
    expect((container?.firstElementChild as HTMLElement)?.style.bottom).toBe('0px')
  })
})
