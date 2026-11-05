import React, { useState, useSyncExternalStore } from 'react'
import { AxiosError } from 'axios'
import TenantBrandLogo from '@/components/brand/TenantBrandLogo'
import { ControlButton } from '@/components/ui/Controls'
import { resolvePreview, type PreviewOutcome, type PreviewState } from './paymentRequestPreviewState'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@/index.css'
import './payment-requests-preview.css'
import SettlementPaymentPanel from '@/features/payments/SettlementPaymentPanel'
import api from '@/lib/api'
import SettlementSummaryCard from '@/features/payments/SettlementSummaryCard'
import type { InvoiceSettlementSummary, PaymentAllocation } from '@/features/payments/types'
import type { ResolutionProjection } from '@/features/payments/attemptResolutionTypes'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'

if (!import.meta.env.DEV) throw new Error('Development preview only')
const invoiceId = 'preview-payment-requests'
const summary: InvoiceSettlementSummary = { ...DB048_SETTLEMENT_FIXTURES.unpaid.summary, invoice_id: invoiceId, principal_total: '268.44', outstanding_balance: '268.44', confirmed_principal: '0.00', active_pending_principal: '268.44', allocatable_balance: '0.00', state: 'payment_pending', version: 1 }
const none = { cancel_unsent: false, check_provider_status: false, request_review: false, release_with_terminal_evidence: false, record_late_receipt: false }
function row(id: string, amount: string, status: ResolutionProjection['checkout_status'], rail: 'card' | 'zelle'): PaymentAllocation {
  const resolution: ResolutionProjection = { attempt_id: id, invoice_id: invoiceId, attempt_version: 1, settlement_version: 1, rail, requested_principal: amount, currency: 'USD', attempt_state: status === 'cancelled' ? 'failed' : 'pending', checkout_status: status, reservation_amount: status === 'cancelled' ? '0.00' : amount, can_retry: false, actions: { ...none, cancel_unsent: status === 'checkout_started' }, block_reason: status === 'review_required' ? { code: 'provider_review_required', message: 'The shop must review this payment before you try again.' } : null, resolution_notice: status === 'cancelled' ? { kind: 'request_cancelled', message: 'Payment request canceled. No payment was recorded. You can try again.', resolved_at: '2026-11-05T12:00:00Z' } : null, review_status: status === 'review_required' ? 'requested' : 'none' }
  return { ...DB048_SETTLEMENT_FIXTURES.pendingZelle500.allocations[0], id, attempt_id: id, rail, provider: rail === 'card' ? 'quickbooks_payments' : 'manual', principal_amount: amount, applied_principal_amount: '0.00', state: status === 'cancelled' ? 'failed' : 'pending', created_at: '2026-11-05T12:00:00Z', confirmed_at: null, actor_name: null, reference_number: null, card_fee_amount: '0.00', card_fee_tax_amount: '0.00', provider_charge_amount: amount, resolution }
}
const rows = [row('preview-card', '168.44', 'checkout_started', 'card'), row('preview-review', '100.00', 'review_required', 'card'), row('preview-canceled', '168.44', 'cancelled', 'zelle')]

let current: PreviewState = { summary, rows }
let selectedOutcome: PreviewOutcome = 'cancelled'
const subscribers = new Set<() => void>()
const subscribe = (callback: () => void) => { subscribers.add(callback); return () => { subscribers.delete(callback) } }
function publish(next: PreviewState) { current = next; subscribers.forEach(callback => callback()) }
// This document's Axios adapter has no network fallback. Unknown calls fail closed.
api.defaults.adapter = async config => {
  const match = /^\/payments\/attempts\/(preview-card)\/resolution$/.exec(config.url || '')
  if (config.method !== 'post' || !match) throw new AxiosError('Preview action unavailable.', 'ERR_PREVIEW', config, undefined, { config, data: { detail: 'Reset the preview to try this action.' }, status: 409, statusText: 'Conflict', headers: {} })
  const command = typeof config.data === 'string' ? JSON.parse(config.data) : config.data
  try {
    const result = resolvePreview(current, match[1], command, selectedOutcome)
    publish(result.state)
    return { data: result.response, status: 200, statusText: 'OK', headers: {}, config }
  } catch (error) {
    throw new AxiosError('Preview action unavailable.', 'ERR_PREVIEW', config, undefined, { config, data: { detail: error instanceof Error ? error.message : 'Reset the preview.' }, status: 409, statusText: 'Conflict', headers: {} })
  }
}
export function Preview() {
  const state = useSyncExternalStore(subscribe, () => current)
  const [outcome, setOutcome] = useState<PreviewOutcome>('cancelled')
  const [epoch, setEpoch] = useState(0)
  const [outcomesOpen, setOutcomesOpen] = useState(false)
  const reset = () => { publish({ summary, rows }); setEpoch(value => value + 1) }
  return <div data-db-touch-controls style={{ minHeight: '100vh', background: '#10131c', color: '#edf0f6' }}>
    <aside aria-label="Preview controls" className="payment-preview-controls">
      <ControlButton aria-expanded={outcomesOpen} aria-controls="preview-outcomes" onClick={() => setOutcomesOpen(open => !open)}>Preview outcomes</ControlButton>
      {outcomesOpen && <div id="preview-outcomes" role="group" aria-label="Cancellation outcome">{([['cancelled', 'Canceled'], ['review_required', 'Needs shop review'], ['received', 'Already paid']] as const).map(([value, label]) => <ControlButton key={value} aria-pressed={outcome === value} onClick={() => { selectedOutcome = value; setOutcome(value); setOutcomesOpen(false); reset() }}>{label}</ControlButton>)}</div>}
      <ControlButton onClick={reset}>Reset</ControlButton>
    </aside>
    <header className="payment-preview-brand"><TenantBrandLogo tenantLogoUrl="https://truckpitstop.com/wp-content/uploads/2025/01/Trasp-white-1080x400-1.png" tenantName="Truck Pit Stop" className="w-[100px]" /><span>Truck Pit Stop</span></header>
    <main className="payment-preview-main">
      <section className="cp-invoice-balance-header" aria-label="Invoice balance"><p>Invoice TPS-1687</p><p>Balance due</p><h1>${Number(state.summary.outstanding_balance).toFixed(2)}</h1></section>
      <SettlementSummaryCard hideAvailable={Number(state.summary.allocatable_balance) > 0} key={epoch} summary={state.summary} streamlined audience="customer" allocations={state.rows} resolutionControls={{ access: { kind: 'authenticated', invoiceId }, audience: 'customer', onUpdated: next => publish({ ...current, summary: next }) }} />
      {Number(state.summary.allocatable_balance) > 0 && <div className="mt-6"><SettlementPaymentPanel access={{ kind: 'authenticated', invoiceId }} summary={state.summary} audience="customer" zelleRecipient={{ display: 'billing@example.test', memo: 'TPS-1687' }} submissionBlockedReason="Payment submission is disabled in this preview." onUpdated={next => publish({ ...current, summary: next })} /></div>}
    </main>
  </div>
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={new QueryClient()}><Preview /></QueryClientProvider></React.StrictMode>)
