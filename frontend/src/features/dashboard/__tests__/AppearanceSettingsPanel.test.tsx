import { useState } from 'react'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Link, MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { ThemeProvider, useTheme } from '../../../contexts/ThemeContext'
import { useAuthStore } from '../../../stores/authStore'
import { garageOwnerSession } from '../../../test-fixtures/db035/staffSession'
import { presentationFixture } from '../../../test-fixtures/db035/appearance'
import AppearanceSettingsPanel from '../AppearanceSettingsPanel'
import { AppearanceNavigationGuardProvider } from '../AppearanceNavigationGuard'
import STAFF_CSS from '../../../index.css?inline'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn() }))
vi.mock('../../../lib/api', () => ({ default: apiMocks }))

function RepairOrdersProbe() {
  const navigate = useNavigate()
  const { mode, hasUnappliedChanges } = useTheme()
  return <>
    <output aria-label="repair appearance">{mode}:{hasUnappliedChanges ? 'draft' : 'committed'}</output>
    <button type="button" onClick={() => navigate(-1)}>Browser back</button>
  </>
}

function SettingsProbe() {
  const [section, setSection] = useState<'appearance' | 'profile'>('appearance')
  const { mode, hasUnappliedChanges } = useTheme()
  return <>
    <button type="button" className="db-settings-nav-item" onClick={() => setSection('profile')}>Profile section</button>
    <Link to="/dashboard/repair-orders">Repair Orders route</Link>
    <output aria-label="settings appearance">{mode}:{hasUnappliedChanges ? 'draft' : 'committed'}</output>
    {section === 'appearance' ? <AppearanceSettingsPanel /> : <div>Profile content</div>}
  </>
}

function RouterHarness({ initialPath = '/dashboard/settings' }: { initialPath?: string }) {
  return <MemoryRouter initialEntries={[initialPath]}>
    <ThemeProvider>
      <AppearanceNavigationGuardProvider>
        <div className="db-staff-shell">
          <Routes>
            <Route path="/dashboard/settings" element={<SettingsProbe />} />
            <Route path="/dashboard/repair-orders" element={<RepairOrdersProbe />} />
          </Routes>
        </div>
      </AppearanceNavigationGuardProvider>
    </ThemeProvider>
  </MemoryRouter>
}

beforeEach(() => {
  localStorage.clear()
  apiMocks.get.mockReset()
  apiMocks.put.mockReset()
  apiMocks.delete.mockReset()
  useAuthStore.setState({ user: garageOwnerSession as never, isAuthenticated: true, authProvider: 'legacy', authSessionEpoch: 1 })
})

it('keeps appearance changes reversible and exposes semantic preview states', async () => {
  const user = userEvent.setup()
  render(<ThemeProvider><AppearanceSettingsPanel /></ThemeProvider>)
  expect(screen.getByRole('heading', { name: 'Appearance' })).toBeInTheDocument()
  expect(screen.getByText('Ready to close')).toHaveClass('is-success')
  expect(screen.getByText('Authorization pending')).toHaveClass('is-warning')
  await user.click(screen.getByRole('button', { name: /Rose/i }))
  expect(screen.getByRole('status')).toHaveTextContent('Previewing changes')
  await user.click(screen.getByRole('button', { name: /Cancel/i }))
  expect(screen.getByRole('status')).toHaveTextContent('Up to date')
})

