import { useEffect, useRef } from 'react'
import { Dialog } from '@headlessui/react'
import { useQuery } from '@tanstack/react-query'
import { loadRepairOrderEntry, type RepairOrderEntry } from './repairOrderEntry'

/** Loading/error gate only. Opening it never creates a customer, truck or order. */
export default function RepairOrderEntryGate({ customerId, vehicleId, onReady, onCancel }: {
  customerId: string; vehicleId: string | null; onReady: (entry: RepairOrderEntry) => void; onCancel: () => void
}) {
  const delivered = useRef(false)
  const query = useQuery({
    queryKey: ['repair-order-entry', customerId, vehicleId],
    queryFn: ({ signal }) => loadRepairOrderEntry(customerId, vehicleId, signal),
    retry: false,
    staleTime: 0,
    gcTime: 0,
  })
  useEffect(() => {
    if (query.data && !query.isFetching && !query.isError && !delivered.current) {
      delivered.current = true
      onReady(query.data)
    }
  }, [onReady, query.data, query.isFetching, query.isError])
  return <Dialog open onClose={onCancel} className="relative z-[60]">
    <div className="fixed inset-0 bg-black/60" aria-hidden="true" />
    <div className="fixed inset-0 flex items-center justify-center p-4">
      <Dialog.Panel className="w-full max-w-md rounded-xl bg-white p-5 text-slate-900 shadow-xl">
        <Dialog.Title className="text-lg font-semibold">New repair order</Dialog.Title>
        {query.isError ? <p role="alert" className="my-4 text-sm text-red-800">Could not load this customer and truck. They may no longer be available. Retry or return to the record.</p>
          : <p role="status" className="my-4 text-sm">Loading customer and truck…</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" onClick={onCancel} className="min-h-11 rounded-lg border px-4">Cancel</button>
          {query.isError && <button type="button" onClick={() => void query.refetch()} className="min-h-11 rounded-lg bg-slate-900 px-4 text-white">Retry</button>}
        </div>
      </Dialog.Panel>
    </div>
  </Dialog>
}
