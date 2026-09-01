import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
import { Bell, Check, LayoutGrid, Palette, RotateCcw, Save, Type, X } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  ACCENT_OPTIONS,
  DENSITY_OPTIONS,
  FONT_FAMILY_OPTIONS,
  MODE_OPTIONS,
  NOTIFICATION_POSITION_OPTIONS,
  useTheme,
} from '../../contexts/ThemeContext'
import { accentRampsFor } from '../../contexts/appearanceTokens'

const choice = (selected: boolean) => `db-appearance-choice ${selected ? 'is-selected' : ''}`

export default function AppearanceSettingsPanel() {
  const {
    accent,
    fontFamily,
    fontSize,
    notificationPosition,
    density,
    mode,
    hasUnappliedChanges,
    saveStatus,
    setAccent,
    setFontFamily,
    setFontSize,
    setNotificationPosition,
    setDensity,
    setMode,
    applyAppearance,
    cancelPreview,
    previewDefaults,
    resetToDefaults,
    presentationVariant,
    presentationSource,
    canSetPresentation,
    presentationStatus,
    setPresentationVariant,
  } = useTheme()
  const [confirmReset, setConfirmReset] = useState(false)
  const accentRamps = accentRampsFor(mode)
  const resetTriggerRef = useRef<HTMLButtonElement>(null)
  const keepCurrentRef = useRef<HTMLButtonElement>(null)
  const confirmResetRef = useRef<HTMLButtonElement>(null)
  const cancelPreviewRef = useRef(cancelPreview)

  useLayoutEffect(() => { cancelPreviewRef.current = cancelPreview }, [cancelPreview])

  useEffect(() => {
    if (!confirmReset) return
    keepCurrentRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        cancelPreviewRef.current()
        resetTriggerRef.current?.focus()
        setConfirmReset(false)
        return
      }
      if (event.key !== 'Tab') return
      if (event.shiftKey && document.activeElement === keepCurrentRef.current) {
        event.preventDefault()
        confirmResetRef.current?.focus()
      } else if (!event.shiftKey && document.activeElement === confirmResetRef.current) {
        event.preventDefault()
        keepCurrentRef.current?.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [confirmReset])

  const closeReset = () => {
    cancelPreview()
    resetTriggerRef.current?.focus()
    setConfirmReset(false)
  }

  const confirmResetAppearance = async () => {
    setConfirmReset(false)
    resetTriggerRef.current?.focus()
    await resetToDefaults()
  }

  const previewNotification = (position: typeof notificationPosition) => {
    setNotificationPosition(position)
    const label = NOTIFICATION_POSITION_OPTIONS.find(option => option.id === position)?.label ?? 'selected'
    toast.success(`Notification preview: ${label}`, {
      id: 'notification-position-preview',
      position: position === 'center-top' ? 'top-center' : position === 'top' ? 'top-right' : 'bottom-right',
    })
  }

  return (
    <section className="db-appearance" aria-labelledby="appearance-title">
      <header className="db-appearance__header">
        <div>
          <h1 id="appearance-title">Appearance</h1>
          <p>Adjust how your workspace reads. Operational status colors always remain consistent.</p>
        </div>
        <div className="db-appearance__status" role="status" aria-live="polite">
          {saveStatus === 'saving' ? 'Applying…' : saveStatus === 'saved' ? 'Applied across this account' : saveStatus === 'conflict' ? 'Changed in another session' : hasUnappliedChanges ? 'Previewing changes' : 'Up to date'}
        </div>
      </header>

      <div className="db-appearance-preview" aria-label="Live appearance preview">
        <div className="db-appearance-preview__nav"><span /><span /><span /></div>
        <div className="db-appearance-preview__body">
          <div>
            <strong>Shop Cockpit</strong>
            <span>Your selected type, spacing, surfaces, and accent appear here immediately.</span>
          </div>
          <span className="db-appearance-preview__action" aria-hidden="true">Primary action</span>
          <div className="db-appearance-preview__states">
            <span className="is-success">Ready to close</span>
            <span className="is-warning">Authorization pending</span>
            <span className="is-danger">Needs attention</span>
          </div>
        </div>
      </div>

      <div className="db-appearance-sections">
        {canSetPresentation && (
          <fieldset className="db-appearance-section">
            <legend><LayoutGrid aria-hidden="true" /> Workspace</legend>
            <p>Applies to everyone at this shop. Classic is the original layout; Modern is the rebuilt one, including the Parts &amp; inventory workspace.</p>
            <div className="db-appearance-segment" aria-label="Workspace layout">
              {([
                { id: 'legacy', label: 'Classic' },
                { id: 'new', label: 'Modern' },
              ] as const).map(option => (
                <button
                  key={option.id}
                  type="button"
                  aria-pressed={presentationVariant === option.id}
                  disabled={presentationStatus === 'saving'}
                  className={presentationVariant === option.id ? 'is-selected' : ''}
                  onClick={() => void setPresentationVariant(option.id)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            {presentationSource === 'global_force_legacy' && (
              <p role="note">Locked to Classic for every shop by a platform setting.</p>
            )}
            {presentationSource === 'user_override' && (
              <p role="note">Your account has a personal override, so it may not match the shop default.</p>
            )}
          </fieldset>
        )}

        <fieldset className="db-appearance-section">
          <legend><Palette aria-hidden="true" /> Accent</legend>
          <p>{mode === 'dark' ? 'Night shop palette: brighter signals tuned for the navy field.' : mode === 'light' ? 'Day shop palette: deeper action colors tuned for road-white surfaces.' : 'High contrast palette: opaque, high-separation accents for the selected surface.'}</p>
          <p>Sets selection, focus and secondary actions. The primary action on each screen keeps the Truck Pit Stop copper.</p>
          <div className="db-appearance-grid db-appearance-grid--accent">
            {ACCENT_OPTIONS.map(option => (
              <button key={option.id} type="button" aria-pressed={accent === option.id} className={choice(accent === option.id)} onClick={() => setAccent(option.id)}>
                <span className="db-appearance-swatch" style={{ backgroundColor: accentRamps[option.id][500], '--db-appearance-swatch-foreground': accentRamps[option.id].swatchForeground } as CSSProperties}>{accent === option.id && <Check aria-hidden="true" />}</span>
                <span>{option.label}</span>
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="db-appearance-section">
          <legend><Type aria-hidden="true" /> Type</legend>
          <p>Choose the reading character and base size. Editable controls remain touch-safe.</p>
          <div className="db-appearance-grid db-appearance-grid--type">
            {FONT_FAMILY_OPTIONS.map(option => (
              <button key={option.id} type="button" aria-pressed={fontFamily === option.id} className={choice(fontFamily === option.id)} style={{ fontFamily: option.stack }} onClick={() => setFontFamily(option.id)}>
                <strong>{option.label}</strong><span>Aa Bb Cc 123</span>
              </button>
            ))}
          </div>
          <div className="db-appearance-segment" aria-label="Font size">
            {['compact', 'default', 'large'].map(size => (
              <button key={size} type="button" aria-pressed={fontSize === size} className={fontSize === size ? 'is-selected' : ''} onClick={() => setFontSize(size as typeof fontSize)}>
                {size === 'compact' ? 'Small' : size === 'large' ? 'Large' : 'Default'}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="db-appearance-section">
          <legend>Workspace density</legend>
          <p>Density changes information rhythm, never browser zoom or minimum target size.</p>
          <div className="db-appearance-grid db-appearance-grid--density">
            {DENSITY_OPTIONS.map(option => (
              <button key={option.id} type="button" aria-pressed={density === option.id} className={choice(density === option.id)} onClick={() => setDensity(option.id)}>
                <strong>{option.label}</strong><span>{option.description}</span>
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="db-appearance-section">
          <legend>Surface mode</legend>
          <p>Choose a curated operating environment with verified contrast.</p>
          <div className="db-appearance-grid db-appearance-grid--mode">
            {MODE_OPTIONS.map(option => (
              <button key={option.id} type="button" aria-pressed={mode === option.id} className={choice(mode === option.id)} onClick={() => setMode(option.id)}>
                <span className={`db-mode-sample db-mode-sample--${option.id}`} aria-hidden="true"><i /><i /></span>
                <strong>{option.label}</strong><span>{option.description}</span>
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="db-appearance-section">
          <legend><Bell aria-hidden="true" /> Notification location</legend>
          <p>Preview placement without saving. Alerts avoid active modal and footer actions.</p>
          <div className="db-appearance-grid db-appearance-grid--notifications">
            {NOTIFICATION_POSITION_OPTIONS.map(option => (
              <button key={option.id} type="button" aria-pressed={notificationPosition === option.id} className={choice(notificationPosition === option.id)} onClick={() => previewNotification(option.id)}>
                <strong>{option.label}</strong><span>{option.description}</span>
              </button>
            ))}
          </div>
        </fieldset>
      </div>

      <footer className="db-appearance-actions">
        <div>
          <button type="button" className="db-button db-button--quiet" onClick={previewDefaults}><RotateCcw aria-hidden="true" /> Preview defaults</button>
          <button ref={resetTriggerRef} type="button" className="db-button db-button--quiet" onClick={() => { previewDefaults(); setConfirmReset(true) }}>Reset saved appearance</button>
        </div>
        <div>
          <button type="button" className="db-button db-button--quiet" disabled={!hasUnappliedChanges || saveStatus === 'saving'} onClick={cancelPreview}><X aria-hidden="true" /> Cancel</button>
          <button type="button" className="db-button db-button--primary" disabled={!hasUnappliedChanges || saveStatus === 'saving' || saveStatus === 'conflict'} onClick={() => void applyAppearance()}><Save aria-hidden="true" /> {saveStatus === 'saving' ? 'Applying…' : 'Apply appearance'}</button>
        </div>
      </footer>

      {confirmReset && (
        <div className="db-confirm" role="dialog" aria-modal="true" aria-labelledby="reset-appearance-title">
          <div className="db-confirm__panel">
            <h2 id="reset-appearance-title">Reset saved appearance?</h2>
            <p>This restores the defaults chosen for your shop. It does not change which product presentation your account receives.</p>
            <div>
              <button ref={keepCurrentRef} type="button" className="db-button db-button--quiet" onClick={closeReset}>Keep current</button>
              <button ref={confirmResetRef} type="button" className="db-button db-button--primary" onClick={() => void confirmResetAppearance()}>Reset appearance</button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