it('requires confirmation before resetting saved appearance', async () => {
  const user = userEvent.setup()
  render(<ThemeProvider><AppearanceSettingsPanel /></ThemeProvider>)
  await user.click(screen.getByRole('button', { name: /Rose/i }))
  await user.click(screen.getByRole('button', { name: 'Reset saved appearance' }))
  expect(screen.getByRole('dialog', { name: 'Reset saved appearance?' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Cyan/i })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('button', { name: 'Keep current' })).toHaveFocus()
  await user.click(screen.getByRole('button', { name: 'Keep current' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Reset saved appearance' })).toHaveFocus()
})

it('keeps large type selected independently from workspace density', async () => {
  const user = userEvent.setup()
  render(<ThemeProvider><AppearanceSettingsPanel /></ThemeProvider>)
  const [largeType] = screen.getAllByRole('button', { name: 'Large' })
  await user.click(largeType)
  expect(largeType).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('button', { name: /Balanced density/i })).toHaveAttribute('aria-pressed', 'true')
})

it('renders a contrast-safe accent ramp for the selected operating surface', async () => {
  const user = userEvent.setup()
  render(<ThemeProvider><AppearanceSettingsPanel /></ThemeProvider>)

  expect(screen.getByText('Night shop palette: brighter signals tuned for the navy field.')).toBeInTheDocument()
  const cyan = screen.getByRole('button', { name: 'Cyan' })
  expect(cyan.querySelector('.db-appearance-swatch')).toHaveStyle({ backgroundColor: '#22d3ee' })

  await user.click(screen.getByRole('button', { name: /Day shop/ }))
  expect(screen.getByText('Day shop palette: deeper action colors tuned for road-white surfaces.')).toBeInTheDocument()
  expect(cyan.querySelector('.db-appearance-swatch')).toHaveStyle({ backgroundColor: '#0f766e' })

  await user.click(screen.getByRole('button', { name: /High contrast/ }))
  expect(screen.getByText('High contrast palette: opaque, high-separation accents for the selected surface.')).toBeInTheDocument()
  expect(cyan.querySelector('.db-appearance-swatch')).toHaveStyle({ backgroundColor: '#22d3ee' })
})

it('summarizes a draft and keeps editing as the safe navigation default', async () => {
  const user = userEvent.setup()
  const committedLight = presentationFixture('new', { ...garageOwnerSession.presentation.appearance, mode: 'light' })
  useAuthStore.setState({ user: { ...garageOwnerSession, presentation: committedLight } as never })
  const { container } = render(<RouterHarness />)
  const shell = container.querySelector('.db-staff-shell')

  await waitFor(() => expect(shell).toHaveAttribute('data-appearance-mode', 'light'))
  await user.click(screen.getByRole('button', { name: /Night shop/ }))
  expect(shell).toHaveAttribute('data-appearance-mode', 'dark')
  await user.click(screen.getByRole('link', { name: 'Repair Orders route' }))
  const dialog = screen.getByRole('dialog', { name: 'Apply appearance changes?' })
  expect(dialog).toBeInTheDocument()
  expect(within(dialog).getByText('Surface mode')).toBeInTheDocument()
  expect(within(dialog).getByText('Day shop')).toBeInTheDocument()
  expect(within(dialog).getByText('Night shop')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Keep editing' })).toHaveFocus()
  expect(screen.queryByLabelText('repair appearance')).not.toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Keep editing' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByLabelText('settings appearance')).toHaveTextContent('dark:draft')
  expect(shell).toHaveAttribute('data-appearance-mode', 'dark')
  expect(apiMocks.put).not.toHaveBeenCalled()
})

it('discards a preview before continuing to another settings section', async () => {
  const user = userEvent.setup()
  const committedLight = presentationFixture('new', { ...garageOwnerSession.presentation.appearance, mode: 'light' })
  useAuthStore.setState({ user: { ...garageOwnerSession, presentation: committedLight } as never })
  const { container } = render(<RouterHarness />)

  await user.click(screen.getByRole('button', { name: /Night shop/ }))
  await user.click(screen.getByRole('button', { name: 'Profile section' }))
  expect(screen.getByRole('dialog', { name: 'Apply appearance changes?' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Discard & continue' }))

  expect(screen.getByText('Profile content')).toBeInTheDocument()
  expect(screen.getByLabelText('settings appearance')).toHaveTextContent('light:committed')
  expect(container.querySelector('.db-staff-shell')).toHaveAttribute('data-appearance-mode', 'light')
  expect(apiMocks.put).not.toHaveBeenCalled()
})

it('applies successfully before continuing to another page', async () => {
  const user = userEvent.setup()
  const committedLight = presentationFixture('new', { ...garageOwnerSession.presentation.appearance, mode: 'light' })
  const committedDark = presentationFixture('new', { ...garageOwnerSession.presentation.appearance, mode: 'dark' })
  useAuthStore.setState({ user: { ...garageOwnerSession, presentation: committedLight } as never })
  apiMocks.put.mockResolvedValue({ data: committedDark })
  render(<RouterHarness />)

  await user.click(screen.getByRole('button', { name: /Night shop/ }))
  await user.click(screen.getByRole('link', { name: 'Repair Orders route' }))
  await user.click(screen.getByRole('button', { name: 'Apply & continue' }))

  await waitFor(() => expect(apiMocks.put).toHaveBeenCalledTimes(1))
  expect(screen.getByLabelText('repair appearance')).toHaveTextContent('dark:committed')
})

it('stays on Appearance when saving before navigation fails', async () => {
  const user = userEvent.setup()
  const committedLight = presentationFixture('new', { ...garageOwnerSession.presentation.appearance, mode: 'light' })
  useAuthStore.setState({ user: { ...garageOwnerSession, presentation: committedLight } as never })
  apiMocks.put.mockRejectedValue(new Error('offline'))
  render(<RouterHarness />)

  await user.click(screen.getByRole('button', { name: /Night shop/ }))
  await user.click(screen.getByRole('link', { name: 'Repair Orders route' }))
  await user.click(screen.getByRole('button', { name: 'Apply & continue' }))

  await waitFor(() => expect(apiMocks.put).toHaveBeenCalledTimes(1))
  expect(screen.getByRole('dialog', { name: 'Apply appearance changes?' })).toBeInTheDocument()
  expect(screen.getByLabelText('settings appearance')).toHaveTextContent('dark:draft')
  expect(screen.queryByLabelText('repair appearance')).not.toBeInTheDocument()
})

it('registers a native unload warning only while an appearance draft exists', async () => {
  const user = userEvent.setup()
  render(<RouterHarness />)

  const cleanUnload = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(cleanUnload)
  expect(cleanUnload.defaultPrevented).toBe(false)

  await user.click(screen.getByRole('button', { name: /Day shop/ }))
  const dirtyUnload = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(dirtyUnload)
  expect(dirtyUnload.defaultPrevented).toBe(true)
})

it('persists an applied preview across navigation but abandons an unapplied preview on reload', async () => {
  const user = userEvent.setup()
  const committedLight = presentationFixture('new', { ...garageOwnerSession.presentation.appearance, mode: 'light' })
  const committedDark = presentationFixture('new', { ...garageOwnerSession.presentation.appearance, mode: 'dark' })
  useAuthStore.setState({ user: { ...garageOwnerSession, presentation: committedLight } as never })
  apiMocks.put.mockResolvedValue({ data: committedDark })
  const first = render(<RouterHarness />)

  await user.click(screen.getByRole('button', { name: /Night shop/ }))
  await user.click(screen.getByRole('button', { name: 'Apply appearance' }))
  await waitFor(() => expect(apiMocks.put).toHaveBeenCalledTimes(1))
  await user.click(screen.getByRole('link', { name: 'Repair Orders route' }))
  expect(screen.getByLabelText('repair appearance')).toHaveTextContent('dark:committed')
  first.unmount()

  useAuthStore.setState({ user: { ...garageOwnerSession, presentation: committedLight } as never, authSessionEpoch: 2 })
  const abandoned = render(<RouterHarness />)
  await user.click(screen.getByRole('button', { name: /Night shop/ }))
  expect(screen.getByLabelText('settings appearance')).toHaveTextContent('dark:draft')
  abandoned.unmount()

  render(<RouterHarness />)
  expect(screen.getByLabelText('settings appearance')).toHaveTextContent('light:committed')
  expect(apiMocks.put).toHaveBeenCalledTimes(1)
})

describe('Appearance selection is visible', () => {
  // The selected treatment was written as `.db-appearance-choice.is-selected`
  // (two classes) while the base rule is scoped
  // `.db-presentation-new .db-staff-content .db-appearance-choice` (three), so
  // the base won and the selected background and border never rendered. Every
  // section looked unselected; what read as selection on screen was the focus
  // ring. Nothing in a component test can see that, so assert the cascade.
  // Match the selector on its own line. A pattern like /[^{}]*\.foo \{/ looks
  // right but [^{}]* also crosses newlines, so it swallows every preceding
  // declaration and the class counts stop meaning anything — that mistake made
  // an earlier version of this test pass against the very bug it describes.
  const selector = (needle: string) =>
    STAFF_CSS.split('\n').find(line => line.trimStart().startsWith(needle) && line.includes('{'))?.split('{')[0].trim() ?? ''
  const classCount = (sel: string) => (sel.match(/\./g) ?? []).length

  const baseRule = selector('.db-presentation-new .db-staff-content .db-appearance-choice {')
  const selectedRuleSelector = STAFF_CSS.split('\n').find(l => l.includes('.db-appearance-choice.is-selected'))?.split('{')[0].trim() ?? ''
  const hoverRuleSelector = STAFF_CSS.split('\n').find(l => l.includes('.db-appearance-choice:hover'))?.split('{')[0].trim() ?? ''
  const selectedRule = selectedRuleSelector
  const hoverRule = hoverRuleSelector

  it('gives the selected rule more weight than the base rule it must override', () => {
    expect(classCount(selectedRule)).toBeGreaterThan(classCount(baseRule))
  })

  it('gives the hover rule enough weight to show at all', () => {
    expect(classCount(hoverRule)).toBeGreaterThanOrEqual(classCount(baseRule))
  })

  it('lifts the selected option off the page rather than only tinting it', () => {
    expect(selectedRule).toBeTruthy()
    const start = STAFF_CSS.indexOf('.db-appearance-choice.is-selected')
    const body = STAFF_CSS.slice(start, STAFF_CSS.indexOf('}', start))
    expect(body).toContain('box-shadow')
    // A tint over `transparent` stains the page instead of raising a surface.
    expect(body).toContain('var(--surface-raised)')
  })

  it('gives Night shop selected segments a caught-light edge and visible depth', () => {
    const needle = ".db-presentation-new[data-appearance-mode='dark'] .db-appearance-segment button.is-selected"
    const start = STAFF_CSS.indexOf(needle)
    expect(start).toBeGreaterThan(-1)
    const body = STAFF_CSS.slice(start, STAFF_CSS.indexOf('}', start))

    expect(body).toContain('color-mix(in srgb, var(--surface-raised)')
    expect(body).toContain('inset 0 1px 0 rgba(255, 255, 255, .12)')
    expect(body).toContain('0 10px 24px rgba(0, 0, 0, .24)')
  })
})
