import { useRef, useState } from 'react'
import { AxiosError } from 'axios'
import { ControlButton } from '@/components/ui/Controls'
import { activateSourceCollection, fetchSourceCollection, prepareSourceCollection, previewSourceCollection } from './api'
import type { SourceCollectionPreview, SourceCollectionSummary as Summary } from './types'
import SourceCollectionSummary from './SourceCollectionSummary'
import EtsReceiptTasks from './EtsReceiptTasks'

const failure = (error: unknown) => {
  if (error instanceof AxiosError) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (detail?.message && typeof detail.message === 'string') return detail.message
  }
  return 'Could not verify the handoff. Refresh the source invoice before continuing.'
}
const holdLabel = (reason: string) => {
  if (/stale|fresh|observed/.test(reason)) return 'The ETS record needs a newer verified balance check.'
  if (/customer|bill.to|tenant/.test(reason)) return 'The original customer and invoice ownership need review.'
  if (/pending|attempt/.test(reason)) return 'A payment is still being resolved. Wait for its confirmed result.'
  if (/paid|zero|positive/.test(reason)) return 'The source does not show a positive unpaid balance to transfer.'
  if (/accounting|quickbooks/.test(reason)) return 'The existing accounting invoice needs reconciliation.'
  return 'The source invoice or its payment history could not be verified.'
}

export default function SourceCollectionPanel({ sourceInvoiceId, customerId }: { sourceInvoiceId: string; customerId: string }) {
  const [preview, setPreview] = useState<SourceCollectionPreview | null>(null)
  const [handoff, setHandoff] = useState<Summary | null>(null)
  const [acknowledged, setAcknowledged] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Reuse mutation keys after an uncertain response; never issue a second
  // activation merely because the first response failed to reach the browser.
  const prepareKey = useRef(crypto.randomUUID())
  const activateKey = useRef(crypto.randomUUID())
  const run = async (action: () => Promise<void>) => {
    if (busy) return
    setBusy(true); setError(null)
    try { await action() } catch (error) { setError(failure(error)) } finally { setBusy(false) }
  }
  return <section aria-label="Move invoice collection to DBN" className="mt-4 border-t border-slate-200 pt-4">
    <h3 className="font-semibold text-slate-900">Collect through DBN</h3>
    <p className="mt-1 text-sm text-slate-600">Review the ETS balance before creating a linked collection copy.</p>
    {!preview && <ControlButton type="button" className="mt-3 whitespace-nowrap rounded-lg border border-slate-300 bg-white px-3 text-slate-800 hover:bg-slate-100 disabled:opacity-50" disabled={busy} onClick={() => void run(async () => {
      const result = await previewSourceCollection(sourceInvoiceId, customerId)
      setPreview(result)
      if (result.existing_handoff) setHandoff(result.existing_handoff)
    })}>{busy ? 'Checking…' : 'Review collection'}</ControlButton>}
    {preview?.eligibility === 'held' && <div role="status" className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
      <p className="font-semibold">Collection needs review</p>
      <ul className="mt-1 list-disc pl-5">{[...new Set(preview.hold_reasons.map(holdLabel))].map(reason => <li key={reason}>{reason}</li>)}</ul>
    </div>}
    {preview?.proposal && preview.eligibility === 'ready' && !handoff && <div className="mt-3 space-y-3">
      <dl className="space-y-1"><div className="flex justify-between gap-4"><dt>ETS invoice</dt><dd>{preview.proposal.source_invoice_number}</dd></div>
        <div className="flex justify-between gap-4 font-semibold"><dt>Balance to collect</dt><dd>${Number(preview.proposal.opening_principal).toFixed(2)}</dd></div></dl>
      <p className="text-xs text-slate-500">Source checked {new Date(preview.proposal.source_observed_at).toLocaleString()}</p>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1 shrink-0" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} disabled={busy} />
        <span>DBN will collect this balance. I will record confirmed DBN payments in ETS and reconcile any payments received there.</span></label>
      <ControlButton type="button" className="whitespace-nowrap rounded-lg border border-slate-300 bg-white px-3 text-slate-800 hover:bg-slate-100 disabled:opacity-50" disabled={busy || !acknowledged} onClick={() => void run(async () => {
        setHandoff(await prepareSourceCollection(preview, prepareKey.current))
      })}>{busy ? 'Preparing…' : 'Prepare collection copy'}</ControlButton>
    </div>}
    {handoff && <>
      <SourceCollectionSummary summary={handoff} />
      {handoff.state === 'prepared' && preview && <ControlButton type="button" className="mt-3 whitespace-nowrap rounded-lg border border-slate-300 bg-white px-3 text-slate-800 hover:bg-slate-100 disabled:opacity-50" disabled={busy} onClick={() => void run(async () => {
        const result = await activateSourceCollection(handoff, preview, activateKey.current)
        setHandoff(result.handoff)
      })}>{busy ? 'Creating…' : 'Create collection invoice'}</ControlButton>}
      {handoff.state === 'prepared' && <p className="mt-2 text-xs text-slate-600">The ETS source record must be checked again after preparation before collection can start.</p>}
      {handoff.native_invoice_id && <a className="mt-3 inline-flex min-h-11 items-center font-semibold text-indigo-700" href={`/api/v1/invoices/${handoff.native_invoice_id}/pdf`} target="_blank" rel="noopener noreferrer">View invoice PDF</a>}
      <p className="mt-2 text-xs text-slate-500">Accounting awaiting external reconciliation. No invoice is sent automatically.</p>
      {handoff.native_invoice_id && <EtsReceiptTasks handoff={handoff} onChange={setHandoff} />}
    </>}
    {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
    {preview && <ControlButton type="button" className="mt-3 whitespace-nowrap rounded-lg border border-slate-300 bg-white px-3 text-slate-800 hover:bg-slate-100 disabled:opacity-50" disabled={busy} onClick={() => void run(async () => {
      // Read back any uncertain activation before changing request identities.
      if (handoff) setHandoff(await fetchSourceCollection(handoff.id))
      const refreshed = await previewSourceCollection(sourceInvoiceId, customerId)
      setPreview(refreshed)
      if (refreshed.existing_handoff) setHandoff(refreshed.existing_handoff)
      prepareKey.current = crypto.randomUUID()
      activateKey.current = crypto.randomUUID()
    })}>Refresh source balance</ControlButton>}
  </section>
}
