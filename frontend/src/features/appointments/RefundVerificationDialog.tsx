import { useRef, useState } from 'react'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react'
import { useQueryClient } from '@tanstack/react-query'
import { ControlButton, ControlInput } from '@/components/ui/Controls'
import { useTheme } from '@/contexts/ThemeContext'
import { getAuthenticatedSessionIdentity, useAuthStore } from '@/stores/authStore'
import api from '@/lib/api'
import type { BookingPrepaymentView } from './booking-fulfillment'

export default function RefundVerificationDialog({ identity, initial, current, close, done, refresh }: { identity: string; initial: BookingPrepaymentView; current: BookingPrepaymentView | null; close: () => void; done: (message: string) => void; refresh: () => Promise<BookingPrepaymentView> }) {
  const { appearance } = useTheme()
  const client = useQueryClient()
  const user = useAuthStore(state => state.user)
  const [baseline, setBaseline] = useState(initial)
  const [reference, setReference] = useState('')
  const [busy, setBusy] = useState(false)
  const [blocked, setBlocked] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const saving = useRef(false)
  const key = useRef(crypto.randomUUID())
  const command = useRef<{ refund_id: string; expected_receipt_version: number; expected_booking_version: number } | null>(null)
  const isCurrent = () => identity === getAuthenticatedSessionIdentity(useAuthStore.getState())
  const stale = !current || current.customer?.id !== baseline.customer.id || current.vehicle?.id !== baseline.vehicle?.id || current.appointment_id !== baseline.appointment_id || current.receipt.id !== baseline.receipt.id || current.receipt.version !== baseline.receipt.version || current.booking_version !== baseline.booking_version
  const allowed = isCurrent() && ['garage_owner', 'garage_admin'].includes(user?.role || '') && current?.receipt.provider === 'quickbooks_payments' && baseline.receipt.provider === 'quickbooks_payments' && !stale && !blocked && !!reference.trim() && reference.trim().length <= 255
  async function submit() {
    if (!allowed || saving.current) return
    saving.current = true; setBusy(true)
    try {
      command.current ||= { refund_id: reference.trim(), expected_receipt_version: baseline.receipt.version, expected_booking_version: baseline.booking_version }
      const result = (await api.post(`/appointments/${baseline.appointment_id}/refund-verifications`, command.current, { headers: { 'Idempotency-Key': key.current } })).data
      const state = result.refund_verification?.state
      if (result.appointment_id !== baseline.appointment_id || result.receipt?.id !== baseline.receipt.id || result.refund_verification?.refund_id !== reference.trim() || !['verified', 'failed', 'pending', 'review_required'].includes(state)) throw new Error('Verification unavailable')
      if (!isCurrent()) return
      await Promise.all(['staff-reservation-detail', 'staff-reservations', 'invoice-settlement', 'invoices'].map(prefix => client.invalidateQueries({ queryKey: [prefix] })))
      if (isCurrent()) done(state === 'verified' ? 'Existing refund verified' : state === 'pending' ? 'Refund verification pending. Verified amounts remain unchanged.' : state === 'failed' ? 'The existing refund could not be verified. Verified amounts remain unchanged.' : 'Refund needs review. Verified amounts remain unchanged.')
    } catch {
      if (isCurrent()) { setBlocked(true); setMessage('Verification could not be completed. Refresh the saved reservation before checking again. Your reference is kept.') }
    } finally { saving.current = false; if (isCurrent()) setBusy(false) }
  }
  async function refreshSaved() {
    if (saving.current) return
    saving.current = true; setBusy(true)
    try { const next = await refresh(); if (isCurrent()) { setBaseline(next); setBlocked(false); setMessage(null) } } catch { if (isCurrent()) setMessage('Saved reservation could not load. Verification is paused.') } finally { saving.current = false; if (isCurrent()) setBusy(false) }
  }
  return <Dialog open onClose={() => { if (!busy) close() }} className="visit-request-dialog booking-fulfillment-dialog db-workflow-info-panel" data-appearance-mode={appearance.mode}><div className="visit-request-dialog-backdrop" aria-hidden="true"/><div className="visit-request-dialog-position"><DialogPanel className="visit-request-dialog-panel"><DialogTitle>Verify existing refund</DialogTitle><p>Check a refund already issued in QuickBooks.</p><form onSubmit={event => { event.preventDefault(); void submit() }}><label>QuickBooks refund reference<ControlInput value={reference} onChange={event => setReference(event.target.value)} required maxLength={255} disabled={busy || !!command.current}/></label>{(message || stale) && <p role="alert">{message || 'The reservation changed. Refresh the saved details before checking this refund.'}</p>}{(blocked || stale) && <ControlButton type="button" className="visit-request-button" disabled={busy} onClick={() => { void refreshSaved() }}>Refresh saved reservation</ControlButton>}<div className="visit-request-actions"><ControlButton type="button" className="visit-request-button" disabled={busy} onClick={close}>Close</ControlButton><ControlButton type="submit" className="visit-request-button visit-request-button-primary" disabled={!allowed || busy}>{busy ? 'Checking…' : 'Verify existing refund'}</ControlButton></div></form></DialogPanel></div></Dialog>
}
