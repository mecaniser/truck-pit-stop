import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Download } from 'lucide-react'
import DatePicker from '@/components/DatePicker'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import type { Vehicle } from '@/types'
import './vehicle-history-export.css'

type Props = { vehicle: Vehicle; children?: ReactNode }
type Auth = ReturnType<typeof useAuthStore.getState>
const identity = (state: Pick<Auth, 'user' | 'authSessionEpoch' | 'isAuthenticated' | 'logoutInProgress'>) =>
  JSON.stringify([state.user?.id, state.user?.tenant_id, state.user?.role, state.authSessionEpoch, state.isAuthenticated, state.logoutInProgress])
const allowed = (user: Auth['user']) => Boolean(user?.tenant_id && ['garage_owner', 'garage_admin', 'receptionist'].includes(user.role))

export default function VehicleHistoryExport({ vehicle, children }: Props) {
  const user = useAuthStore(state => state.user)
  const epoch = useAuthStore(state => state.authSessionEpoch)
  const authenticated = useAuthStore(state => state.isAuthenticated)
  const loggingOut = useAuthStore(state => state.logoutInProgress)
  const scope = identity({ user, authSessionEpoch: epoch, isAuthenticated: authenticated, logoutInProgress: loggingOut })
  if (!allowed(user) || !authenticated || loggingOut) return children ? <div className="db-customer-record__work-actions">{children}</div> : null
  return <ExportControls key={`${scope}:${vehicle.id}`} vehicle={vehicle} scope={scope}>{children}</ExportControls>
}

async function failureMessage(error: unknown): Promise<string> {
  const response = (error as { response?: { status?: number; data?: unknown } })?.response
  let data = response?.data
  if (data instanceof Blob && data.size < 16_384) {
    try { data = JSON.parse(await data.text()) } catch { data = null }
  }
  const code = (data as { detail?: { code?: string } } | null)?.detail?.code
  if (code === 'history_empty') return 'No completed shop work or active outside-shop history matches these dates. Try a different range or leave both dates blank.'
  if (code === 'history_export_too_large') return 'This export is too large. Choose a narrower date range and try again.'
  if (code === 'vehicle_not_found') return 'This vehicle is no longer available. Return to the customer and reopen its current vehicle record.'
  if (response?.status === 401 || response?.status === 403) return 'Your access to this export has changed. Sign in with an authorized shop account and try again.'
  if (response?.status === 422) return 'Check the history dates and try again.'
  return 'Could not download service history. Your dates are kept; try again.'
}

