import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import { ChevronUp, Play, X } from 'lucide-react'
import { Spinner } from '@/components/ui'

interface StartWorkActionProps {
  technicians: { mechanic_id: string; mechanic_name: string; load: number }[]
  onAssign?: (mechanicId: string) => void
  onStartWithoutTechnician?: () => void
  assignmentPending: boolean
  startPending: boolean
}

export default function StartWorkAction({
  technicians, onAssign, onStartWithoutTechnician, assignmentPending, startPending,
}: StartWorkActionProps) {
  const pending = assignmentPending || startPending

  return (
    <Popover className="relative">
      {({ close }) => (
        <>
          <PopoverButton
            disabled={pending}
            aria-busy={pending}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-orange-600 px-4 text-sm font-bold text-white hover:bg-orange-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600 disabled:opacity-60"
          >
            {pending ? <span aria-hidden="true"><Spinner size="xs" /></span> : <Play className="h-4 w-4" aria-hidden="true" />}
            {startPending ? 'Starting…' : assignmentPending ? 'Assigning…' : 'Start work…'}
            {!pending && <ChevronUp className="h-4 w-4" aria-hidden="true" />}
          </PopoverButton>
          <PopoverPanel
            anchor="top end"
            focus
            aria-label="Start work options"
            className="z-[100] w-80 max-w-[calc(100vw-2rem)] overflow-y-auto rounded-xl bg-white p-4 text-gray-900 shadow-lg ring-1 ring-gray-200 [--anchor-gap:8px] [--anchor-padding:16px]"
          >
            <div className="mb-3 flex items-center justify-between gap-2">
              <h3 className="text-base font-bold">Start work</h3>
              <button type="button" onClick={() => close()} aria-label="Close start work options" className="-mr-2 inline-flex h-11 w-11 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100">
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            {onAssign && (
              <div>
                <p className="text-sm font-semibold">Assign technician</p>
                <p className="mt-1 text-xs text-gray-600">They’ll be notified and can start work.</p>
                {technicians.length > 0 ? (
                  <div className="mt-2 max-h-48 overflow-y-auto">
                    {technicians.map((tech) => (
                      <button
                        key={tech.mechanic_id}
                        type="button"
                        disabled={pending}
                        onClick={() => { onAssign(tech.mechanic_id); close() }}
                        className="flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-2 text-left text-sm font-semibold hover:bg-orange-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-600 disabled:opacity-60"
                      >
                        <span className="min-w-0 break-words">{tech.mechanic_name}</span>
                        <span className="shrink-0 text-xs font-normal text-gray-600">{tech.load.toFixed(0)}% load</span>
                      </button>
                    ))}
                  </div>
                ) : <p className="mt-2 text-sm text-gray-600">No technicians available to assign.</p>}
              </div>
            )}
            {onStartWithoutTechnician && (
              <div className={onAssign ? 'mt-3 border-t border-gray-200 pt-3' : ''}>
                <button
                  type="button"
                  disabled={pending}
                  onClick={() => { onStartWithoutTechnician(); close() }}
                  className="flex min-h-11 w-full items-center gap-2 rounded-lg bg-orange-50 px-3 py-2 text-left text-sm font-semibold text-orange-800 hover:bg-orange-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-600 disabled:opacity-60"
                >
                  <Play className="h-4 w-4 shrink-0" aria-hidden="true" />
                  Start without a technician
                </button>
                <p className="mt-2 text-xs text-gray-600">Start work now. You can assign someone later.</p>
              </div>
            )}
          </PopoverPanel>
        </>
      )}
    </Popover>
  )
}
