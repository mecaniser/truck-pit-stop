import { ControlButton } from '@/components/ui/Controls'
import PlatformSelect from '@/components/PlatformSelect'
import { useState } from 'react'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { invalidateOperationExecution } from '@/features/operation-execution/queries'
import { errorDetail } from '@/features/service-checklists/queries'
import { holdReasonLabel } from './holdReason'
import { staffHoldResultSchema, type WorkHoldOrder } from './staffHold'

/** Mounted when opened so the raw server version and user's intent stay fixed. */
export default function StaffHoldDialog({ order, onClose, onUpdated }: {
  order: WorkHoldOrder; onClose: () => void; onUpdated?: () => void
}) {
  const client = useQueryClient()
  const tenantId = useAuthStore(state => state.user?.tenant_id)
  const [intent] = useState(() => ({ version: order.updated_at, release: !!order.hold_reason, reason: order.hold_reason }))
  const [reason, setReason] = useState('waiting_for_parts')
  const [customReason, setCustomReason] = useState('')
  const [error, setError] = useState('')
  const stale = intent.version !== order.updated_at || intent.release !== !!order.hold_reason || order.status !== 'in_progress'
  const value = reason === 'custom' ? customReason.trim() : reason
  const refresh = async () => {
    if (tenantId) await invalidateOperationExecution(client, tenantId, order.id)
    onUpdated?.()
  }
  const mutation = useMutation({
    mutationFn: async () => {
      const response = await api.post(`/repair-orders/${order.id}/${intent.release ? 'staff-release-hold' : 'staff-hold'}`, {
        expected_updated_at: intent.version,
        ...(!intent.release ? { reason: value } : {}),
      })
      const result = staffHoldResultSchema.parse(response.data)
      if (result.id !== order.id || result.updated_at === intent.version
        || (intent.release ? result.hold_reason !== null || result.held_at !== null || result.stopped_sessions_count !== 0
          : result.hold_reason !== value || !result.held_at)) throw new Error('Unconfirmed hold response')
      return result
    },
    onSuccess: async result => {
      await refresh()
      toast.success(intent.release ? 'Hold released. Technicians can start work.'
        : `Order on hold.${result.stopped_sessions_count ? ` ${result.stopped_sessions_count} timer${result.stopped_sessions_count === 1 ? '' : 's'} stopped.` : ''}`)
      onClose()
    },
    onError: async failure => {
      setError(errorDetail(failure, 'Change could not be confirmed. Review the refreshed order before trying again.'))
      // A lost response may still have committed. Refresh; never replay automatically.
      await refresh()
    },
  })
  const dismiss = () => { if (!mutation.isPending) onClose() }
  return <Dialog open onClose={dismiss} className="fixed inset-0 z-[140]">
    <div className="fixed inset-0 bg-black/50" aria-hidden="true" />
    <div className="fixed inset-x-0 flex items-center justify-center p-3" style={{ top: 'var(--db-workspace-viewport-top, 0px)', height: 'var(--db-workspace-viewport-height, 100dvh)' }}>
      <DialogPanel className="flex max-h-full w-full max-w-md flex-col overflow-hidden rounded-xl bg-white text-gray-900 shadow-xl">
        <div className="flex shrink-0 items-center justify-between gap-2 border-b px-4 py-2">
          <DialogTitle className="text-base font-semibold">{intent.release ? 'Release hold' : 'Put order on hold'}</DialogTitle>
          <ControlButton controlKind="icon" type="button" aria-label="Close hold dialog" disabled={mutation.isPending} onClick={dismiss} className="inline-flex  w-11 shrink-0 items-center justify-center rounded-lg hover:bg-gray-100 disabled:opacity-50"><X size={20} /></ControlButton>
        </div>
        <form className="flex min-h-0 flex-col" onSubmit={event => { event.preventDefault(); if (!stale && !mutation.isPending && (intent.release || value.length > 0 && value.length <= 100)) { setError(''); mutation.mutate() } }}>
          <div className="min-h-0 space-y-3 overflow-y-auto px-4 py-3">
            <p className="break-words text-sm font-semibold">#{order.order_number}</p>
            {intent.release ? <>
              <p className="break-words text-sm">{holdReasonLabel(intent.reason ?? '')}</p>
              <p className="text-sm text-gray-600">Technicians can start work again. No timers will start automatically.</p>
            </> : <>
              <p className="text-sm text-gray-600">Stops all active timers on this order. Assignments and completed work stay in place.</p>
              <label className="block text-sm font-medium">Hold reason
                <PlatformSelect autoFocus value={reason} disabled={mutation.isPending} onChange={event => setReason(event.target.value)} className="mt-1 min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 text-sm">
                  <option value="waiting_for_parts">Waiting for parts</option>
                  <option value="waiting_for_customer_approval">Waiting for customer approval</option>
                  <option value="need_more_info">More information needed</option>
                  <option value="custom">Other reason</option>
                </PlatformSelect>
              </label>
              {reason === 'custom' && <label className="block text-sm font-medium">Other hold reason
                <textarea value={customReason} disabled={mutation.isPending} required maxLength={100} rows={3} onChange={event => setCustomReason(event.target.value)} className="mt-1 w-full resize-none rounded-lg border border-gray-300 px-3 py-2 text-base" />
                <span className="text-xs text-gray-500">{customReason.length}/100 · Staff only</span>
              </label>}
            </>}
            {error && <p role="alert" className="break-words text-sm text-red-700">{error}</p>}
            {stale && <p role="alert" className="text-sm text-amber-800">This order changed. Close this dialog and review its current state before continuing.</p>}
          </div>
          <div className="flex shrink-0 flex-wrap justify-end gap-2 border-t px-4 py-2">
            <ControlButton type="button" disabled={mutation.isPending} onClick={dismiss} className=" whitespace-nowrap rounded-lg border border-gray-300 px-4 text-sm font-semibold disabled:opacity-50">Cancel</ControlButton>
            <ControlButton type="submit" disabled={mutation.isPending || stale || !intent.release && (!value || value.length > 100)} className=" whitespace-nowrap rounded-lg bg-orange-600 px-4 text-sm font-semibold text-white disabled:opacity-50">{mutation.isPending ? 'Saving…' : intent.release ? 'Release hold' : 'Put on hold'}</ControlButton>
          </div>
        </form>
      </DialogPanel>
    </div>
  </Dialog>
}
