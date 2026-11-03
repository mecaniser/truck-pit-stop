import { ControlButton } from './ui/Controls'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { clearAnalyticsCookies, privacySignal, savePrivacyChoice, usePrivacyChoice } from '../lib/privacyPreferences'
import './PrivacyControls.css'

export default function PrivacyControls() {
  const choice = usePrivacyChoice()
  const [expanded, setExpanded] = useState(false)
  const [error, setError] = useState('')
  const settings = useRef<HTMLButtonElement>(null)
  const location = useLocation()
  useEffect(() => { clearAnalyticsCookies() }, [])
  if (location.pathname === '/fleet/motive/callback') return null
  const open = choice === null || expanded
  const choose = (next: 'rejected') => {
    if (!savePrivacyChoice(next)) {
      setError('Your browser could not save this preference. Optional analytics remains off. Enable local storage to save your choice.')
      return
    }
    setError('')
    setExpanded(false)
    settings.current?.focus()
  }
  return <aside className="privacy-controls" aria-label="Cookie preferences">
    <ControlButton ref={settings} type="button" className="privacy-settings" aria-expanded={open} aria-controls="privacy-panel" onClick={() => setExpanded(true)}>Cookie settings</ControlButton>
    {open && <section id="privacy-panel" className="privacy-panel" aria-labelledby="privacy-heading">
      <h2 id="privacy-heading">Your privacy choices</h2>
      <p>Optional analytics is off. We use necessary storage for sign-in, security, and your preferences. We do not load Google Analytics or advertising trackers. Payment and map providers load when you use their features.</p>
      <p><Link to="/cookies">Cookie policy</Link> · <Link to="/privacy">Privacy policy</Link></p>
      {privacySignal() && <p>Your browser privacy signal is on. Optional analytics is disabled.</p>}
      {error && <p role="status">{error}</p>}
      <div className="privacy-actions">
        <ControlButton type="button" onClick={() => choose('rejected')}>Keep optional cookies off</ControlButton>
        {choice !== null && <ControlButton type="button" onClick={() => { setExpanded(false); settings.current?.focus() }}>Close settings</ControlButton>}
      </div>
    </section>}
  </aside>
}
