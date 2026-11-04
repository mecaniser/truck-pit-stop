import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ControlButton } from '@/components/ui/Controls'
import StaffSettlementDialog from '@/features/payments/StaffSettlementDialog'
import { formatMoney, moneyToCents } from '@/features/payments/money'
import type { ZelleReviewRow, ZelleReviewQueueState } from './useZelleReviewQueue'
import './zelleReviewQueue.css'

function boundResolution(row: ZelleReviewRow): boolean {
  return !!row.resolution && row.resolution.attempt_id === row.attempt_id && row.resolution.invoice_id === row.invoice_id && row.resolution.rail === row.rail
}
function reviewDescription(row: ZelleReviewRow): string {
  if (row.kind === 'legacy_zelle_submission') return row.report_status === 'legacy_report' ? 'Reported transfer' : 'Payment request awaiting review'
  if (!boundResolution(row)) return 'Payment details unavailable'
  if (row.kind === 'canonical_efs_attempt') return row.efs?.status === 'review_required' ? 'EFS payment needs review' : 'EFS code awaiting verification'
  const status = row.resolution!.checkout_status
  if (row.rail === 'card') return status === 'checkout_started' ? 'Card checkout started' : status === 'verification_pending' ? 'Card verification pending' : 'Card payment needs review'
  if (status === 'review_required') return 'Zelle payment needs review'
  if (status === 'verification_pending') return 'Zelle verification pending'
  return row.report_status === 'explicit_report' && status === 'transfer_reported' ? 'Customer reported transfer sent' : row.report_status === 'legacy_report' ? 'Reported transfer' : 'Payment request awaiting review'
}

export default function ZelleReviewQueue({ queue, compact = false, onOpenQueue, onOpenLegacy }: { queue: ZelleReviewQueueState; compact?: boolean; onOpenQueue: () => void; onOpenLegacy: (repairOrderId: string) => void }) {
  const client = useQueryClient()
  const [selected, setSelected] = useState<{ row: ZelleReviewRow; identity: string | null } | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  if (!queue.allowed) return null
  const refresh = () => { void queue.refetch() }
  if (compact) return queue.isSuccess && !queue.rows.length ? null : <div className="db-zelle-review db-zelle-review--compact"><div><strong>Payment review</strong><span>{queue.isError ? 'Couldn’t load payment requests' : queue.isLoading ? 'Checking payment requests…' : `${queue.rows.length} payment ${queue.rows.length === 1 ? 'request' : 'requests'} awaiting review`}</span></div><ControlButton className="db-work-control" onClick={onOpenQueue}>Review payments</ControlButton></div>
  return <section className="db-zelle-review" aria-labelledby="zelle-review-heading"><header><h2 ref={heading} tabIndex={-1} id="zelle-review-heading">Payment review</h2><ControlButton className="db-work-control" disabled={queue.isFetching} onClick={refresh}>{queue.isFetching ? 'Refreshing…' : 'Refresh requests'}</ControlButton></header>{queue.isError ? <div role="alert"><p>Payment requests couldn’t load. Existing work remains available.</p><ControlButton className="db-work-control" onClick={refresh}>Try again</ControlButton></div> : queue.isLoading ? <p role="status">Loading payment requests…</p> : queue.rows.length ? <div className="db-zelle-review__rows">{queue.rows.map(row => {
    const amount = moneyToCents(row.principal_amount)
    const canonical = ((row.kind === 'canonical_zelle_attempt' && row.rail === 'zelle') || (row.kind === 'canonical_card_attempt' && row.rail === 'card') || (row.kind === 'canonical_efs_attempt' && row.rail === 'fleet_payment' && row.efs?.provider === 'EFS')) && row.review_mode === 'canonical_attempt' && !!row.attempt_id && boundResolution(row)
    const legacy = row.kind === 'legacy_zelle_submission' && row.rail === 'zelle' && row.review_mode === 'legacy_invoice'
    const provenance = reviewDescription(row)
    return <article key={row.attempt_id || `legacy:${row.invoice_id}`}><div><strong>{row.customer_display_name}</strong><p>Invoice {row.display_invoice_number}</p><p>{provenance}</p></div><div className="db-zelle-review__amount"><span>{legacy ? 'Invoice amount' : 'Requested amount'}</span><strong>{amount !== null && amount > 0n ? formatMoney(row.principal_amount) : 'Unavailable'}</strong></div>{(row.rail === 'card' || row.rail === 'fleet_payment' && !!row.efs && (row.efs.can_reveal || row.efs.can_verify || row.efs.can_reject) || row.can_confirm) && amount !== null && amount > 0n && canonical ? <ControlButton className="db-work-control" onClick={() => setSelected({ row, identity: queue.identity })} aria-label={`Review ${row.rail === 'card' ? 'card' : row.rail === 'fleet_payment' ? 'EFS' : 'Zelle'} request for invoice ${row.display_invoice_number}`}>Review</ControlButton> : row.can_confirm && legacy && row.repair_order_id ? <ControlButton className="db-work-control" onClick={() => onOpenLegacy(row.repair_order_id!)} aria-label={`Review Zelle report for invoice ${row.display_invoice_number}`}>Review</ControlButton> : <span>Review unavailable</span>}</article>
  })}</div> : <p>No payment requests awaiting review.</p>}{selected && selected.identity === queue.identity && !queue.isError && <StaffSettlementDialog key={`${queue.identity}:${selected.row.invoice_id}`} open invoiceId={selected.row.invoice_id} reviewAttemptId={selected.row.attempt_id || undefined} invoiceNumber={selected.row.display_invoice_number} onClose={() => { setSelected(null); heading.current?.focus() }} onUpdated={() => { void client.invalidateQueries({ queryKey: ['zelle-review-queue'] }) }}/>}</section>
}
