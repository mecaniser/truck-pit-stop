import React from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@/index.css'
import api from '@/lib/api'
import SettlementSummaryCard from '@/features/payments/SettlementSummaryCard'
import type { InvoiceSettlementSummary, PaymentAllocation } from '@/features/payments/types'
import type { ResolutionProjection } from '@/features/payments/attemptResolutionTypes'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'

if (!import.meta.env.DEV) throw new Error('Development preview only')
// This presentation fixture never sends API requests or touches financial records.
api.interceptors.request.use(() => Promise.reject(new Error('Preview only. No payment request was sent.')))
const invoiceId = 'preview-payment-requests'
const summary: InvoiceSettlementSummary = { ...DB048_SETTLEMENT_FIXTURES.unpaid.summary, invoice_id: invoiceId, principal_total: '268.44', outstanding_balance: '268.44', confirmed_principal: '0.00', active_pending_principal: '268.44', allocatable_balance: '0.00', state: 'payment_pending', version: 1 }
const none = { cancel_unsent: false, check_provider_status: false, request_review: false, release_with_terminal_evidence: false, record_late_receipt: false }
function row(id: string, amount: string, status: ResolutionProjection['checkout_status'], rail: 'card' | 'zelle'): PaymentAllocation {
  const resolution: ResolutionProjection = { attempt_id: id, invoice_id: invoiceId, attempt_version: 1, settlement_version: 1, rail, requested_principal: amount, currency: 'USD', attempt_state: status === 'cancelled' ? 'failed' : 'pending', checkout_status: status, reservation_amount: status === 'cancelled' ? '0.00' : amount, can_retry: false, actions: { ...none, cancel_unsent: status === 'checkout_started' }, block_reason: status === 'review_required' ? { code: 'provider_review_required', message: 'The shop must review this payment before you try again.' } : null, resolution_notice: status === 'cancelled' ? { kind: 'request_cancelled', message: 'Payment request canceled. No payment was recorded. You can try again.', resolved_at: '2026-11-05T12:00:00Z' } : null, review_status: status === 'review_required' ? 'requested' : 'none' }
  return { ...DB048_SETTLEMENT_FIXTURES.pendingZelle500.allocations[0], id, attempt_id: id, rail, provider: rail === 'card' ? 'quickbooks_payments' : 'manual', principal_amount: amount, applied_principal_amount: '0.00', state: status === 'cancelled' ? 'failed' : 'pending', created_at: '2026-11-05T12:00:00Z', confirmed_at: null, actor_name: null, reference_number: null, card_fee_amount: '0.00', resolution }
}
const rows = [row('preview-card', '168.44', 'checkout_started', 'card'), row('preview-review', '100.00', 'review_required', 'card'), row('preview-canceled', '168.44', 'cancelled', 'zelle')]
createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={new QueryClient()}><div data-db-touch-controls style={{ minHeight: '100vh', background: '#0f131c', color: '#edf0f6' }}><header style={{ height: 64, borderBottom: '1px solid #2a3245', display: 'flex', alignItems: 'center', padding: '0 24px', gap: 12 }}><img alt="Truck Pit Stop logo" src="https://truckpitstop.com/wp-content/uploads/2025/01/Trasp-white-1080x400-1.png" style={{ width: 100 }} /><span style={{ fontWeight: 600 }}>Truck Pit Stop</span></header><main style={{ maxWidth: 672, padding: '24px 16px 48px', margin: '0 auto' }}><p style={{ textAlign: 'center', fontSize: 14, color: '#99a4b7', marginBottom: 16 }}>Invoice TPS-1687</p><p style={{ textAlign: 'center', fontSize: 12, color: '#99a4b7' }}>Balance due</p><h1 style={{ textAlign: 'center', fontWeight: 800, fontSize: 44, margin: '0 0 24px', letterSpacing: '-0.03em' }}>$268.44</h1><SettlementSummaryCard summary={summary} streamlined audience="customer" allocations={rows} resolutionControls={{ access: { kind: 'authenticated', invoiceId }, audience: 'customer', onUpdated: () => {} }} /></main></div></QueryClientProvider></React.StrictMode>)
