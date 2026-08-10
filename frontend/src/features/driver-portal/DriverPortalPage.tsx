import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Check, ClipboardCheck, LogOut, ShieldCheck, Truck } from 'lucide-react'
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
  const [reportingFor, setReportingFor] = useState<Equipment | null>(null)
  const [incident, setIncident] = useState({ incident_type: 'other', severity: 'medium', location: '', description: '' })

  const load = async () => {
    setLoading(true)
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
    } catch {
      toast.error('Unable to load your assigned equipment')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const openInspectionByVehicle = useMemo(
    () => new Map(inspections.filter((item) => item.status === 'scheduled').map((item) => [item.vehicle_id, item])),
    [inspections],
  )

  const acknowledge = async (custodyId: string) => {
    await api.post(`/fleet-identity/me/custody/${custodyId}/acknowledge`)
    toast.success('Equipment handoff acknowledged')
    await load()
  }

  const startInspection = async (vehicleId: string) => {
    const response = await api.post('/fleet-identity/me/inspections', { vehicle_id: vehicleId })
    navigate(`/driver/inspections/${response.data.id}`)
  }

  const reportIncident = async () => {
    if (!reportingFor?.vehicle_id || !incident.description.trim()) return
    await api.post('/fleet-identity/me/incidents', {
      ...incident,
      vehicle_id: reportingFor.vehicle_id,
      occurred_at: new Date().toISOString(),
    })
    toast.success('Incident reported. Fleet management has been notified.')
    setReportingFor(null)
    setIncident({ incident_type: 'other', severity: 'medium', location: '', description: '' })
    await load()
  }

  if (loading) return <main className="driver-loading">Loading your assignment…</main>

  return (
    <main className="driver-home">
      <header className="driver-header">
        <div>
          <p className="driver-eyebrow">Driver workspace</p>
          <h1>{profile ? `${profile.first_name} ${profile.last_name}` : 'My equipment'}</h1>
          <p>Confirm custody, complete your pre-trip inspection, and report conditions as they happen.</p>
        </div>
        <button type="button" className="driver-icon-button" onClick={async () => {
          try { await api.post('/auth/workos/logout') } finally { clearSession(); window.location.assign('/driver/login') }
        }} aria-label="Sign out"><LogOut /></button>
      </header>

      {equipment.length === 0 ? (
        <section className="driver-empty"><Truck /><h2>No equipment assigned</h2><p>Your fleet manager must assign a truck before you can perform a PTI or report an incident.</p></section>
      ) : (
        <section className="driver-equipment-grid" aria-label="Assigned equipment">
          {equipment.map((item) => {
            const openInspection = item.vehicle_id ? openInspectionByVehicle.get(item.vehicle_id) : undefined
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
                {!item.custody_acknowledged_at && <button className="driver-primary" onClick={() => void acknowledge(item.custody_session_id)}>Confirm this equipment</button>}
                {item.vehicle_id && (
                  <div className="driver-actions">
                    <button className="driver-primary" onClick={() => openInspection ? navigate(`/driver/inspections/${openInspection.id}`) : void startInspection(item.vehicle_id!)}>
                      <ClipboardCheck /> {openInspection ? 'Continue PTI' : 'Start PTI'}
                    </button>
                    <button className="driver-secondary driver-danger" onClick={() => setReportingFor(item)}><AlertTriangle /> Report incident</button>
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
          <div className="driver-history-row" key={item.id}><span className={`driver-severity is-${item.severity}`} /> <div><strong>{item.description}</strong><p>{new Date(item.occurred_at).toLocaleString()}</p></div><span>{item.status.replace('_', ' ')}</span></div>
        ))}
      </section>

      {scorecard && (
        <section className="driver-scorecard" aria-labelledby="driver-score-title">
          <div><p className="driver-eyebrow">Reviewed accountability</p><h2 id="driver-score-title">Your operating record</h2><p>Only finalized findings count. Open or disputed reviews never count against your record.</p></div>
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

      {reportingFor && (
        <div className="driver-sheet-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setReportingFor(null) }}>
          <section className="driver-sheet" role="dialog" aria-modal="true" aria-labelledby="incident-title">
            <p className="driver-eyebrow">Unit {reportingFor.unit_number || 'not set'}</p>
            <h2 id="incident-title">Report an incident</h2>
            <p>Describe what happened and the equipment’s current condition. Reporting an incident does not assign fault.</p>
            <label>Type<select value={incident.incident_type} onChange={(event) => setIncident({ ...incident, incident_type: event.target.value })}><option value="mechanical">Mechanical</option><option value="collision">Collision</option><option value="cargo">Cargo or securement</option><option value="roadside">Roadside</option><option value="other">Other</option></select></label>
            <label>Severity<select value={incident.severity} onChange={(event) => setIncident({ ...incident, severity: event.target.value })}><option value="low">Low — safe to continue</option><option value="medium">Medium — needs review</option><option value="high">High — stop and contact fleet</option><option value="critical">Critical — emergency</option></select></label>
            <label>Location<input value={incident.location} onChange={(event) => setIncident({ ...incident, location: event.target.value })} placeholder="Road, city, or yard location" /></label>
            <label>What happened?<textarea value={incident.description} onChange={(event) => setIncident({ ...incident, description: event.target.value })} rows={5} autoFocus /></label>
            <div className="driver-sheet-actions"><button className="driver-secondary" onClick={() => setReportingFor(null)}>Cancel</button><button className="driver-primary driver-danger-solid" disabled={!incident.description.trim()} onClick={() => void reportIncident()}>Send incident report</button></div>
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
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    const response = await api.get(`/fleet-identity/me/inspections/${inspectionId}`)
    setInspection(response.data)
    setOdometer(String(response.data.odometer || ''))
  }, [inspectionId])
  useEffect(() => { void load() }, [load])

  const categories = useMemo(() => {
    const grouped = new Map<string, InspectionItem[]>()
    for (const item of inspection?.items || []) grouped.set(item.category, [...(grouped.get(item.category) || []), item])
    return [...grouped.entries()]
  }, [inspection])

  const update = async (item: InspectionItem, result: InspectionItem['result']) => {
    const response = await api.patch(`/fleet-identity/me/inspections/${inspectionId}/items/${item.id}`, { result })
    setInspection(response.data)
  }

  const complete = async () => {
    setSaving(true)
    try {
      await api.post(`/fleet-identity/me/inspections/${inspectionId}/complete`, { odometer: Number(odometer) })
      toast.success('PTI submitted')
      navigate('/driver')
    } catch (error: unknown) {
      toast.error((error as ApiError)?.response?.data?.detail || 'Unable to submit PTI')
    } finally { setSaving(false) }
  }

  if (!inspection) return <main className="driver-loading">Opening PTI…</main>
  const items = inspection.items || []
  const completed = items.filter((item) => item.result !== 'pending').length
  return (
    <main className="driver-inspection">
      <header className="driver-inspection-header"><button className="driver-secondary" onClick={() => navigate('/driver')}>Back</button><div><p className="driver-eyebrow">Pre-trip inspection</p><h1>Unit {inspection.vehicle_unit_number || 'not set'}</h1></div><strong>{completed}/{items.length}</strong></header>
      <div className="driver-progress"><span style={{ width: `${items.length ? completed / items.length * 100 : 0}%` }} /></div>
      <label className="driver-odometer">Current odometer<input inputMode="numeric" maxLength={7} value={odometer} onChange={(event) => setOdometer(event.target.value.replace(/\D/g, ''))} /></label>
      <div className="driver-checklist">
        {categories.map(([category, categoryItems]) => <section key={category}><h2>{category}</h2>{categoryItems.map((item) => <div className="driver-check" key={item.id}><strong>{item.label}</strong><div role="group" aria-label={`${item.label} result`}><button aria-pressed={item.result === 'pass'} className={item.result === 'pass' ? 'is-pass' : ''} onClick={() => void update(item, 'pass')}><Check /> Pass</button><button aria-pressed={item.result === 'fail'} className={item.result === 'fail' ? 'is-fail' : ''} onClick={() => void update(item, 'fail')}>Fail</button><button aria-pressed={item.result === 'na'} className={item.result === 'na' ? 'is-na' : ''} onClick={() => void update(item, 'na')}>N/A</button></div></div>)}</section>)}
      </div>
      <footer className="driver-submit"><span>{items.length - completed} checks remaining</span><button className="driver-primary" disabled={completed !== items.length || !odometer || saving} onClick={() => void complete()}>{saving ? 'Submitting…' : 'Confirm and submit PTI'}</button></footer>
    </main>
  )
}

export default function DriverPortalPage() {
  return <Routes><Route index element={<DriverHome />} /><Route path="inspections/:inspectionId" element={<DriverInspection />} /><Route path="*" element={<Navigate to="/driver" replace />} /></Routes>
}
