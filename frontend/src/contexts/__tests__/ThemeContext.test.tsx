import { StrictMode } from 'react'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider, appearanceTokenRecord, useTheme } from '../ThemeContext'
import { useAuthStore } from '../../stores/authStore'
import { fleetManagerWithoutMessaging, garageOwnerSession, sameUserOtherTenant } from '../../test-fixtures/db035/staffSession'
import { presentationFixture } from '../../test-fixtures/db035/appearance'
import { isPresentationBootstrap, type AppearancePreferences } from '../../types/presentation'
import { renderPresentationSurface, STAFF_SURFACES } from '../../test-fixtures/db035/presentationRenderHarness'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn() }))
vi.mock('../../lib/api', () => ({ default: apiMocks }))
vi.mock('react-hot-toast', () => ({ toast: { success: vi.fn(), error: vi.fn() }, default: { success: vi.fn(), error: vi.fn() } }))

function Probe() {
  const theme = useTheme()
  return <>
    <output>{theme.presentationVariant}:{theme.accent}:{theme.mode}:{theme.density}:{theme.hasUnappliedChanges ? 'draft' : 'committed'}</output>
    <output aria-label="save status">{theme.saveStatus}</output>
    <button onClick={() => theme.setAccent('rose')}>Rose</button>
    <button onClick={theme.cancelPreview}>Cancel</button>
    <button onClick={() => void theme.applyAppearance()}>Apply</button>
  </>
}

function StaffProbe() {
  return <div className="db-staff-shell"><Probe /></div>
}

