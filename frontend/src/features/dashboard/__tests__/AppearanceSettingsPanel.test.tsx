import { useState } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { Link, MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { ThemeProvider, useTheme } from '../../../contexts/ThemeContext'
import { useAuthStore } from '../../../stores/authStore'
import { garageOwnerSession } from '../../../test-fixtures/db035/staffSession'
import { presentationFixture } from '../../../test-fixtures/db035/appearance'
import AppearanceSettingsPanel from '../AppearanceSettingsPanel'

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
    <button type="button" onClick={() => setSection('profile')}>Profile section</button>
    <Link to="/dashboard/repair-orders">Repair Orders route</Link>
    <output aria-label="settings appearance">{mode}:{hasUnappliedChanges ? 'draft' : 'committed'}</output>
    {section === 'appearance' ? <AppearanceSettingsPanel /> : <div>Profile content</div>}
  </>
}

function RouterHarness({ initialPath = '/dashboard/settings' }: { initialPath?: string }) {
  return <MemoryRouter initialEntries={[initialPath]}>
    <ThemeProvider>
      <div className="db-staff-shell">
        <Routes>
          <Route path="/dashboard/settings" element={<SettingsProbe />} />
          <Route path="/dashboard/repair-orders" element={<RepairOrdersProbe />} />
        </Routes>
      </div>
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

it('restores committed appearance before a route destination and section switch are presented', async () => {
  const user = userEvent.setup()
  const committedLight = presentationFixture('new', { ...garageOwnerSession.presentation.appearance, mode: 'light' })
  useAuthStore.setState({ user: { ...garageOwnerSession, presentation: committedLight } as never })
  const { container } = render(<RouterHarness />)
  const shell = container.querySelector('.db-staff-shell')

  await waitFor(() => expect(shell).toHaveAttribute('data-appearance-mode', 'light'))
  await waitFor(() => expect(localStorage.getItem('dieselbridge:presentation:v1:tenant-wisconsin:user-owner')).not.toBeNull())
  const committedCache = localStorage.getItem('dieselbridge:presentation:v1:tenant-wisconsin:user-owner')

  await user.click(screen.getByRole('button', { name: /Night shop/ }))
  expect(shell).toHaveAttribute('data-appearance-mode', 'dark')
  expect(apiMocks.put).not.toHaveBeenCalled()
  expect(localStorage.getItem('dieselbridge:presentation:v1:tenant-wisconsin:user-owner')).toBe(committedCache)

  await user.click(screen.getByRole('link', { name: 'Repair Orders route' }))
  expect(screen.getByLabelText('repair appearance')).toHaveTextContent('light:committed')
  expect(shell).toHaveAttribute('data-appearance-mode', 'light')
  expect(apiMocks.put).not.toHaveBeenCalled()

  await user.click(screen.getByRole('button', { name: 'Browser back' }))
  expect(screen.getByLabelText('settings appearance')).toHaveTextContent('light:committed')
  expect(screen.getByRole('button', { name: /Day shop/ })).toHaveAttribute('aria-pressed', 'true')

  await user.click(screen.getByRole('button', { name: /Night shop/ }))
  await user.click(screen.getByRole('button', { name: 'Profile section' }))
  expect(screen.getByText('Profile content')).toBeInTheDocument()
  expect(screen.getByLabelText('settings appearance')).toHaveTextContent('light:committed')
  expect(shell).toHaveAttribute('data-appearance-mode', 'light')
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
