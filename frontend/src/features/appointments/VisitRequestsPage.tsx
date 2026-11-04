import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ControlButton, ControlInput } from '@/components/ui/Controls'
import { getAuthenticatedSessionIdentity, useAuthStore } from '@/stores/authStore'
import BaseSelect from '@/components/BaseSelect'
import type { RepairOrder, Vehicle } from '@/types'
import { useTheme } from '@/contexts/ThemeContext'
import { getPortalItems } from '@/features/customer-portal/portal-context'
import api from '@/lib/api'
import { arrivalDateLabel, requestVehicleLabel, visitRequestLabels, type StaffVisitRequest } from './visit-requests'
import { shopWorkReturnUrl } from '@/features/dashboard/shopWorkNavigation'
import './visit-requests.css'
import StaffReservationsPage from './StaffReservationsPage'
import { useStaffRequests, visitRequestStaffRoles } from './staffVisitRequestQueries'

function canAct(row: StaffVisitRequest, action: 'review' | 'accept' | 'decline' | 'fulfill') {
  return action === 'review' ? row.can_review : action === 'accept' ? row.can_accept ?? row.can_review : action === 'decline' ? row.can_decline ?? row.can_review : row.can_fulfill ?? row.can_review
}
export default function VisitRequestsPage() {
  const user = useAuthStore(state => state.user)
  const identity = useAuthStore(getAuthenticatedSessionIdentity)
  if (!identity || !visitRequestStaffRoles.includes(user?.role || '')) return <div role="alert" className="visit-requests"><h1>Visit requests unavailable</h1><p>Your role cannot review visit requests.</p></div>
  return <ServiceVisitsWorkspace key={identity} identity={identity}/ >
}
function ServiceVisitsWorkspace({ identity }: { identity: string }) {
  const [params] = useSearchParams()
  const reservations = params.get('view') === 'reservations'
  const sectionUrl = (view: string) => { const next = new URLSearchParams(params); next.delete('request'); next.delete('appointment_id'); if (view === 'reservations') next.set('view', view); else next.delete('view'); return `/dashboard/visit-requests?${next}` }
  return <div className="min-h-0"><nav aria-label="Service visit sections" className="visit-requests-tools visit-requests-section-nav"><Link data-db-control="action" className="visit-request-button" aria-current={!reservations ? 'page' : undefined} to={sectionUrl('requests')}>Requests</Link><Link data-db-control="action" className="visit-request-button" aria-current={reservations ? 'page' : undefined} to={sectionUrl('reservations')}>Reservations</Link></nav>{reservations ? <StaffReservationsPage/> : <StaffQueue identity={identity}/>}</div>
}
function StaffQueue({ identity }: { identity: string }) {
  const query = useStaffRequests(identity)
  const [params] = useSearchParams()
  const requestedId = params.get('request')
  const boardReturn = shopWorkReturnUrl(params)
  const selectedHeading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { if (requestedId && query.isSuccess) selectedHeading.current?.focus() }, [requestedId, query.isSuccess])
  const [all, setAll] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [selected, setSelected] = useState<{ row: StaffVisitRequest; action: 'review' | 'accept' | 'decline' | 'fulfill' } | null>(null)
  const rows = query.isError ? [] : (query.data || []).filter(row => requestedId ? row.id === requestedId : all || ['requested', 'availability_review'].includes(row.status))
  return <div className="visit-requests"><header className="visit-requests-header"><div><h1 ref={selectedHeading} tabIndex={-1}>{requestedId ? 'Visit request' : 'Visit requests'}</h1><p className="visit-requests-muted mt-2">Review a customer’s preferred visit date. No start time is reserved.</p></div>{!boardReturn && <Link data-db-control="action" className="visit-request-button" to="/dashboard">Back to Shop Work</Link>}</header>{!requestedId && <div className="visit-requests-tools"><ControlButton className="visit-request-button" aria-pressed={!all} onClick={() => setAll(false)}>Needs review</ControlButton><ControlButton className="visit-request-button" aria-pressed={all} onClick={() => setAll(true)}>All requests</ControlButton></div>}
    {notice && <p role="status">{notice}</p>}
    {query.isLoading ? <p role="status">Loading visit requests…</p> : query.isError ? <div role="alert"><p>Visit requests couldn’t load.</p><ControlButton className="visit-request-button" onClick={() => { void query.refetch() }}>Try again</ControlButton></div> : rows.length ? rows.map(row => <article key={row.id} className="visit-request-row"><div className="visit-request-row-head"><div><h2>{row.customer.company_name || row.customer.display_name}</h2>{row.customer.company_name && <p className="visit-requests-muted">{row.customer.display_name}</p>}</div><span className="visit-request-status">{visitRequestLabels[row.status]}</span></div><div className="visit-request-meta"><div><strong>{row.service.name}</strong><p className="visit-requests-muted">{requestVehicleLabel(row.vehicle)}</p></div><div>{row.accepted_arrival_date ? <p>Arrival date · {arrivalDateLabel(row.accepted_arrival_date)}</p> : <p>Preferred date · {row.preferred_date ? arrivalDateLabel(row.preferred_date) : 'No preference'}</p>}<p className="visit-requests-muted">{row.request_reference}</p>{(row.customer.phone || row.customer.email) && <p className="visit-requests-muted">{[row.customer.phone, row.customer.email].filter(Boolean).join(' · ')}</p>}</div></div>{row.customer_notes && <p className="visit-request-note">{row.customer_notes}</p>}{row.internal_review_note && <p className="visit-request-note"><strong>Staff note:</strong> {row.internal_review_note}</p>}<div className="visit-request-actions">{['requested', 'availability_review'].includes(row.status) && <>{row.can_review && row.status === 'requested' && <ControlButton className="visit-request-button" onClick={() => setSelected({ row, action: 'review' })}>Start review</ControlButton>}{canAct(row, 'accept') && <ControlButton className="visit-request-button visit-request-button-primary" onClick={() => setSelected({ row, action: 'accept' })}>Accept visit</ControlButton>}{canAct(row, 'decline') && <ControlButton className="visit-request-button" onClick={() => setSelected({ row, action: 'decline' })}>Decline</ControlButton>}</>}{row.status === 'accepted' && <>{canAct(row, 'accept') && <ControlButton className="visit-request-button" onClick={() => setSelected({ row, action: 'accept' })}>Change arrival date</ControlButton>}{canAct(row, 'fulfill') && <ControlButton className="visit-request-button" onClick={() => setSelected({ row, action: 'fulfill' })}>Record check-in</ControlButton>}</>}</div></article>) : requestedId ? <p role="alert">This visit request is no longer available.</p> : <p>No {all ? '' : 'pending '}visit requests.</p>}
    {selected && <ReviewDialog key={`${selected.row.id}:${selected.action}`} identity={identity} row={selected.row} action={selected.action} onSaved={updated => setNotice(`${visitRequestLabels[updated.status]}${updated.accepted_arrival_date ? ` · ${arrivalDateLabel(updated.accepted_arrival_date)}` : ''}`)} onClose={() => setSelected(null)} refresh={async () => { const result = await query.refetch(); if (result.isError) throw new Error('Read unavailable'); return result.data || [] }}/ >}
  </div>
}
function ReviewDialog({ identity, row, action, onClose, refresh, onSaved }: { identity: string; row: StaffVisitRequest; action: 'review' | 'accept' | 'decline' | 'fulfill'; onClose: () => void; refresh: () => Promise<StaffVisitRequest[]>; onSaved: (request: StaffVisitRequest) => void }) {
  const { appearance } = useTheme()
  const client = useQueryClient()
  const [baseline, setBaseline] = useState(row)
  const [date, setDate] = useState(row.accepted_arrival_date || row.preferred_date || '')
  const [note, setNote] = useState('')
  const validReason = !(baseline.status === 'accepted' || action === 'fulfill') || !!note.trim()
  const [repairOrderId, setRepairOrderId] = useState('')
  const [reviewedVehicle, setReviewedVehicle] = useState('')
  const intakeOrders = useQuery({ queryKey: ['visit-request-intake-orders', identity, row.customer.id], queryFn: ({ signal }) => getPortalItems<RepairOrder>('/repair-orders', { customer_id: row.customer.id }, signal), enabled: action === 'fulfill', retry: false })
  const intakeVehicles = useQuery({ queryKey: ['visit-request-intake-vehicles', identity, row.customer.id], queryFn: ({ signal }) => getPortalItems<Vehicle>('/vehicles', { customer_id: row.customer.id }, signal), enabled: action === 'fulfill' && !row.vehicle, retry: false })
  const eligibleOrders = (intakeOrders.isError ? [] : intakeOrders.data || []).filter(order => order.customer_id === row.customer.id && !['cancelled'].includes(order.status) && !order.source && !order.imported_billing && (!row.vehicle || order.vehicle_id === row.vehicle.id))
  const selectedOrder = eligibleOrders.find(order => order.id === repairOrderId)
  const validIntake = action !== 'fulfill' || (!!selectedOrder && !!note.trim() && (!!row.vehicle || (reviewedVehicle === selectedOrder.vehicle_id && (intakeVehicles.data || []).some(vehicle => vehicle.id === reviewedVehicle))))
  const [needsReview, setNeedsReview] = useState(false)
  const [latest, setLatest] = useState<StaffVisitRequest | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const key = useRef(crypto.randomUUID())
  const saving = useRef(false)
  const isCurrent = () => identity === getAuthenticatedSessionIdentity(useAuthStore.getState())
  const loadLatest = async () => {
    setRefreshing(true)
    try { const rows = await refresh(); if (isCurrent()) setLatest(rows.find(item => item.id === row.id) || null) }
    catch { if (isCurrent()) setMessage('The saved request couldn’t load. Your draft is still here.') }
    finally { if (isCurrent()) setRefreshing(false) }
  }
  const mutation = useMutation({ retry: false, mutationFn: async () => {
    if (!isCurrent() || !canAct(baseline, action) || saving.current) throw new Error('Request unavailable')
    saving.current = true
    if (!validIntake || !validReason) throw new Error('Check the intake selection')
    const response = await api.post(`/appointments/visit-requests/${row.id}/${action}`, { expected_version: baseline.version, ...(action === 'accept' ? { arrival_date: date } : {}), ...(action === 'fulfill' ? { repair_order_id: repairOrderId, reason: note.trim(), ...(!row.vehicle ? { expected_vehicle_id: reviewedVehicle } : {}) } : note.trim() ? { internal_note: note.trim() } : {}) }, { headers: { 'Idempotency-Key': key.current } })
    if (!response.data?.request || response.data.request.id !== row.id) throw new Error('Saved request unavailable')
    return response.data.request as StaffVisitRequest
  }, onSuccess: async (updated: StaffVisitRequest) => { if (!isCurrent()) return; onSaved(updated); await Promise.all([client.invalidateQueries({ queryKey: ['staff-visit-requests'] }), client.invalidateQueries({ queryKey: ['visit-requests'] })]); if (isCurrent()) onClose() }, onError: async (failure: unknown) => { if (!isCurrent()) return; const response = (failure as { response?: { status?: number; data?: { detail?: { message?: string } } } }).response; if (response?.status === 422) { setMessage(response.data?.detail?.message || 'Check the date and staff note, then try again.'); return }; setNeedsReview(true); setMessage('The request may have changed. Review its saved state before continuing. Your draft is kept.'); await loadLatest() }, onSettled: () => { saving.current = false } })
  const title = action === 'fulfill' ? 'Record check-in' : action === 'accept' ? baseline.status === 'accepted' ? 'Change arrival date' : 'Accept visit' : action === 'decline' ? 'Decline visit request' : 'Start review'
  return <Dialog open onClose={() => { if (!mutation.isPending) onClose() }} className="visit-request-dialog db-workflow-info-panel" data-appearance-mode={appearance.mode}><div className="visit-request-dialog-backdrop" aria-hidden="true"/><div className="visit-request-dialog-position"><DialogPanel className="visit-request-dialog-panel"><DialogTitle>{title}</DialogTitle><p>{row.customer.company_name || row.customer.display_name} · {row.service.name}</p><form onSubmit={event => { event.preventDefault(); if (!needsReview && !mutation.isPending && !saving.current && (action !== 'accept' || date) && validIntake && validReason) mutation.mutate() }}>{action === 'fulfill' && <><p className="visit-requests-muted">Choose the existing repair order created at intake. This records check-in only.</p><label>Repair order<BaseSelect variant={appearance.mode === 'light' ? 'light' : 'dark'} ariaLabel="Intake repair order" options={eligibleOrders.map(order => ({ value: order.id, label: order.order_number, subLabel: order.description || undefined }))} value={repairOrderId} onChange={setRepairOrderId} searchable selectOnly heightClass="h-[44px]" optionHeightClass="min-h-[44px]" disabled={intakeOrders.isLoading || intakeOrders.isError || mutation.isPending}/></label>{!row.vehicle && <label>Vehicle reviewed at intake<BaseSelect variant={appearance.mode === 'light' ? 'light' : 'dark'} ariaLabel="Vehicle reviewed at intake" options={(intakeVehicles.isError ? [] : intakeVehicles.data || []).map(vehicle => ({ value: vehicle.id, label: requestVehicleLabel(vehicle) }))} value={reviewedVehicle} onChange={setReviewedVehicle} searchable selectOnly heightClass="h-[44px]" optionHeightClass="min-h-[44px]" disabled={intakeVehicles.isLoading || intakeVehicles.isError || mutation.isPending}/></label>}{(intakeOrders.isError || intakeVehicles.isError) && <p role="alert">Intake records couldn’t load. Close and reopen this request to try again.</p>}</>}{action === 'accept' && <><label>Arrival date<ControlInput type="date" required value={date} disabled={mutation.isPending} onChange={event => setDate(event.target.value)}/></label><p className="visit-requests-muted">No guaranteed start time. The shop will start as availability allows.</p></>}<label>Staff note {action === 'fulfill' ? '(reason for check-in)' : baseline.status === 'accepted' ? '(reason for change)' : '(optional)'}<textarea value={note} disabled={mutation.isPending} onChange={event => setNote(event.target.value)} required={baseline.status === 'accepted' || action === 'fulfill'}/></label>{message && <p role="alert">{message}</p>}{needsReview && <div className="visit-request-conflict">{refreshing ? <p role="status">Loading saved request…</p> : latest ? <><p>Saved state: {visitRequestLabels[latest.status]}{latest.accepted_arrival_date ? ` · ${arrivalDateLabel(latest.accepted_arrival_date)}` : ''}</p>{canAct(latest, action) && (action === 'accept' ? ['requested', 'availability_review', 'accepted'].includes(latest.status) : action === 'fulfill' ? latest.status === 'accepted' : action === 'review' ? latest.status === 'requested' : ['requested', 'availability_review'].includes(latest.status)) && <ControlButton className="visit-request-button" type="button" onClick={() => { setBaseline(latest); setNeedsReview(false); setLatest(null); setMessage(null); key.current = crypto.randomUUID() }}>Keep draft and review again</ControlButton>}</> : <ControlButton className="visit-request-button" type="button" onClick={() => { void loadLatest() }}>Refresh saved request</ControlButton>}</div>}<div className="visit-request-actions"><ControlButton className="visit-request-button" type="button" disabled={mutation.isPending} onClick={onClose}>Close</ControlButton><ControlButton className="visit-request-button visit-request-button-primary" type="submit" disabled={mutation.isPending || needsReview || !canAct(baseline, action) || !validIntake || !validReason || (action === 'accept' && !date)}>{mutation.isPending ? 'Saving…' : title}</ControlButton></div></form></DialogPanel></div></Dialog>
}
