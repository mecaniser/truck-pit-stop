import { useEffect, useRef, useState } from 'react'
import { CalendarDays, ChevronLeft, ChevronRight, X } from 'lucide-react'
import { REPORT_PRESETS, formatReportDate, rangeError, validDate, type ReportRange, type ResolvedRange } from './reportRange'
import './ReportingDatePicker.css'

// Operate: draft a reporting window, inspect its dates, then apply once.
// Existing shop-local API presets remain authoritative; no client-side fiscal assumptions.
function iso(date: Date) { return date.toISOString().slice(0, 10) }
function shiftDay(day: string, amount: number) {
  const date = new Date(`${day}T12:00:00Z`)
  date.setUTCDate(date.getUTCDate() + amount)
  return iso(date)
}
function shiftMonth(month: string, amount: number) {
  const date = new Date(`${month}-01T12:00:00Z`)
  date.setUTCMonth(date.getUTCMonth() + amount)
  return iso(date).slice(0, 7)
}

export default function ReportingDatePicker({ value, resolved, onChange }: {
  value: ReportRange; resolved?: ResolvedRange; onChange: (range: ReportRange) => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<ReportRange['range']>(value.range)
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7))
  const [focusedDay, setFocusedDay] = useState('')
  const [pickingEnd, setPickingEnd] = useState(false)
  useEffect(() => {
    const compact = window.matchMedia('(max-width: 900px)')
    const keepFocusedMonthVisible = () => {
      if (compact.matches && validDate(focusedDay)) setMonth(focusedDay.slice(0, 7))
    }
    keepFocusedMonthVisible()
    compact.addEventListener('change', keepFocusedMonthVisible)
    return () => compact.removeEventListener('change', keepFocusedMonthVisible)
  }, [focusedDay])
  const error = draft === 'custom' ? rangeError(from, to) : null
  const label = value.range === 'custom' ? 'Custom range' : REPORT_PRESETS[value.range]
  const actual = value.range === 'custom' ? { range_start: value.from_date, range_end: value.to_date } : resolved
  const close = () => { dialog.current?.close(); setOpen(false); trigger.current?.focus() }
  const launch = () => {
    setDraft(value.range)
    setFrom(actual?.range_start || '')
    setTo(actual?.range_end || '')
    setMonth((actual?.range_start || iso(new Date())).slice(0, 7))
    setFocusedDay(actual?.range_start || iso(new Date()))
    setPickingEnd(false)
    setOpen(true)
    dialog.current?.showModal()
  }
  const chooseDay = (day: string) => {
    setDraft('custom')
    setFocusedDay(day)
    if (!pickingEnd) { setFrom(day); setTo(''); setPickingEnd(true) }
    else { setFrom(day < from ? day : from); setTo(day < from ? from : day); setPickingEnd(false) }
  }
  const focusDay = (day: string) => {
    setFocusedDay(day)
    if (day.slice(0, 7) !== month) setMonth(day.slice(0, 7))
    requestAnimationFrame(() => dialog.current?.querySelector<HTMLButtonElement>(`[data-day="${day}"]`)?.focus())
  }
  function calendar(offset: number) {
    const current = shiftMonth(month, offset)
    const first = `${current}-01`
    const weekday = (new Date(`${first}T12:00:00Z`).getUTCDay() + 6) % 7
    const days = new Date(new Date(`${shiftMonth(current, 1)}-01T12:00:00Z`).valueOf() - 86400000).getUTCDate()
    const monthLabel = new Date(`${first}T12:00:00Z`).toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' })
    return <section className={`db-report-calendar ${offset ? 'db-report-calendar--second' : ''}`} aria-label={monthLabel} key={current}>
      <h3>{monthLabel}</h3>
      <div className="db-report-calendar__week" aria-hidden="true">{['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].map(d => <span key={d}>{d}</span>)}</div>
      <div className="db-report-calendar__days" role="group" aria-label={`Dates in ${monthLabel}`}>
        {Array.from({ length: weekday }, (_, i) => <span key={`blank-${i}`} />)}
        {Array.from({ length: days }, (_, i) => {
          const day = `${current}-${String(i + 1).padStart(2, '0')}`
          const selected = draft === 'custom' && day >= from && day <= (to || from)
          const edge = draft === 'custom' && (day === from || day === to)
          return <button type="button" key={day} data-day={day} aria-label={formatReportDate(day)} aria-pressed={selected}
            className={`${selected ? 'is-in-range' : ''} ${edge ? 'is-endpoint' : ''}`}
            tabIndex={focusedDay === day ? 0 : -1}
            onClick={() => chooseDay(day)} onFocus={() => setFocusedDay(day)} onKeyDown={event => {
              const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key]
              if (step) { event.preventDefault(); focusDay(shiftDay(day, step)) }
              if (event.key === 'Home' || event.key === 'End') { event.preventDefault(); focusDay(event.key === 'Home' ? first : `${current}-${days}`) }
              if (event.key === 'PageUp' || event.key === 'PageDown') { event.preventDefault(); focusDay(`${shiftMonth(current, event.key === 'PageUp' ? -1 : 1)}-01`) }
            }}>{i + 1}</button>
        })}
      </div>
    </section>
  }
  return <div className="db-report-period">
    <button className="db-report-period__trigger" type="button" ref={trigger} onClick={launch} aria-haspopup="dialog" aria-expanded={open}>
      <CalendarDays size={18} aria-hidden="true" /><span><strong>{label}</strong><small>{actual ? `${formatReportDate(actual.range_start)} – ${formatReportDate(actual.range_end)}` : 'Choose reporting dates'}</small></span>
    </button>
    <dialog className="db-report-picker" ref={dialog} aria-labelledby="report-period-title" onCancel={event => { event.preventDefault(); close() }} onClick={event => { if (event.target === event.currentTarget) close() }}>
      <div className="db-report-picker__content">
        <header><div><h2 id="report-period-title">Reporting period</h2><p>Shop-local dates. Start and end dates are included.</p></div><button type="button" aria-label="Close reporting period" onClick={close}><X size={20} /></button></header>
        <div className="db-report-picker__body">
          <aside aria-label="Reporting shortcuts">
            <h3>Quick periods</h3>
            {Object.entries(REPORT_PRESETS).map(([key, text]) => <button type="button" key={key} aria-pressed={draft === key} onClick={() => { setDraft(key as ReportRange['range']); setFrom(''); setTo(''); setPickingEnd(false) }}>{text}</button>)}
            <button type="button" aria-pressed={draft === 'custom'} onClick={() => setDraft('custom')}>Custom range</button>
          </aside>
          <div className="db-report-picker__selection">
            <div className="db-report-picker__fields">
              <label>Start date<input type="date" aria-label="Start date" value={from} onChange={e => { setFrom(e.target.value); setDraft('custom'); setPickingEnd(false); if (validDate(e.target.value)) { setMonth(e.target.value.slice(0, 7)); setFocusedDay(e.target.value) } }} /></label>
              <label>End date<input type="date" aria-label="End date" value={to} onChange={e => { setTo(e.target.value); setDraft('custom'); setPickingEnd(false) }} /></label>
            </div>
            <div className="db-report-picker__navigation"><button type="button" aria-label="Previous month" onClick={() => { setMonth(shiftMonth(month, -1)); setFocusedDay(`${shiftMonth(month, -1)}-01`) }}><ChevronLeft size={18} /></button><span>{pickingEnd ? 'Choose an end date' : 'Choose a start date, then an end date'}</span><button type="button" aria-label="Next month" onClick={() => { setMonth(shiftMonth(month, 1)); setFocusedDay(`${shiftMonth(month, 1)}-01`) }}><ChevronRight size={18} /></button></div>
            <div className="db-report-picker__months">{calendar(0)}{calendar(1)}</div>
            <p className="db-report-picker__summary" role="status">{draft === 'custom' ? (error || `${formatReportDate(from)} – ${formatReportDate(to)}`) : `${REPORT_PRESETS[draft]} · ${draft.startsWith('this_') ? 'through today in the shop’s timezone' : 'the complete previous calendar period'}`}</p>
          </div>
        </div>
        <footer><span>Applies to date-filtered reports. Inventory is current value.</span><div><button type="button" onClick={close}>Cancel</button><button type="button" className="db-report-picker__apply" disabled={Boolean(error)} onClick={() => { onChange(draft === 'custom' ? { range: draft, from_date: from, to_date: to } : { range: draft }); close() }}>Apply period</button></div></footer>
      </div>
    </dialog>
  </div>
}