function ExportControls({ vehicle, scope, children }: Props & { scope: string }) {
  const [open, setOpen] = useState(false)
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const trigger = useRef<HTMLButtonElement>(null)
  const container = useRef<HTMLDivElement>(null)
  const request = useRef<AbortController | null>(null)
  const formId = useId()
  useEffect(() => () => { request.current?.abort() }, [])
  const close = useCallback(() => {
    request.current?.abort(); request.current = null
    setPending(false); setOpen(false); setError(''); setSuccess('')
    trigger.current?.focus()
  }, [])
  useEffect(() => {
    if (!open) return
    container.current?.querySelector('input')?.focus()
    const escape = (event: KeyboardEvent) => {
      const calendar = container.current?.querySelector('[role="dialog"]')
      if (calendar?.closest('.db-datepicker')?.contains(document.activeElement)) return
      // A disabled pending button may surrender focus to the document. Do not
      // dismiss a different dialog opened over this workspace.
      if (event.key === 'Escape' && (document.activeElement === document.body || container.current?.contains(document.activeElement))) {
        event.preventDefault(); event.stopPropagation(); close()
      }
    }
    document.addEventListener('keydown', escape, true)
    return () => document.removeEventListener('keydown', escape, true)
  }, [open, close])
  const download = async () => {
    if (request.current) return
    setError(''); setSuccess('')
    if ([from, to].some(value => value && (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value < '1900-01-01'
      || Number.isNaN(Date.parse(`${value}T12:00:00Z`)) || new Date(`${value}T12:00:00Z`).toISOString().slice(0, 10) !== value))) {
      setError('Enter valid history dates as YYYY-MM-DD, on or after 1900-01-01.'); return
    }
    if (from && to && from > to) { setError('History from must be on or before History to.'); return }
    const controller = new AbortController()
    request.current = controller
    const current = () => !controller.signal.aborted && request.current === controller && identity(useAuthStore.getState()) === scope
    setPending(true)
    try {
      const response = await api.get<Blob>(`/vehicles/${vehicle.id}/service-history.csv`, {
        params: { ...(from ? { date_from: from } : {}), ...(to ? { date_to: to } : {}) },
        responseType: 'blob', signal: controller.signal,
      })
      if (!current()) return
      const count = Number(response.headers['x-export-row-count'])
      if (!(response.data instanceof Blob) || !/^text\/csv(?:;|$)/i.test(String(response.headers['content-type']))
        || response.headers['x-export-vehicle-id'] !== vehicle.id || !Number.isInteger(count) || count < 1 || count > 1000
        || response.data.size === 0 || response.data.size > 2 * 1024 * 1024) throw new Error('Invalid history export')
      const url = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url; link.download = `vehicle-service-history-${vehicle.id}.csv`
      document.body.appendChild(link)
      try { link.click() } finally {
        link.remove()
        // Allow the browser to consume the download before freeing its URL.
        window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      }
      setSuccess(`Downloaded ${count} service ${count === 1 ? 'record' : 'records'}.`)
    } catch (failure) {
      const message = await failureMessage(failure)
      if (current()) setError(message)
    } finally {
      if (current()) { request.current = null; setPending(false) }
    }
  }
  return <div ref={container} className="db-vehicle-export">
    <div className="db-customer-record__work-actions">
      <button ref={trigger} type="button" aria-expanded={open} aria-controls={formId} onClick={() => open ? close() : setOpen(true)}><Download aria-hidden="true" />Export history</button>
      {children}
    </div>
    {open && <form id={formId} aria-label="Export vehicle service history" onSubmit={event => { event.preventDefault(); void download() }} onKeyDown={event => { if (event.key === 'Escape' && event.defaultPrevented) event.stopPropagation() }}>
      <h3>Export service history</h3>
      <p>Completed shop work and active outside-shop records for <strong>{vehicle.unit_number || [vehicle.year, vehicle.make, vehicle.model].filter(Boolean).join(' ') || 'this vehicle'}</strong>, across all pages.</p>
      <div className="db-vehicle-export__dates">
        <DatePicker key={`from-${pending}`} label="History from" value={from} min="1900-01-01" max="9999-12-31" disabled={pending} showDayDetails={false} surface="light" onChange={value => { setFrom(value); setError(''); setSuccess('') }} />
        <DatePicker key={`to-${pending}`} label="History to" value={to} min="1900-01-01" max="9999-12-31" disabled={pending} showDayDetails={false} surface="light" onChange={value => { setTo(value); setError(''); setSuccess('') }} />
      </div>
      {(from || to) && <button className="db-vehicle-export__clear" type="button" disabled={pending} onClick={() => { setFrom(''); setTo(''); setError(''); setSuccess('') }}>Clear dates</button>}
      <p className="db-vehicle-export__hint">Leave dates blank for all history. Unknown service dates use the record-created date and are labeled in the file. Internal notes and prices are excluded.</p>
      {error && <p role="alert">{error}</p>}
      {success && <p role="status">{success}</p>}
      <div className="db-vehicle-export__actions"><button type="button" onClick={close}>Cancel</button><button type="submit" disabled={pending}><Download aria-hidden="true" />{pending ? 'Preparing…' : error ? 'Retry download' : 'Download CSV'}</button></div>
    </form>}
  </div>
}
