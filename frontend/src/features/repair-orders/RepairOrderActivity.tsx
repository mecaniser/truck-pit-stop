import { ControlButton, ControlInput } from '@/components/ui/Controls'
import { useState } from 'react'
import { ChevronDown, Search, X } from 'lucide-react'
import type { PriceBuilderHistoryEvent } from './PriceBuilderPanel'

type Props = {
  events: PriceBuilderHistoryEvent[]
  initiallyOpen?: boolean
  loading?: boolean
  error?: boolean
  onOpen?: () => void
  onRetry?: () => void
}

export default function RepairOrderActivity({ events, initiallyOpen = false, loading, error, onOpen, onRetry }: Props) {
  const [open, setOpen] = useState(initiallyOpen)
  const [search, setSearch] = useState('')
  const [limit, setLimit] = useState(10)
  const terms = search.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  const matches = [...events].sort((a, b) => Date.parse(b.at) - Date.parse(a.at)).filter(event => {
    const text = `${event.label} ${event.detail ?? ''} ${event.actor ?? ''}`.toLocaleLowerCase()
    return terms.every(term => text.includes(term))
  })
  const visible = matches.slice(0, limit)
  const clearSearch = () => { setSearch(''); setLimit(10) }

  return (
    <section aria-label="Repair order activity" className="min-w-0 py-2">
      <ControlButton controlKind="content"
        type="button"
        aria-expanded={open}
        onClick={() => { if (!open) onOpen?.(); setOpen(!open) }}
        className="flex min-h-11 w-full items-center justify-between gap-2 text-left sm:min-h-9"
      >
        <span className="text-sm font-semibold text-gray-900">Repair order history</span>
        <ChevronDown className={`h-4 w-4 shrink-0 text-gray-500 transition-transform ${open ? '' : '-rotate-90'}`} />
      </ControlButton>
      {open && <>
        <div className="relative mb-2">
          <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-gray-400 sm:top-2.5" />
          <ControlInput
            type="search"
            aria-label="Search repair order history"
            placeholder="Search work, action, or person"
            value={search}
            onChange={event => { setSearch(event.target.value); setLimit(10) }}
            className=" w-full min-w-0 rounded-lg border border-gray-300 bg-white  pl-9 pr-11 text-base text-gray-900  sm:text-sm [&::-webkit-search-cancel-button]:appearance-none"
          />
          {search && <ControlButton controlKind="icon" type="button" aria-label="Clear history search" onClick={clearSearch} className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-gray-500"><X className="h-4 w-4" /></ControlButton>}
        </div>
        {loading && <p role="status" className="py-2 text-sm text-gray-500">Loading history…</p>}
        {error && <div role="alert" className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <span>Some history could not be loaded. Events may be missing.</span>
          <ControlButton type="button" disabled={loading} onClick={onRetry} className=" whitespace-nowrap font-semibold underline disabled:opacity-50 ">Retry history</ControlButton>
        </div>}
        <p role="status" className="pb-2 text-xs text-gray-500">
          {terms.length ? `${matches.length} matching ${matches.length === 1 ? 'event' : 'events'}` : `${events.length} recorded ${events.length === 1 ? 'event' : 'events'}`}
        </p>
        {visible.length > 0 ? <ol aria-label="History events" className="divide-y divide-gray-100">
          {visible.map(event => {
            const date = new Date(event.at)
            const valid = !Number.isNaN(date.getTime())
            return <li key={event.id} className="min-w-0 py-2.5">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                <p className="min-w-0 break-words text-sm font-semibold text-gray-900 [overflow-wrap:anywhere]">{event.label}</p>
                <time dateTime={valid ? event.at : undefined} title={valid ? date.toLocaleString() : undefined} className="shrink-0 text-xs text-gray-500">
                  {valid ? date.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }) : 'Time unavailable'}
                </time>
              </div>
              {event.detail && <p className="mt-0.5 break-words text-sm text-gray-700 [overflow-wrap:anywhere]">{event.detail}</p>}
              {event.actor && <p className="mt-0.5 break-words text-xs text-gray-500 [overflow-wrap:anywhere]">By {event.actor}</p>}
            </li>
          })}
        </ol> : !loading && !error && <div className="py-3 text-sm text-gray-500">
          <p>{terms.length ? 'No events match your search.' : 'No repair order history has been recorded yet.'}</p>
          {terms.length > 0 && <ControlButton type="button" onClick={clearSearch} className=" font-semibold text-orange-700 ">Clear search</ControlButton>}
        </div>}
        {matches.length > 10 && <div className="flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-2">
          <p className="text-xs text-gray-500">Showing {visible.length} of {matches.length} events</p>
          <div className="flex flex-wrap gap-2">
            {limit > 10 && <ControlButton type="button" onClick={() => setLimit(10)} className=" whitespace-nowrap rounded-lg border border-gray-200 px-3 text-sm ">Show less</ControlButton>}
            {matches.length > limit && <ControlButton type="button" onClick={() => setLimit(limit + 10)} className=" whitespace-nowrap rounded-lg bg-orange-50 px-3 text-sm font-semibold text-orange-700 ">Show {Math.min(10, matches.length - limit)} older {matches.length - limit === 1 ? 'event' : 'events'}</ControlButton>}
          </div>
        </div>}
      </>}
    </section>
  )
}
