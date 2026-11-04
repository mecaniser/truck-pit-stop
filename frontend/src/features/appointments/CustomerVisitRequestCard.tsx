import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ControlButton } from '@/components/ui/Controls'
import { getAuthenticatedSessionIdentity, useAuthStore } from '@/stores/authStore'
import type { VisitRequestResult } from '@/features/booking/booking-contract'
import { arrivalDateLabel, visitRequestLabels } from './visit-requests'
import api from '@/lib/api'

export default function CustomerVisitRequestCard({ request, vehicleLabel }: { request: VisitRequestResult; vehicleLabel: string }) {
  const identity = useAuthStore(getAuthenticatedSessionIdentity)
  const client = useQueryClient()
  const key = useRef(crypto.randomUUID())
  const submitting = useRef(false)
  const [confirming, setConfirming] = useState(false)
  const [needsRefresh, setNeedsRefresh] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const mayWithdraw = !!identity && ['requested', 'availability_review', 'accepted'].includes(request.status) && Number.isInteger(request.version)
  const current = () => identity && identity === getAuthenticatedSessionIdentity(useAuthStore.getState())
  const mutation = useMutation({ retry: false, mutationFn: async () => {
    if (!current() || !mayWithdraw || submitting.current) throw new Error('Request unavailable')
    submitting.current = true
    const response = await api.post(`/appointments/visit-requests/${request.id}/withdraw`, { expected_version: request.version }, { headers: { 'Idempotency-Key': key.current } })
    if (response.data?.request?.id !== request.id) throw new Error('Saved request unavailable')
    return response.data.request as VisitRequestResult
  }, onSuccess: async () => { if (!current()) return; setConfirming(false); await client.invalidateQueries({ queryKey: ['visit-requests'] }) }, onError: () => { if (!current()) return; setNeedsRefresh(true); setError('Your request couldn’t be checked. Refresh its status before trying again.') }, onSettled: () => { submitting.current = false } })
  return <article className="cp-panel p-4 space-y-2" aria-label={`Visit request ${request.request_reference}`}><h3 className="font-bold">{request.service_name || 'Service visit request'}</h3><p className="cp-unit">{vehicleLabel}</p><h4 className="font-semibold">{visitRequestLabels[request.status]}</h4>{request.status === 'accepted' ? <p>Arrive on <time dateTime={request.accepted_arrival_date || undefined}>{arrivalDateLabel(request.accepted_arrival_date)}</time>. The shop will start as availability allows.</p> : ['requested', 'availability_review'].includes(request.status) ? <p>The shop will confirm availability. No start time is reserved.</p> : request.status === 'declined' ? <p>The shop couldn’t accept this visit request. Contact the shop for another date.</p> : request.status === 'withdrawn' ? <p>This visit request has been withdrawn.</p> : <p>Your visit has been checked in with the shop.</p>}{request.preferred_date && !['accepted', 'fulfilled'].includes(request.status) && <p className="text-sm">Preferred date: <time dateTime={request.preferred_date}>{arrivalDateLabel(request.preferred_date)}</time></p>}{request.status === 'fulfilled' && request.accepted_arrival_date && <p className="text-sm">Arrival date: <time dateTime={request.accepted_arrival_date}>{arrivalDateLabel(request.accepted_arrival_date)}</time></p>}{request.customer_notes && <p className="text-sm whitespace-pre-wrap">{request.customer_notes}</p>}<p className="text-xs">Request {request.request_reference}</p>{error && <p role="alert">{error}</p>}{needsRefresh ? <ControlButton className="cp-secondary" disabled={mutation.isPending} onClick={async () => { try { await client.refetchQueries({ queryKey: ['visit-requests'] }, { throwOnError: true }) } catch { return }; if (current()) { setNeedsRefresh(false); setError(null); setConfirming(false) } }}>Refresh request status</ControlButton> : mayWithdraw && (confirming ? <div className="flex flex-wrap items-center gap-3"><p>Withdraw this request?</p><ControlButton className="cp-secondary" disabled={mutation.isPending} onClick={() => setConfirming(false)}>Keep request</ControlButton><ControlButton className="cp-secondary" disabled={mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? 'Withdrawing…' : 'Withdraw'}</ControlButton></div> : <ControlButton className="cp-text" onClick={() => setConfirming(true)}>Withdraw request</ControlButton>)}</article>
}
