import { useId, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown } from 'lucide-react'

import api from '../../lib/api'
import { Spinner } from '@/components/ui'
import { fmtDate } from './helpers'

/**
 * The append-only record of what happened to one road incident.
 *
 * The server has kept this trail — who reported it, attached work, voided or
 * resolved it — since incidents were introduced, at
 * GET /fleet/incidents/{id}/events. Nothing read it, so "what happened to this
 * incident?" had an answer in the database and none on screen.
 *
 * Fetched only when opened: a truck can carry many settled incidents, and most
 * readers want the outcome line, not the full trail.
 */

interface IncidentEvent {
  id: string
  event_type: string
  actor_name: string
  reason?: string | null
  data: Record<string, unknown>
  occurred_at: string
}

function describe(event: IncidentEvent): string {
  const order = typeof event.data.order_number === 'string' ? ` ${event.data.order_number}` : ''
  switch (event.event_type) {
    case 'reported': return 'Reported'
    case 'updated': return 'Details edited'
    case 'evidence_added': return 'Photo added'
    case 'evidence_voided': return 'Photo removed'
    case 'repair_order_created': return 'Repair order opened'
    case 'repair_order_linked': return `Assigned to repair order${order}`
    case 'repair_order_unlinked': return 'Unassigned from its repair order'
    case 'resolved_by_repair_order': return `Resolved by repair order${order}`
    case 'operationally_resolved': return 'Resolved'
    case 'operationally_reopened': return 'Reopened'
    case 'voided': return 'Voided'
    // The trail is append-only and may gain types this screen predates.
    default: return event.event_type.replace(/_/g, ' ')
  }
}

export default function IncidentHistory({ incidentId }: { incidentId: string }) {
  const [open, setOpen] = useState(false)
  const listId = useId()
  const events = useQuery<IncidentEvent[]>({
    queryKey: ['fleet-incident-events', incidentId],
    queryFn: async () => (await api.get(`/fleet/incidents/${incidentId}/events`)).data,
    enabled: open,
  })

  return (
    <div style={{ marginTop: 8 }}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={listId}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 4, padding: 0,
          border: 0, background: 'transparent', color: 'var(--muted)',
          fontSize: 12, cursor: 'pointer',
        }}
      >
        {open ? 'Hide history' : 'Show history'}
        <ChevronDown size={13} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .15s ease' }} />
      </button>
      {open && (
        events.isLoading ? (
          <div style={{ marginTop: 6, fontSize: 12, color: 'var(--muted)' }}><Spinner size="xs" /> Loading history…</div>
        ) : events.isError ? (
          <div style={{ marginTop: 6, fontSize: 12, color: 'var(--muted)' }}>This incident's history could not be loaded.</div>
        ) : (
          <ol
            id={listId}
            aria-label="Incident history"
            style={{ margin: '6px 0 0', padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 5 }}
          >
            {(events.data || []).map((event) => (
              <li key={event.id} style={{ display: 'flex', gap: 8, fontSize: 12, lineHeight: 1.45 }}>
                <span style={{ color: 'var(--muted)', whiteSpace: 'nowrap' }}>{fmtDate(event.occurred_at)}</span>
                <span style={{ color: 'var(--text)' }}>
                  {describe(event)}
                  <span style={{ color: 'var(--muted)' }}> · {event.actor_name}</span>
                  {event.reason && <span style={{ color: 'var(--muted)' }}> — {event.reason}</span>}
                </span>
              </li>
            ))}
          </ol>
        )
      )}
    </div>
  )
}
