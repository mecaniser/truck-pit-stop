import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, Check, ClipboardCheck, LogOut, Minus, ShieldCheck, Truck, X } from 'lucide-react'
import { Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'
import './driver-portal.css'

type DriverProfile = { id: string; first_name: string; last_name: string; employee_number?: string | null }
type Equipment = {
  asset_id: string
  custody_session_id: string
  custody_status: string
  custody_acknowledged_at?: string | null
  equipment_role: 'power_unit' | 'trailer'
  vehicle_id?: string | null
  trailer_id?: string | null
  unit_number?: string | null
  vin?: string | null
  make?: string | null
  model?: string | null
  year?: number | null
  license_plate?: string | null
  odometer?: number | null
}
type InspectionItem = { id: string; category: string; label: string; result: 'pending' | 'pass' | 'fail' | 'na'; note?: string | null }
type Inspection = {
  id: string
  vehicle_id: string
  status: string
  result?: string | null
  vehicle_unit_number?: string | null
  vehicle_make: string
  vehicle_model: string
  odometer?: number | null
  items?: InspectionItem[]
}
type Incident = { id: string; occurred_at: string; description: string; severity: string; status: string; vehicle_unit_number?: string | null }
type Scorecard = { custody_miles: number; incidents_during_custody: number; finalized_reviews: number; confirmed_driver_duty_issues: number; not_attributable_findings: number; disputed_or_pending_reviews: number; reviewed_duty_issue_rate_per_10k_miles?: number | null; scoring_ready: boolean }
type ApiError = { response?: { data?: { detail?: string } } }

function apiErrorMessage(error: unknown, fallback: string) {
  const detail = (error as ApiError)?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (typeof navigator !== 'undefined' && !navigator.onLine) return 'You appear to be offline. Reconnect and try again.'
  return fallback
}

function equipmentTitle(item: Equipment) {
  return [item.year, item.make, item.model].filter(Boolean).join(' ') || (item.equipment_role === 'trailer' ? 'Trailer' : 'Truck')
}

function DriverHome() {
  const navigate = useNavigate()
  const clearSession = useAuthStore((state) => state.clearSession)
  const [profile, setProfile] = useState<DriverProfile | null>(null)
  const [equipment, setEquipment] = useState<Equipment[]>([])
  const [inspections, setInspections] = useState<Inspection[]>([])
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [scorecard, setScorecard] = useState<Scorecard | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [operationError, setOperationError] = useState<string | null>(null)
  const [acknowledgingId, setAcknowledgingId] = useState<string | null>(null)
  const [startingVehicleId, setStartingVehicleId] = useState<string | null>(null)
  const [reportingFor, setReportingFor] = useState<Equipment | null>(null)
  const [reporting, setReporting] = useState(false)
  const [incidentError, setIncidentError] = useState<string | null>(null)
  const [incident, setIncident] = useState({ incident_type: 'other', severity: 'medium', location: '', description: '' })
  const reportOpenerRef = useRef<HTMLElement | null>(null)
  const sheetRef = useRef<HTMLElement | null>(null)
  const incidentDescriptionRef = useRef<HTMLTextAreaElement | null>(null)
  const reportingRef = useRef(reporting)
  reportingRef.current = reporting

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const [profileResponse, equipmentResponse, inspectionResponse, incidentResponse, scorecardResponse] = await Promise.all([
        api.get('/fleet-identity/me'),
        api.get('/fleet-identity/me/equipment'),
        api.get('/fleet-identity/me/inspections'),
        api.get('/fleet-identity/me/incidents'),
        api.get('/fleet-identity/me/scorecard'),
      ])
      setProfile(profileResponse.data)
      setEquipment(equipmentResponse.data)
      setInspections(inspectionResponse.data)
      setIncidents(incidentResponse.data)
      setScorecard(scorecardResponse.data)
    } catch (error: unknown) {
      setLoadError(apiErrorMessage(error, 'We could not load your Driver Workspace.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  useEffect(() => {
    if (!reportingFor) return
    const opener = reportOpenerRef.current
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const frame = window.requestAnimationFrame(() => incidentDescriptionRef.current?.focus())
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !reportingRef.current) {
        event.preventDefault()
        setReportingFor(null)
        return
      }
      if (event.key !== 'Tab') return
      const focusable = Array.from(sheetRef.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
      ) || [])
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && (document.activeElement === first || !sheetRef.current?.contains(document.activeElement))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      window.cancelAnimationFrame(frame)
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      if (opener?.isConnected) opener.focus()
    }
  }, [reportingFor])

  const openInspectionByVehicle = useMemo(
    () => new Map(inspections.filter((item) => item.status === 'scheduled').map((item) => [item.vehicle_id, item])),
    [inspections],
  )

  const acknowledge = async (custodyId: string) => {
    setAcknowledgingId(custodyId)
    setOperationError(null)
    try {
      const response = await api.post(`/fleet-identity/me/custody/${custodyId}/acknowledge`)
      setEquipment((current) => current.map((item) => item.custody_session_id === custodyId
        ? { ...item, custody_acknowledged_at: response.data.acknowledged_at || new Date().toISOString(), custody_status: response.data.status || 'active' }
        : item))
      toast.success('Equipment handoff acknowledged')
    } catch (error: unknown) {
      setOperationError(apiErrorMessage(error, 'We could not confirm this equipment. Try again.'))
    } finally {
      setAcknowledgingId(null)
    }
  }

  const startInspection = async (vehicleId: string) => {
    setStartingVehicleId(vehicleId)
    setOperationError(null)
    try {
      const response = await api.post('/fleet-identity/me/inspections', { vehicle_id: vehicleId })
      navigate(`/driver/inspections/${response.data.id}`)
    } catch (error: unknown) {
      setOperationError(apiErrorMessage(error, 'We could not start the PTI. Try again.'))
      setStartingVehicleId(null)
    }
  }

  const reportIncident = async () => {
    if (!reportingFor?.vehicle_id || !incident.description.trim()) return
    setReporting(true)
    setIncidentError(null)
    try {
      const response = await api.post('/fleet-identity/me/incidents', {
        ...incident,
        location: incident.location.trim(),
        description: incident.description.trim(),
        vehicle_id: reportingFor.vehicle_id,
        occurred_at: new Date().toISOString(),
      })
      setIncidents((current) => [response.data, ...current])
      toast.success('Incident reported. Fleet management has been notified.')
      setReportingFor(null)
      setIncident({ incident_type: 'other', severity: 'medium', location: '', description: '' })
    } catch (error: unknown) {
      setIncidentError(apiErrorMessage(error, 'We could not send this report. Your information is still here—try again.'))
    } finally {
      setReporting(false)
    }
  }

  if (loading) return <main className="driver-loading" aria-live="polite">Loading your assignment…</main>
  if (loadError) return <main className="driver-loading"><section className="driver-load-error" role="alert"><AlertTriangle /><h1>Driver Workspace unavailable</h1><p>{loadError}</p><button type="button" className="driver-primary" onClick={() => void load()}>Try again</button></section></main>

  return (
    <main className="driver-home">
      <header className="driver-header">
        <div>
          <h1>{profile ? `${profile.first_name} ${profile.last_name}` : 'My equipment'}</h1>
          <p>Confirm custody, complete your pre-trip inspection, and report conditions as they happen.</p>
        </div>
        <button type="button" className="driver-icon-button" onClick={async () => {
          try { await api.post('/auth/workos/logout') } finally { clearSession(); window.location.assign('/driver/login') }
        }} aria-label="Sign out"><LogOut /></button>
      </header>

      {operationError && <div className="driver-inline-error" role="alert"><AlertTriangle /> <span>{operationError}</span></div>}

      {equipment.length === 0 ? (
        <section className="driver-empty"><Truck /><h2>No equipment assigned</h2><p>Your fleet manager must assign a truck before you can perform a PTI or report an incident.</p></section>
      ) : (
        <section className="driver-equipment-grid" aria-label="Assigned equipment">
          {equipment.map((item) => {
            const openInspection = item.vehicle_id ? openInspectionByVehicle.get(item.vehicle_id) : undefined
            const custodyConfirmed = Boolean(item.custody_acknowledged_at)
            return (
              <article className="driver-equipment-card" key={item.asset_id}>
                <div className="driver-equipment-heading">
                  <span className="driver-equipment-icon">{item.equipment_role === 'power_unit' ? <Truck /> : <ShieldCheck />}</span>
                  <div><p>{item.equipment_role === 'power_unit' ? 'Power unit' : 'Trailer'}</p><h2>Unit {item.unit_number || 'not set'}</h2></div>
                  <span className={`driver-custody ${item.custody_acknowledged_at ? 'is-active' : ''}`}>{item.custody_acknowledged_at ? 'In my custody' : 'Needs confirmation'}</span>
                </div>
                <div className="driver-equipment-facts">
                  <strong>{equipmentTitle(item)}</strong>
                  <span>{item.vin ? `VIN ${item.vin}` : 'VIN not recorded'}</span>
                  <span>{item.odometer != null ? `${item.odometer.toLocaleString()} mi` : item.license_plate || 'No odometer recorded'}</span>
                </div>
                {!custodyConfirmed && (
                  <div className="driver-confirmation">
                    <div>
                      <strong>Confirm before operating</strong>
                      <p>This records when the equipment entered your custody. It does not assign fault for existing conditions.</p>
                    </div>
                    <button type="button" className="driver-primary" disabled={acknowledgingId === item.custody_session_id} onClick={() => void acknowledge(item.custody_session_id)}>{acknowledgingId === item.custody_session_id ? 'Confirming…' : 'Confirm this equipment'}</button>
                  </div>
                )}
                {custodyConfirmed && item.vehicle_id && (
                  <div className="driver-actions">
                    <button type="button" className="driver-primary" disabled={startingVehicleId === item.vehicle_id} onClick={() => openInspection ? navigate(`/driver/inspections/${openInspection.id}`) : void startInspection(item.vehicle_id!)}>
                      <ClipboardCheck /> {startingVehicleId === item.vehicle_id ? 'Opening PTI…' : openInspection ? 'Continue PTI' : 'Start PTI'}
                    </button>
                    <button type="button" className="driver-secondary driver-danger" onClick={(event) => { reportOpenerRef.current = event.currentTarget; setIncidentError(null); setReportingFor(item) }}><AlertTriangle /> Report incident</button>
                  </div>
                )}
              </article>
            )
          })}
        </section>
      )}

      <section className="driver-history">
        <h2>Recent reports</h2>
        {incidents.length === 0 ? <p>No incidents reported during your custody.</p> : incidents.slice(0, 5).map((item) => (
          <div className="driver-history-row" key={item.id}><span className={`driver-severity is-${item.severity}`} /> <div><strong>{item.description}</strong><p>{new Date(item.occurred_at).toLocaleString()}</p></div><span className="driver-history-status">{item.status.replace(/_/g, ' ')}</span></div>
        ))}
      </section>

      {scorecard && (scorecard.scoring_ready || scorecard.custody_miles > 0 || scorecard.incidents_during_custody > 0 || scorecard.finalized_reviews > 0 || scorecard.disputed_or_pending_reviews > 0) && (
        <section className="driver-scorecard" aria-labelledby="driver-score-title">
          <div><h2 id="driver-score-title">Your operating record</h2><p>Only finalized findings count. Open or disputed reviews never count against your record.</p></div>
          <dl>
            <div><dt>Custody miles</dt><dd>{scorecard.custody_miles.toLocaleString()}</dd></div>
            <div><dt>Incidents recorded</dt><dd>{scorecard.incidents_during_custody}</dd></div>
            <div><dt>Not attributable</dt><dd>{scorecard.not_attributable_findings}</dd></div>
            <div><dt>Confirmed duty issues</dt><dd>{scorecard.confirmed_driver_duty_issues}</dd></div>
            <div><dt>Pending or disputed</dt><dd>{scorecard.disputed_or_pending_reviews}</dd></div>
          </dl>
          {!scorecard.scoring_ready && <p className="driver-score-note">A rate will appear after at least 1,000 custody miles and one finalized review.</p>}
          {scorecard.scoring_ready && <p className="driver-score-note">Reviewed duty-issue rate: <strong>{scorecard.reviewed_duty_issue_rate_per_10k_miles} per 10,000 custody miles</strong></p>}
        </section>
      )}
      {scorecard && !scorecard.scoring_ready && scorecard.custody_miles === 0 && scorecard.incidents_during_custody === 0 && scorecard.finalized_reviews === 0 && scorecard.disputed_or_pending_reviews === 0 && (
        <section className="driver-score-empty" aria-labelledby="driver-score-empty-title">
          <ShieldCheck aria-hidden="true" />
          <div>
            <h2 id="driver-score-empty-title">Your operating record starts here</h2>
            <p>Completed custody and finalized reviews will appear here. Open or disputed reviews never count against your record.</p>
          </div>
        </section>
      )}

      {reportingFor && (
        <div className="driver-sheet-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !reporting) setReportingFor(null) }}>
          <section ref={sheetRef} className="driver-sheet" role="dialog" aria-modal="true" aria-labelledby="incident-title" aria-describedby="incident-description" aria-busy={reporting || undefined}>
            <div className="driver-sheet-header"><div><p className="driver-sheet-context">Unit {reportingFor.unit_number || 'not set'}</p><h2 id="incident-title">Report an incident</h2></div><button type="button" className="driver-icon-button" disabled={reporting} aria-label="Close incident report" onClick={() => setReportingFor(null)}><X /></button></div>
            <p id="incident-description">Describe what happened and the equipment’s current condition. Reporting an incident does not assign fault.</p>
            <form className="driver-sheet-form" onSubmit={(event) => { event.preventDefault(); void reportIncident() }}>
              <label>Type<select disabled={reporting} value={incident.incident_type} onChange={(event) => setIncident({ ...incident, incident_type: event.target.value })}><option value="mechanical">Mechanical</option><option value="collision">Collision</option><option value="cargo">Cargo or securement</option><option value="roadside">Roadside</option><option value="other">Other</option></select></label>
              <label>Severity<select disabled={reporting} value={incident.severity} onChange={(event) => setIncident({ ...incident, severity: event.target.value })}><option value="low">Low — safe to continue</option><option value="medium">Medium — needs review</option><option value="high">High — stop and contact fleet</option><option value="critical">Critical — emergency</option></select></label>
              <label>Location<input disabled={reporting} maxLength={255} value={incident.location} onChange={(event) => setIncident({ ...incident, location: event.target.value })} placeholder="Road, city, or yard location" /></label>
              <label>What happened?<textarea ref={incidentDescriptionRef} disabled={reporting} required maxLength={2000} value={incident.description} onChange={(event) => setIncident({ ...incident, description: event.target.value })} rows={5} /></label>
              {incidentError && <div className="driver-inline-error" role="alert"><AlertTriangle /> <span>{incidentError}</span></div>}
              <div className="driver-sheet-actions"><button type="button" className="driver-secondary" disabled={reporting} onClick={() => setReportingFor(null)}>Cancel</button><button type="submit" className="driver-primary driver-danger-solid" disabled={!incident.description.trim() || reporting}>{reporting ? 'Sending report…' : 'Send incident report'}</button></div>
            </form>
          </section>
        </div>
      )}
    </main>
  )
}

