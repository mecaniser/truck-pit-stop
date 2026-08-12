import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { ThemeProvider } from '../../../contexts/ThemeContext'
import { useAuthStore } from '../../../stores/authStore'
import { garageOwnerSession } from '../../../test-fixtures/db035/staffSession'
import AppearanceSettingsPanel from '../AppearanceSettingsPanel'

vi.mock('../../../lib/api', () => ({ default: { put: vi.fn(), delete: vi.fn() } }))

beforeEach(() => {
  localStorage.clear()
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
