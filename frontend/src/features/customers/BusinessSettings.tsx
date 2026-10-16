import { useId, useRef, useState, type ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'

export default function BusinessSettings({ children }: { children: ReactNode }) {
  const [expanded, setExpanded] = useState(false)
  const [visited, setVisited] = useState(false)
  const settingsId = useId(); const trigger = useRef<HTMLButtonElement>(null)
  return <div className="db-customer-business-settings">
    <button ref={trigger} type="button" aria-expanded={expanded} aria-controls={settingsId} onClick={() => { setExpanded(value => !value); setVisited(true) }}>
      <ChevronDown aria-hidden="true" className={expanded ? 'rotate-180' : ''} />Business settings
    </button>
    <section id={settingsId} aria-label="Business settings" hidden={!expanded} onKeyDown={event => {
      // React events from a portaled dialog still bubble through this disclosure.
      if (event.key === 'Escape' && event.currentTarget.contains(event.target as Node)) { event.stopPropagation(); setExpanded(false); trigger.current?.focus() }
    }}>{visited && children}</section>
  </div>
}