describe('DB-035 presentation provider', () => {
  beforeEach(() => {
    localStorage.clear()
    apiMocks.put.mockReset()
    apiMocks.get.mockReset()
    apiMocks.delete.mockReset()
    useAuthStore.setState({
      user: garageOwnerSession as never,
      isAuthenticated: true,
      authProvider: 'legacy',
      authSessionEpoch: 4,
      logoutInProgress: false,
    })
  })

  it('previews locally, cancels without a request, and applies with optimistic revision', async () => {
    const user = userEvent.setup()
    apiMocks.put.mockResolvedValue({ data: presentationFixture('new', { ...garageOwnerSession.presentation.appearance, accent: 'rose' }) })
    render(<ThemeProvider><StaffProbe /></ThemeProvider>)
    expect(screen.getByText('new:cyan:dark:default:committed')).toBeInTheDocument()
    await user.click(screen.getByText('Rose'))
    expect(screen.getByText('new:rose:dark:default:draft')).toBeInTheDocument()
    expect(apiMocks.put).not.toHaveBeenCalled()
    await user.click(screen.getByText('Cancel'))
    expect(screen.getByText('new:cyan:dark:default:committed')).toBeInTheDocument()
    await user.click(screen.getByText('Rose'))
    await user.click(screen.getByText('Apply'))
    expect(apiMocks.put).toHaveBeenCalledWith('/auth/me/appearance', expect.objectContaining({
      schema_version: 1,
      base_revision: 4,
      appearance: expect.objectContaining({ accent: 'rose' }),
    }), expect.any(Object))
  })

  it('preserves legacy immediate theme changes while syncing the same server preference', async () => {
    const user = userEvent.setup()
    const legacy = presentationFixture('legacy')
    useAuthStore.setState({ user: { ...garageOwnerSession, presentation: legacy } as never })
    apiMocks.put.mockResolvedValue({
      data: presentationFixture('legacy', { ...legacy.appearance, accent: 'rose' }),
    })

    render(<ThemeProvider><StaffProbe /></ThemeProvider>)
    await user.click(screen.getByText('Rose'))

    expect(screen.getByText('legacy:rose:dark:default:committed')).toBeInTheDocument()
    expect(localStorage.getItem('theme-accent')).toBe('rose')
    await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith(
      '/auth/me/appearance',
      expect.objectContaining({ appearance: expect.objectContaining({ accent: 'rose' }) }),
      expect.any(Object),
    ))
  })

  it('refreshes a stale legacy bootstrap immediately from the authoritative staff appearance', async () => {
    const staleLegacy = presentationFixture('legacy')
    const authoritativeNew = presentationFixture('new')
    useAuthStore.setState({
      user: { ...garageOwnerSession, presentation: staleLegacy } as never,
    })
    apiMocks.get.mockResolvedValue({ data: authoritativeNew })

    render(<ThemeProvider><StaffProbe /></ThemeProvider>)

    expect(screen.getByText('legacy:cyan:dark:default:committed')).toBeInTheDocument()
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/auth/me/appearance'))
    await waitFor(() => expect(screen.getByText('new:cyan:dark:default:committed')).toBeInTheDocument())
    expect(document.querySelector('.db-staff-shell')).toHaveAttribute('data-presentation', 'new')
  })

  it('does not overwrite an in-progress appearance preview when the mount refresh settles', async () => {
    const user = userEvent.setup()
    let resolveRefresh: ((value: { data: ReturnType<typeof presentationFixture> }) => void) | undefined
    apiMocks.get.mockReturnValue(new Promise(resolve => { resolveRefresh = resolve }))

    render(<ThemeProvider><StaffProbe /></ThemeProvider>)
    await user.click(screen.getByText('Rose'))
    expect(screen.getByText('new:rose:dark:default:draft')).toBeInTheDocument()

    await act(async () => {
      resolveRefresh?.({ data: presentationFixture('new', { ...garageOwnerSession.presentation.appearance, accent: 'indigo' }) })
    })

    expect(screen.getByText('new:rose:dark:default:draft')).toBeInTheDocument()
  })

  it('keys the bootstrap cache to the exact user and tenant identity', () => {
    const { rerender } = render(<ThemeProvider><StaffProbe /></ThemeProvider>)
    expect(localStorage.getItem('dieselbridge:presentation:v1:tenant-wisconsin:user-owner')).toContain('"resolved_variant":"new"')
    act(() => useAuthStore.setState({ user: sameUserOtherTenant as never, authSessionEpoch: 5 }))
    rerender(<ThemeProvider><StaffProbe /></ThemeProvider>)
    expect(document.querySelector('.db-staff-shell')).toHaveAttribute('data-presentation', 'new')
    expect(localStorage.getItem('dieselbridge:presentation:v1:tenant-north-carolina:user-owner')).toContain('"resolved_variant":"new"')
  })

  it('keeps a conflicting preview local and asks the user to review instead of retrying', async () => {
    const user = userEvent.setup()
    apiMocks.put.mockRejectedValue({ response: { status: 409 } })
    apiMocks.get.mockResolvedValue({ data: presentationFixture('new', { ...garageOwnerSession.presentation.appearance, accent: 'indigo' }) })
    render(<ThemeProvider><StaffProbe /></ThemeProvider>)
    await user.click(screen.getByText('Rose'))
    await user.click(screen.getByText('Apply'))
    expect(apiMocks.put).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/auth/me/appearance'))
    expect(screen.getByLabelText('save status')).toHaveTextContent('idle')
    expect(screen.getByText('new:rose:dark:default:draft')).toBeInTheDocument()
  })

  it('removes applied presentation tokens when the authenticated identity ends', () => {
    render(<ThemeProvider><StaffProbe /></ThemeProvider>)
    const shell = document.querySelector<HTMLElement>('.db-staff-shell')
    expect(shell).toHaveAttribute('data-presentation', 'new')
    act(() => useAuthStore.setState({ user: null, isAuthenticated: false, authSessionEpoch: 5 }))
    expect(shell?.style.getPropertyValue('--personal-accent-500')).toBe('')
  })

  it('does not apply staff presentation tokens outside the authenticated staff shell', () => {
    render(<ThemeProvider><main data-testid="public-surface">Public surface</main></ThemeProvider>)
    expect(document.documentElement.style.getPropertyValue('--personal-accent-500')).toBe('')
    expect(screen.getByTestId('public-surface').style.getPropertyValue('--personal-accent-500')).toBe('')
  })

  it('does not request staff appearance for an excluded fleet identity', () => {
    useAuthStore.setState({ user: fleetManagerWithoutMessaging as never })
    render(<ThemeProvider><StaffProbe /></ThemeProvider>)
    expect(apiMocks.get).not.toHaveBeenCalled()
  })

  it('migrates legacy preferences once even when React replays mount effects', async () => {
    localStorage.setItem('theme-accent', 'rose')
    const pendingPresentation = {
      ...garageOwnerSession.presentation,
      legacy_migration_status: 'pending' as const,
    }
    useAuthStore.setState({
      user: { ...garageOwnerSession, presentation: pendingPresentation } as never,
    })
    apiMocks.put.mockResolvedValue({
      data: presentationFixture('new', { ...garageOwnerSession.presentation.appearance, accent: 'rose' }),
    })
    render(<StrictMode><ThemeProvider><StaffProbe /></ThemeProvider></StrictMode>)
    await waitFor(() => expect(apiMocks.put).toHaveBeenCalledTimes(1))
    expect(apiMocks.put).toHaveBeenCalledWith('/auth/me/appearance', expect.objectContaining({
      migration_source: 'legacy_local_v1',
      appearance: expect.objectContaining({ accent: 'rose' }),
    }), expect.objectContaining({ headers: expect.objectContaining({ 'Idempotency-Key': expect.any(String) }) }))
  })

  it('rejects incomplete rollout data instead of activating a presentation', () => {
    const valid = presentationFixture('new')
    expect(isPresentationBootstrap(valid)).toBe(true)
    expect(isPresentationBootstrap({ ...valid, source: 'unknown' })).toBe(false)
    expect(isPresentationBootstrap({ ...valid, legacy_migration_status: undefined })).toBe(false)
    expect(isPresentationBootstrap({ ...valid, updated_at: 42 })).toBe(false)
  })

  it('fails closed to legacy when a malformed server bootstrap conflicts with a cached new presentation', () => {
    localStorage.setItem('dieselbridge:presentation:v1:tenant-wisconsin:user-owner', JSON.stringify({
      schema_version: 1,
      resolved_variant: 'new',
      appearance: garageOwnerSession.presentation.appearance,
      revision: 4,
      timestamp: Date.now(),
    }))
    useAuthStore.setState({
      user: { ...garageOwnerSession, presentation: { ...garageOwnerSession.presentation, source: 'unknown' } } as never,
    })
    render(<ThemeProvider><StaffProbe /></ThemeProvider>)
    expect(screen.getByText('legacy:cyan:dark:default:committed')).toBeInTheDocument()
  })

  it('renders all six surfaces through every appearance combination', () => {
    const accents = ['cyan', 'indigo', 'emerald', 'rose', 'amber'] as const
    const fonts = ['geist', 'dm-sans', 'jakarta', 'inter'] as const
    const sizes = ['small', 'default', 'large'] as const
    const densities = ['compact', 'default', 'comfortable', 'large'] as const
    const modes = ['light', 'dark', 'high_contrast'] as const
    const positions = ['top_right', 'bottom_right', 'top_center'] as const
    let count = 0
    for (const accent of accents) for (const font_family of fonts) for (const font_size of sizes) for (const density of densities) for (const mode of modes) for (const notification_position of positions) {
      const appearance: AppearancePreferences = { accent, font_family, font_size, density, mode, notification_position }
      for (const surface of STAFF_SURFACES) {
        const rendered = renderPresentationSurface(surface, appearance)
        expect(Object.values(rendered.tokens).every(Boolean)).toBe(true)
        expect(rendered.minTarget).toBeGreaterThanOrEqual(44)
        expect(rendered.html).toContain(`data-surface="${surface}"`)
        expect(rendered.html).toContain('semantic-success')
        expect(rendered.html).not.toContain(appearanceTokenRecord(appearance)['--personal-accent-500'])
        count += 1
      }
    }
    expect(count).toBe(12_960)
  })

  it('uses surface-specific accent ramps while preserving the curated accent identifiers', () => {
    const base = { ...garageOwnerSession.presentation.appearance, accent: 'cyan' as const }
    expect(appearanceTokenRecord({ ...base, mode: 'light' })['--personal-accent-500']).toBe('#0f766e')
    expect(appearanceTokenRecord({ ...base, mode: 'dark' })['--personal-accent-500']).toBe('#22d3ee')
    expect(appearanceTokenRecord({ ...base, mode: 'high_contrast' })['--personal-accent-500']).toBe('#22d3ee')
  })
})
