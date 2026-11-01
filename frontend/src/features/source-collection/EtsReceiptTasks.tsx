import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ControlButton, ControlInput } from '@/components/ui/Controls'
import { acknowledgeEtsReceiptTask, claimEtsReceiptTask, fetchEtsReceiptTasks, fetchSourceCollection, reconcileSourceCollection } from './api'
import type { EtsReceiptTask, SourceCollectionSummary } from './types'

function ReceiptTask({ task, handoff, onChange }: { task: EtsReceiptTask; handoff: SourceCollectionSummary; onChange: () => Promise<void> }) {
  const [allocationIds, setAllocationIds] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const claimKey = useRef(crypto.randomUUID())
  const ackKey = useRef(crypto.randomUUID())
  const verified = task.state === 'verified'
  const claimExpired = Boolean(task.claim_expires_at && Date.parse(task.claim_expires_at) <= Date.now())
  const ids = allocationIds.split(/[\s,]+/).filter(Boolean)
  const perform = async (action: () => Promise<unknown>) => {
    setBusy(true); setError(false)
    try { await action(); await onChange() } catch { setError(true) } finally { setBusy(false) }
  }
  return <li className="rounded-lg border border-slate-200 p-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><strong>${Number(task.principal_amount).toFixed(2)} to record in ETS</strong><span>{task.state.replace(/_/g, ' ')}</span></div>
    <p className="mt-1 text-xs text-slate-500">DBN receipt {task.payment_id} · {new Date(task.effective_at).toLocaleString()}</p>
    {!verified && <>
      <p className="mt-2 text-xs">Record only this principal against ETS invoice {handoff.source_invoice_number}. DBN fees and unapplied money are excluded.</p>
      <p className="mt-2 text-xs">Include this receipt reference in the ETS payment notes:</p>
      <code className="mt-1 block break-all rounded bg-slate-100 p-2 text-xs">DBN-RECEIPT:{task.payment_id}</code>
      {(task.state === 'pending_manual' || claimExpired) && <ControlButton type="button" disabled={busy} className="mt-2 whitespace-nowrap rounded-lg border border-slate-300 bg-white px-3 text-slate-800 hover:bg-slate-100 disabled:opacity-50" onClick={() => void perform(() => claimEtsReceiptTask(task, claimKey.current))}>{claimExpired ? 'Reclaim ETS update' : 'Claim ETS update'}</ControlButton>}
      {['claimed', 'awaiting_verification'].includes(task.state) && <div className="mt-3 space-y-2">
        <label className="block text-xs">ETS allocation IDs from the recorded receipt
          <ControlInput value={allocationIds} onChange={event => setAllocationIds(event.target.value)} className="mt-1 w-full border border-slate-300 text-sm" placeholder="Allocation IDs, separated by commas" disabled={busy} />
        </label>
        <p className="text-xs text-slate-500">After the ETS record is refreshed, DBN verifies these IDs against its source evidence. Submitting IDs does not record another payment.</p>
        <ControlButton type="button" disabled={busy || claimExpired || !ids.length} className="whitespace-nowrap rounded-lg border border-slate-300 bg-white px-3 text-slate-800 hover:bg-slate-100 disabled:opacity-50" onClick={() => void perform(async () => {
          const fresh = await fetchSourceCollection(handoff.id)
          await acknowledgeEtsReceiptTask(task, fresh, ids, ackKey.current)
        })}>Verify ETS receipt</ControlButton>
      </div>}
    </>}
    {error && <p role="alert" className="mt-2 text-xs text-red-700">Update not verified. Refresh the task and source evidence before continuing. Do not enter the payment again in ETS.</p>}
  </li>
}

export default function EtsReceiptTasks({ handoff, onChange }: { handoff: SourceCollectionSummary; onChange: (summary: SourceCollectionSummary) => void }) {
  const [skip, setSkip] = useState(0)
  const queryClient = useQueryClient()
  const queryKey = ['ets-receipt-tasks', handoff.id, skip]
  const tasks = useQuery({ queryKey, queryFn: () => fetchEtsReceiptTasks(handoff.id, skip), retry: false })
  const [reconciling, setReconciling] = useState(false)
  const [error, setError] = useState(false)
  const reconcileKey = useRef(crypto.randomUUID())
  const refresh = async () => {
    onChange(await fetchSourceCollection(handoff.id))
    await queryClient.invalidateQueries({ queryKey: ['ets-receipt-tasks', handoff.id] })
  }
  return <section className="mt-4 space-y-3" aria-label="ETS payment reconciliation">
    <h4 className="font-semibold">ETS payment reconciliation</h4>
    {tasks.isLoading ? <p>Loading receipt updates…</p> : tasks.isError ? <p role="alert">Receipt updates unavailable. Refresh to retry.</p> : tasks.data && <>
      {!tasks.data.total && <p className="text-xs text-slate-600">No DBN receipt needs an ETS update.</p>}
      <ul className="space-y-2">{tasks.data.items.map(task => <ReceiptTask key={`${task.id}:${task.version}`} task={task} handoff={handoff} onChange={refresh} />)}</ul>
      {tasks.data.total > tasks.data.limit && <div className="flex items-center justify-between gap-2">
        <ControlButton type="button" disabled={skip === 0} onClick={() => setSkip(value => Math.max(0, value - 20))}>Previous</ControlButton>
        <span className="text-xs">{skip + 1}–{skip + tasks.data.items.length} of {tasks.data.total}</span>
        <ControlButton type="button" disabled={skip + 20 >= tasks.data.total} onClick={() => setSkip(value => value + 20)}>Next</ControlButton>
      </div>}
    </>}
    <div className="flex flex-wrap gap-2">
      <ControlButton type="button" disabled={reconciling} className="whitespace-nowrap rounded-lg border border-slate-300 bg-white px-3 text-slate-800 hover:bg-slate-100 disabled:opacity-50" onClick={() => void refresh().catch(() => setError(true))}>Refresh receipts</ControlButton>
      <ControlButton type="button" disabled={reconciling} className="whitespace-nowrap rounded-lg border border-slate-300 bg-white px-3 text-slate-800 hover:bg-slate-100 disabled:opacity-50" onClick={async () => {
        setReconciling(true); setError(false)
        try {
          const fresh = await fetchSourceCollection(handoff.id)
          const result = await reconcileSourceCollection(fresh, reconcileKey.current)
          onChange(result.handoff)
          setError(result.conflict)
          await refresh()
          reconcileKey.current = crypto.randomUUID()
        } catch {
          setError(true)
          try { await refresh() } catch { /* Keep the unverified-result warning visible. */ }
        } finally { setReconciling(false) }
      }}>Reconcile ETS payments</ControlButton>
    </div>
    <p className="text-xs text-slate-500">Reconciliation applies verified ETS receipts once. It never charges the customer.</p>
    {error && <p role="alert" className="text-xs text-red-700">Reconciliation needs review. No verified result is available; refresh before retrying.</p>}
  </section>
}
