import { ControlButton } from './ui/Controls'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { clearAnalyticsCookies, privacySignal, savePrivacyChoice } from '../lib/privacyPreferences'
import './PrivacyControls.css'

const OPEN_SETTINGS = 'dieselbridge:open-cookie-settings'

/** Inline entry point for public footers and account settings. */
export function CookieSettingsButton() {
  return <ControlButton type="button" className="cookie-settings-link" aria-haspopup="dialog" onClick={event => {
    window.dispatchEvent(new CustomEvent(OPEN_SETTINGS, { detail: event.currentTarget }))
  }}>Cookie settings</ControlButton>
}

export function CookiePrivacySettings() {
  return <section className="cookie-privacy-settings">
    <h3>Cookies and privacy</h3>
    <p>Optional analytics and advertising trackers are off. Review the necessary storage used by this browser.</p>
    <CookieSettingsButton />
  </section>
}

export default function PrivacyControls() {
  const [expanded, setExpanded] = useState(false)
  const [error, setError] = useState('')
  const trigger = useRef<HTMLElement | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const location = useLocation()
  useEffect(() => {
    clearAnalyticsCookies()
    const open = (event: Event) => {
      trigger.current = (event as CustomEvent<HTMLElement>).detail
      setError('')
      setExpanded(true)
    }
    window.addEventListener(OPEN_SETTINGS, open)
    return () => window.removeEventListener(OPEN_SETTINGS, open)
  }, [])
  useEffect(() => { setExpanded(false) }, [location.pathname])
  useEffect(() => { if (expanded) heading.current?.focus() }, [expanded])
  const close = () => {
    setExpanded(false)
    if (trigger.current?.isConnected) trigger.current.focus()
  }
  const choose = () => {
    if (!savePrivacyChoice('rejected')) {
      setError('Your browser could not save this preference. Optional analytics remains off.')
      return
    }
    setError('')
    close()
  }
  if (!expanded || location.pathname === '/fleet/motive/callback') return null
  return <aside className="privacy-controls" aria-label="Cookie preferences">
    <section id="privacy-panel" className="privacy-panel" role="dialog" aria-modal="false" aria-labelledby="privacy-heading" onKeyDown={event => {
      if (event.key === 'Escape') { event.stopPropagation(); close() }
    }}>
      <h2 id="privacy-heading" ref={heading} tabIndex={-1}>Your privacy choices</h2>
      <p>Optional analytics is off. We use necessary storage for sign-in, security, and your preferences. We do not load Google Analytics or advertising trackers. Payment and map providers load when you use their features.</p>
      <p><Link to="/cookies">Cookie policy</Link> · <Link to="/privacy">Privacy policy</Link></p>
      {privacySignal() && <p>Your browser privacy signal is on. Optional analytics is disabled.</p>}
      {error && <p role="status">{error}</p>}
      <div className="privacy-actions">
        <ControlButton type="button" onClick={choose}>Keep optional cookies off</ControlButton>
        <ControlButton type="button" onClick={close}>Close settings</ControlButton>
      </div>
    </section>
  </aside>
}
