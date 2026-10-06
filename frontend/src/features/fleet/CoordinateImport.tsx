import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown } from 'lucide-react'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'
import type { BoardTruck } from './types'
import { checkFreshness, checkpointKey, exampleObservation, makeCheckpoint, locationFingerprint, matchTruck, observationSchema, persistCheckpoint, readCheckpoint, verifyActor, verifyProjection, verifyReceipt, type Actor, type Checkpoint } from './coordinateImportModel'
import './coordinateImport.css'

export default function CoordinateImport() {
  const user = useAuthStore(s => s.user)
  const epoch = useAuthStore(s => s.authSessionEpoch)
  const identity = `${user?.tenant_id}:${user?.id}:${epoch}`
  return user && ['garage_owner', 'garage_admin'].includes(user.role) ? <ImportForm key={identity} actor={user} epoch={epoch} /> : <main className="coordinate-import"><h1>Coordinate import</h1><p>Garage owner or admin access required.</p></main>
}
function ImportForm({ actor, epoch }: { actor: Actor; epoch: number }) {
  const [text, setText] = useState('')
  const [exampleOpen, setExampleOpen] = useState(false)
  const [preview, setPreview] = useState<Checkpoint | null>(null)
  const [checkpoint, setCheckpoint] = useState<Checkpoint | null>(null)
  const [blocked, setBlocked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [projected, setProjected] = useState(false)
  const mounted = useRef(true)
  const pending = useRef(false)
  useEffect(() => {
    mounted.current = true
    try { const saved = readCheckpoint(localStorage, actor); setCheckpoint(saved); if (saved) { setText(JSON.stringify(saved.source, null, 2)); setMessage('Saved request restored. Reconcile by retrying the same request.'); } }
    catch { setBlocked(true); setMessage('Checkpoint unreadable. Import blocked; preserve browser data and reconcile before continuing.'); }
    return () => { mounted.current = false }
  }, [actor])
  function guard() {
    const current = useAuthStore.getState()
    if (!mounted.current || !current.isAuthenticated || !current.user || current.authSessionEpoch !== epoch) throw Error('Session changed. No further action allowed.')
    verifyActor(current.user, actor, actor.tenant_id || '')
  }
  async function readContext(tenant: string) {
    guard()
    const me = await api.get<Actor>('/auth/me'); guard(); verifyActor(me.data, actor, tenant)
    const board = await api.get<{ trucks: BoardTruck[] }>('/fleet/board'); guard()
    if (!Array.isArray(board.data.trucks)) throw Error('Fleet response unavailable.')
    return board.data.trucks
  }
  async function run(action: () => Promise<void>) {
    if (pending.current) return
    pending.current = true; setBusy(true); setMessage('')
    try { await action() } catch (error) { if (mounted.current) setMessage(error instanceof Error ? error.message : 'Request failed. Preserve this request and retry safely.') }
    finally { pending.current = false; if (mounted.current) setBusy(false) }
  }
  function validate() { void run(async () => {
    setPreview(null)
    const source = observationSchema.parse(JSON.parse(text))
    const trucks = await readContext(source.expected_tenant_id)
    const truck = matchTruck(trucks, source); checkFreshness(truck, source)
    setPreview(makeCheckpoint(source, actor, truck)); setMessage('Validated against current session and fleet. Ready to import one observation.')
  }) }
  function commit() { void run(async () => {
    setProjected(false)
    if (!navigator.locks) throw Error('Exclusive browser lock unavailable. Import blocked.')
    await navigator.locks.request(checkpointKey(actor), async () => {
    const attempt = checkpoint || preview
    if (!attempt || blocked) return
    const existing = readCheckpoint(localStorage, actor)
    if (existing && existing.payload.client_request_id !== attempt.payload.client_request_id) {
      setCheckpoint(existing); setPreview(null); setText(JSON.stringify(existing.source, null, 2))
      throw Error('Another tab saved a request. Restored it; reconcile this request first.')
    }
    const trucks = await readContext(attempt.tenant_id)
    const truck = matchTruck(trucks, attempt.source)
    if (truck.id !== attempt.vehicle_id || truck.board_membership_customer_id !== attempt.payload.fleet_customer_id) throw Error('Fleet membership changed. Import blocked.')
    if (attempt.receipt) {
      const visible = verifyProjection(trucks, attempt, attempt.receipt)
      setProjected(visible)
      setMessage(visible ? 'Saved receipt and fleet-board coordinates verified.' : 'Saved receipt confirmed; fleet-board projection does not match yet. Retry verification.')
      return
    }
    if (locationFingerprint(truck) !== attempt.baseline_location) throw Error('Fleet position changed since validation. Request retained; automatic retry blocked until this request is reconciled.')
    checkFreshness(truck, attempt.source)
    // Persist immutable request before the first POST. All retries reuse this exact request.
    persistCheckpoint(localStorage, actor, attempt)
    setCheckpoint(attempt); setPreview(null); guard()
    let response
    try { response = await api.post(`/fleet/trucks/${attempt.vehicle_id}/telemetry-snapshots`, attempt.payload) }
    catch { throw Error('Import outcome unconfirmed. Input is locked; retry this same request to reconcile. Nothing will receive a new request ID.') }
    guard()
    if (response.status !== 200 && response.status !== 201) throw Error('Unexpected response. Keep and retry this request for reconciliation.')
    const receipt = verifyReceipt(response.data, attempt)
    const saved = { ...attempt, receipt, response_status: response.status as 200 | 201 }
    setCheckpoint(saved)
    try { persistCheckpoint(localStorage, actor, saved) } catch { throw Error('Receipt confirmed, but browser storage failed. Download the receipt now; preserve the original request for reconciliation.') }
    setMessage('Receipt confirmed. Checking fleet map data…')
    try {
      const board = await readContext(attempt.tenant_id)
      const visible = verifyProjection(board, attempt, receipt)
      setProjected(visible)
      setMessage(visible ? 'Saved receipt and fleet-board coordinates verified.' : 'Saved receipt confirmed; fleet-board projection does not match yet. Retry verification.')
    } catch { if (mounted.current) setMessage('Saved receipt confirmed; fleet-board verification unavailable. Retry verification.') }
    })
  }) }
  function download() {
    if (!checkpoint?.receipt) return
    const url = URL.createObjectURL(new Blob([JSON.stringify({ ...checkpoint, fleet_board_verified: projected }, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url; link.download = `coordinate-receipt-${checkpoint.payload.client_request_id}.json`
    document.body.appendChild(link)
    link.click(); link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 10000)
  }
  async function next() {
    if (!checkpoint?.receipt || !projected) return
    try { if (!navigator.locks) throw Error(); await navigator.locks.request(checkpointKey(actor), () => { guard(); const stored = readCheckpoint(localStorage, actor); if (stored?.payload.client_request_id !== checkpoint.payload.client_request_id) throw Error(); localStorage.removeItem(checkpointKey(actor)); if (localStorage.getItem(checkpointKey(actor)) !== null) throw Error(); setCheckpoint(null); setPreview(null); setText(''); setProjected(false); setMessage('Ready for another observation.'); }) }
    catch { setMessage('Could not clear checkpoint. Keep the current request.'); }
  }
  return <main className="coordinate-import">
    <header><div><h1>Coordinate import</h1><p>One verified Motive observation</p></div><Link to="/fleet">Open fleet</Link></header>
    <p className="coordinate-import-note">Exact VIN only. Unknown observation time stays unknown. Source data and receipts remain in this browser until downloaded or cleared.</p>
    <label htmlFor="coordinate-source">Source observation JSON</label>
    <textarea id="coordinate-source" spellCheck={false} value={text} disabled={busy || !!checkpoint || blocked} onChange={e => { setText(e.target.value); setPreview(null) }} />
    <div className="coordinate-import-example"><button type="button" className="coordinate-import-example-toggle" aria-expanded={exampleOpen} aria-controls="coordinate-example" onClick={() => setExampleOpen(!exampleOpen)}>Synthetic format example <ChevronDown size={16} style={{ transform: exampleOpen ? 'rotate(180deg)' : undefined }} /></button>{exampleOpen && <pre id="coordinate-example">{JSON.stringify(exampleObservation, null, 2)}</pre>}</div>
    {(preview || checkpoint) && <dl><dt>VIN</dt><dd>{(checkpoint || preview)!.source.vin}</dd><dt>Coordinates</dt><dd>{(checkpoint || preview)!.source.lat}, {(checkpoint || preview)!.source.lng}</dd><dt>Observed</dt><dd>{(checkpoint || preview)!.source.observed_at || 'Unknown'}</dd><dt>Request</dt><dd>{(checkpoint || preview)!.payload.client_request_id}</dd></dl>}
    {checkpoint?.receipt && <dl aria-label="Saved receipt"><dt>Receipt</dt><dd>{checkpoint.receipt.id}</dd><dt>Captured</dt><dd>{checkpoint.receipt.captured_at}</dd><dt>HTTP status</dt><dd>{checkpoint.response_status ?? 'Unavailable'}</dd></dl>}
    <div className="coordinate-import-actions">
      {!checkpoint && <button className="dbtn" disabled={busy || blocked || !text} onClick={validate}>Validate</button>}
      {(preview || checkpoint) && <button className="dbtn" disabled={busy || blocked} onClick={commit}>{checkpoint?.receipt ? 'Verify fleet board' : checkpoint ? 'Retry same request' : 'Import observation'}</button>}
      {checkpoint?.receipt && <><button className="dbtn" onClick={download}>Download receipt</button><button className="dbtn" disabled={busy || !projected} onClick={next}>Next observation</button></>}
    </div>
    <p role="status" aria-live="polite">{busy ? 'Working… ' : ''}{message}</p>
  </main>
}
