import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ControlButton } from '@/components/ui/Controls'
import StaffSettlementDialog from '@/features/payments/StaffSettlementDialog'
import { formatMoney, moneyToCents } from '@/features/payments/money'
import type { ZelleReviewRow, ZelleReviewQueueState } from './useZelleReviewQueue'
import './zelleReviewQueue.css'

export default function ZelleReviewQueue({ queue, onOpenLegacy }: { queue: ZelleReviewQueueState; onOpenLegacy: (repairOrderId: string) => void }) {
  const client = useQueryClient()
  const [selected, setSelected] = useState<{ row: ZelleReviewRow; identity: string | null } | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  if (!queue.allowed) return null
  const refresh = () => { void queue.refetch() }
  return <section className="db-zelle-review" aria-labelledby="zelle-review-heading"><header><h2 ref={heading} tabIndex={-1} id="zelle-review-heading">Payment review</h2><ControlButton className="db-work-control" disabled={queue.isFetching} onClick={refresh}>{queue.isFetching ? 'Refreshing…' : 'Refresh requests'}</ControlButton></header>{queue.isError ? <div role="alert"><p>Zelle requests couldn’t load. Existing work remains available.</p><ControlButton className="db-work-control" onClick={refresh}>Try again</ControlButton></div> : queue.isLoading ? <p role="status">Loading Zelle requests…</p> : queue.rows.length ? <div className="db-zelle-review__rows">{queue.rows.map(row => {
    const amount = moneyToCents(row.principal_amount)
    const canonical = row.kind === 'canonical_zelle_attempt' && row.review_mode === 'canonical_attempt' && !!row.attempt_id
    const legacy = row.kind === 'legacy_zelle_submission' && row.review_mode === 'legacy_invoice'
    const provenance = row.report_status === 'explicit_report' ? 'Customer reported transfer sent' : row.report_status === 'legacy_report' ? 'Reported transfer' : 'Payment request awaiting review'
    return <article key={row.attempt_id || `legacy:${row.invoice_id}`}><div><strong>{row.customer_display_name}</strong><p>Invoice {row.display_invoice_number}</p><p>{provenance}</p></div><div className="db-zelle-review__amount"><span>{legacy ? 'Invoice amount' : 'Requested amount'}</span><strong>{amount !== null && amount > 0n ? formatMoney(row.principal_amount) : 'Unavailable'}</strong></div>{row.can_confirm && amount !== null && amount > 0n && canonical ? <ControlButton className="db-work-control" onClick={() => setSelected({ row, identity: queue.identity })} aria-label={`Review Zelle request for invoice ${row.display_invoice_number}`}>Review</ControlButton> : row.can_confirm && legacy && row.repair_order_id ? <ControlButton className="db-work-control" onClick={() => onOpenLegacy(row.repair_order_id!)} aria-label={`Review Zelle report for invoice ${row.display_invoice_number}`}>Review</ControlButton> : <span>Review unavailable</span>}</article>
  })}</div> : <p>No Zelle requests awaiting review.</p>}{selected && selected.identity === queue.identity && !queue.isError && <StaffSettlementDialog key={`${queue.identity}:${selected.row.invoice_id}`} open invoiceId={selected.row.invoice_id} invoiceNumber={selected.row.display_invoice_number} onClose={() => { setSelected(null); heading.current?.focus() }} onUpdated={() => { void client.invalidateQueries({ queryKey: ['zelle-review-queue'] }) }}/>}</section>
}

/** Resolve only an authorized queue record; URL identifiers never supply invoice authority. */
export function BoardPaymentReview({ queue, selectedId, onClose }: { queue: ZelleReviewQueueState; selectedId: string | null; onClose: () => void }) {
  const client = useQueryClient()
  if (!selectedId || !queue.allowed) return null
  const row = !queue.isError && queue.rows.find(item => item.attempt_id === selectedId && item.kind === 'canonical_zelle_attempt' && item.review_mode === 'canonical_attempt')
  const amount = row ? moneyToCents(row.principal_amount) : null
  if (!row || !row.can_confirm || amount === null || amount <= 0n) return <section className="db-work-state" role={queue.isLoading ? 'status' : 'alert'}><p>{queue.isLoading ? 'Loading selected payment review…' : queue.isError ? 'This payment review couldn’t load.' : 'This request is no longer available for review.'}</p>{queue.isError && <ControlButton className="db-work-control" onClick={() => { void queue.refetch() }}>Try again</ControlButton>}<ControlButton className="db-work-control" onClick={onClose}>Back to board</ControlButton></section>
  return <StaffSettlementDialog key={`${queue.identity}:${row.invoice_id}`} open invoiceId={row.invoice_id} invoiceNumber={row.display_invoice_number} onClose={onClose} onUpdated={() => { void client.invalidateQueries({ queryKey: ['zelle-review-queue'] }) }}/>
}