function DriverInspection() {
  const { inspectionId } = useParams()
  const navigate = useNavigate()
  const [inspection, setInspection] = useState<Inspection | null>(null)
  const [odometer, setOdometer] = useState('')
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [savingItemId, setSavingItemId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      const response = await api.get(`/fleet-identity/me/inspections/${inspectionId}`)
      setInspection(response.data)
      setOdometer(String(response.data.odometer || ''))
      setNotes(Object.fromEntries((response.data.items || []).map((item: InspectionItem) => [item.id, item.note || ''])))
    } catch (error: unknown) {
      setLoadError(apiErrorMessage(error, 'We could not open this PTI.'))
    }
  }, [inspectionId])
  useEffect(() => { void load() }, [load])

  const categories = useMemo(() => {
    const grouped = new Map<string, InspectionItem[]>()
    for (const item of inspection?.items || []) grouped.set(item.category, [...(grouped.get(item.category) || []), item])
    return [...grouped.entries()]
  }, [inspection])

  const update = async (item: InspectionItem, result: InspectionItem['result']) => {
    if (savingItemId || saving) return
    setSavingItemId(item.id)
    try {
      const response = await api.patch(`/fleet-identity/me/inspections/${inspectionId}/items/${item.id}`, {
        result,
        note: result === 'fail' ? notes[item.id] || '' : '',
      })
      setInspection(response.data)
      if (result !== 'fail') setNotes((current) => ({ ...current, [item.id]: '' }))
    } catch (error: unknown) {
      toast.error(apiErrorMessage(error, `We could not save “${item.label}”. Try again.`))
    } finally {
      setSavingItemId(null)
    }
  }

  const saveFailureNote = async (item: InspectionItem) => {
    const nextNote = (notes[item.id] || '').trim()
    if (!nextNote || nextNote === (item.note || '').trim() || savingItemId || saving) return
    setSavingItemId(item.id)
    try {
      const response = await api.patch(`/fleet-identity/me/inspections/${inspectionId}/items/${item.id}`, { result: 'fail', note: nextNote })
      setInspection(response.data)
    } catch (error: unknown) {
      toast.error(apiErrorMessage(error, `We could not save the note for “${item.label}”.`))
    } finally {
      setSavingItemId(null)
    }
  }

  const complete = async () => {
    const failedWithoutNotes = (inspection?.items || []).filter((item) => item.result === 'fail' && !(notes[item.id] || '').trim())
    if (failedWithoutNotes.length) {
      toast.error('Describe each failed check before submitting')
      return
    }
    setSaving(true)
    try {
      const changedFailedItems = (inspection?.items || []).filter(
        (item) => item.result === 'fail' && (notes[item.id] || '').trim() !== (item.note || '').trim(),
      )
      await Promise.all(changedFailedItems.map((item) => api.patch(
        `/fleet-identity/me/inspections/${inspectionId}/items/${item.id}`,
        { result: 'fail', note: notes[item.id].trim() },
      )))
      await api.post(`/fleet-identity/me/inspections/${inspectionId}/complete`, { odometer: Number(odometer) })
      toast.success('PTI submitted')
      navigate('/driver')
    } catch (error: unknown) {
      toast.error((error as ApiError)?.response?.data?.detail || 'Unable to submit PTI')
    } finally { setSaving(false) }
  }

  if (loadError) return <main className="driver-loading"><section className="driver-load-error" role="alert"><AlertTriangle /><h1>PTI unavailable</h1><p>{loadError}</p><div><button type="button" className="driver-secondary" onClick={() => navigate('/driver')}>Back to workspace</button><button type="button" className="driver-primary" onClick={() => void load()}>Try again</button></div></section></main>
  if (!inspection) return <main className="driver-loading" aria-live="polite">Opening PTI…</main>
  const items = inspection.items || []
  const completed = items.filter((item) => item.result !== 'pending').length
  const failedWithoutNotes = items.filter((item) => item.result === 'fail' && !(notes[item.id] || '').trim()).length
  return (
    <main className="driver-inspection">
      <header className="driver-inspection-header"><button type="button" className="driver-secondary" onClick={() => navigate('/driver')}>Back</button><div><p className="driver-inspection-context">Pre-trip inspection</p><h1>Unit {inspection.vehicle_unit_number || 'not set'}</h1></div><strong>{completed}/{items.length}</strong></header>
      <div className="driver-progress" role="progressbar" aria-label="Inspection progress" aria-valuemin={0} aria-valuemax={items.length} aria-valuenow={completed}><span style={{ width: `${items.length ? completed / items.length * 100 : 0}%` }} /></div>
      <label className="driver-odometer">Current odometer<input inputMode="numeric" maxLength={7} value={odometer} onChange={(event) => setOdometer(event.target.value.replace(/\D/g, ''))} /></label>
      <div className="driver-checklist">
        {categories.map(([category, categoryItems]) => <section key={category}><h2>{category}</h2>{categoryItems.map((item) => <div className="driver-check" key={item.id} aria-busy={savingItemId === item.id || undefined}><strong>{item.label}</strong><div role="group" aria-label={`${item.label} result`}><button type="button" disabled={Boolean(savingItemId) || saving} aria-pressed={item.result === 'pass'} className={item.result === 'pass' ? 'is-pass' : ''} onClick={() => void update(item, 'pass')}><Check /> Pass</button><button type="button" disabled={Boolean(savingItemId) || saving} aria-pressed={item.result === 'fail'} className={item.result === 'fail' ? 'is-fail' : ''} onClick={() => void update(item, 'fail')}><X /> Fail</button><button type="button" disabled={Boolean(savingItemId) || saving} aria-pressed={item.result === 'na'} className={item.result === 'na' ? 'is-na' : ''} onClick={() => void update(item, 'na')}><Minus /> N/A</button></div>{item.result === 'fail' && <label className="driver-failure-note">What is wrong?<textarea required disabled={savingItemId === item.id || saving} maxLength={1000} rows={2} value={notes[item.id] || ''} onChange={(event) => setNotes((current) => ({ ...current, [item.id]: event.target.value }))} onBlur={() => void saveFailureNote(item)} placeholder="Describe the condition for fleet management" /></label>}</div>)}</section>)}
      </div>
      <footer className="driver-submit" aria-live="polite"><span>{savingItemId ? 'Saving check…' : failedWithoutNotes ? `${failedWithoutNotes} failed ${failedWithoutNotes === 1 ? 'check needs' : 'checks need'} a note` : `${items.length - completed} checks remaining`}</span><button type="button" className="driver-primary" disabled={completed !== items.length || !odometer || failedWithoutNotes > 0 || Boolean(savingItemId) || saving} onClick={() => void complete()}>{saving ? 'Submitting…' : 'Confirm and submit PTI'}</button></footer>
    </main>
  )
}

export default function DriverPortalPage() {
  return <Routes><Route index element={<DriverHome />} /><Route path="inspections/:inspectionId" element={<DriverInspection />} /><Route path="*" element={<Navigate to="/driver" replace />} /></Routes>
}
