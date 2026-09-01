import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  ACCENT_OPTIONS,
  DENSITY_OPTIONS,
  FONT_FAMILY_OPTIONS,
  MODE_OPTIONS,
  useTheme,
} from '../../contexts/ThemeContext'

type PendingNavigation = {
  run: () => void
  trigger: HTMLElement | null
}

type AppearanceChange = {
  label: string
  before: string
  after: string
}

const labelFor = <T extends string>(
  options: ReadonlyArray<{ id: T; label: string }>,
  id: T,
) => options.find(option => option.id === id)?.label ?? id

const FONT_SIZE_LABELS = {
  small: 'Small',
  default: 'Default',
  large: 'Large',
} as const

const NOTIFICATION_LABELS = {
  top_right: 'Top right',
  bottom_right: 'Bottom right',
  top_center: 'Top center',
} as const

export function AppearanceNavigationGuardProvider({ children }: { children: ReactNode }) {
  const {
    appearance,
    committedAppearance,
    hasUnappliedChanges,
    saveStatus,
    applyAppearance,
    cancelPreview,
  } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const [pending, setPending] = useState<PendingNavigation | null>(null)
  const [continuing, setContinuing] = useState<'apply' | 'discard' | null>(null)
  const keepEditingRef = useRef<HTMLButtonElement>(null)
  const discardRef = useRef<HTMLButtonElement>(null)
  const applyRef = useRef<HTMLButtonElement>(null)
  const bypassInterceptionRef = useRef(false)

  const changes = useMemo<AppearanceChange[]>(() => {
    const candidates: Array<AppearanceChange | null> = [
      appearance.accent === committedAppearance.accent ? null : {
        label: 'Accent',
        before: labelFor(ACCENT_OPTIONS, committedAppearance.accent),
        after: labelFor(ACCENT_OPTIONS, appearance.accent),
      },
      appearance.font_family === committedAppearance.font_family ? null : {
        label: 'Type',
        before: labelFor(FONT_FAMILY_OPTIONS, committedAppearance.font_family),
        after: labelFor(FONT_FAMILY_OPTIONS, appearance.font_family),
      },
      appearance.font_size === committedAppearance.font_size ? null : {
        label: 'Font size',
        before: FONT_SIZE_LABELS[committedAppearance.font_size],
        after: FONT_SIZE_LABELS[appearance.font_size],
      },
      appearance.density === committedAppearance.density ? null : {
        label: 'Workspace density',
        before: labelFor(DENSITY_OPTIONS, committedAppearance.density),
        after: labelFor(DENSITY_OPTIONS, appearance.density),
      },
      appearance.mode === committedAppearance.mode ? null : {
        label: 'Surface mode',
        before: labelFor(MODE_OPTIONS, committedAppearance.mode),
        after: labelFor(MODE_OPTIONS, appearance.mode),
      },
      appearance.notification_position === committedAppearance.notification_position ? null : {
        label: 'Notification location',
        before: NOTIFICATION_LABELS[committedAppearance.notification_position],
        after: NOTIFICATION_LABELS[appearance.notification_position],
      },
    ]
    return candidates.filter((change): change is AppearanceChange => change !== null)
  }, [appearance, committedAppearance])

  const requestNavigation = useCallback((action: () => void) => {
    if (!hasUnappliedChanges) {
      action()
      return
    }
    setPending({
      run: action,
      trigger: document.activeElement instanceof HTMLElement ? document.activeElement : null,
    })
  }, [hasUnappliedChanges])

  useEffect(() => {
    if (!hasUnappliedChanges) return
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [hasUnappliedChanges])

  useEffect(() => {
    if (!hasUnappliedChanges) return
    const interceptNavigation = (event: MouseEvent) => {
      if (bypassInterceptionRef.current) return
      if (
        event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey ||
        event.shiftKey || event.altKey
      ) return
      const target = event.target instanceof Element ? event.target : null
      const anchor = target?.closest<HTMLAnchorElement>('a[href]')
      if (anchor && anchor.target !== '_blank' && !anchor.hasAttribute('download')) {
        const destination = new URL(anchor.href, window.location.href)
        if (destination.origin !== window.location.origin) return
        const next = `${destination.pathname}${destination.search}${destination.hash}`
        const current = `${location.pathname}${location.search}${location.hash}`
        if (next === current) return
        event.preventDefault()
        event.stopPropagation()
        requestNavigation(() => navigate(next))
        return
      }
      const settingsSection = target?.closest<HTMLButtonElement>(
        'button.db-settings-nav-item, button.db-settings-mobile-section-selector__option',
      )
      if (!settingsSection) return
      event.preventDefault()
      event.stopPropagation()
      requestNavigation(() => {
        bypassInterceptionRef.current = true
        settingsSection.click()
        queueMicrotask(() => { bypassInterceptionRef.current = false })
      })
    }
    document.addEventListener('click', interceptNavigation, true)
    return () => document.removeEventListener('click', interceptNavigation, true)
  }, [hasUnappliedChanges, location.hash, location.pathname, location.search, navigate, requestNavigation])

  useEffect(() => {
    if (!pending) return
    keepEditingRef.current?.focus()
    const handleDialogKeys = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        const trigger = pending.trigger
        setPending(null)
        setContinuing(null)
        window.requestAnimationFrame(() => trigger?.focus())
        return
      }
      if (event.key !== 'Tab') return
      const controls = [keepEditingRef.current, discardRef.current, applyRef.current]
        .filter((control): control is HTMLButtonElement => Boolean(control && !control.disabled))
      if (controls.length === 0) return
      const first = controls[0]
      const last = controls[controls.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleDialogKeys)
    return () => document.removeEventListener('keydown', handleDialogKeys)
  }, [pending])

  const keepEditing = () => {
    const trigger = pending?.trigger
    setPending(null)
    setContinuing(null)
    window.requestAnimationFrame(() => trigger?.focus())
  }

  const discardAndContinue = () => {
    if (!pending) return
    const next = pending.run
    setContinuing('discard')
    cancelPreview()
    setPending(null)
    setContinuing(null)
    next()
  }

  const applyAndContinue = async () => {
    if (!pending) return
    setContinuing('apply')
    const saved = await applyAppearance()
    if (!saved) {
      setContinuing(null)
      return
    }
    const next = pending.run
    setPending(null)
    setContinuing(null)
    next()
  }

  const dialog = pending ? (
        <div className="db-confirm db-appearance-leave" role="presentation">
          <section
            className="db-confirm__panel db-appearance-leave__panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="appearance-leave-title"
            aria-describedby="appearance-leave-description"
          >
            <h2 id="appearance-leave-title">Apply appearance changes?</h2>
            <p id="appearance-leave-description">
              You changed the following workspace settings. Apply them before leaving, or discard the preview.
            </p>
            <ul className="db-appearance-leave__changes" aria-label="Unsaved appearance changes">
              {changes.map(change => (
                <li key={change.label}>
                  <strong>{change.label}</strong>
                  <span><span>{change.before}</span><span aria-hidden="true">→</span><b>{change.after}</b></span>
                </li>
              ))}
            </ul>
            <div className="db-appearance-leave__actions">
              <button ref={keepEditingRef} type="button" className="db-button db-button--quiet" onClick={keepEditing}>
                Keep editing
              </button>
              <button ref={discardRef} type="button" className="db-button db-button--secondary" disabled={continuing !== null} onClick={discardAndContinue}>
                Discard &amp; continue
              </button>
              <button ref={applyRef} type="button" className="db-button db-button--primary" disabled={continuing !== null || saveStatus === 'conflict'} onClick={() => void applyAndContinue()}>
                {continuing === 'apply' ? 'Applying…' : 'Apply & continue'}
              </button>
            </div>
          </section>
        </div>
      ) : null
  const themedDialogHost = typeof document === 'undefined'
    ? null
    : document.querySelector<HTMLElement>('.db-staff-shell')

  return (
    <>
      {children}
      {dialog && themedDialogHost ? createPortal(dialog, themedDialogHost) : dialog}
    </>
  )
}
