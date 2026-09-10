import { useEffect, useRef, useState } from 'react'
import { CalendarDays, Check, ChevronLeft, ChevronRight, X } from 'lucide-react'
import { REPORT_PRESETS, formatReportDate, rangeError, validDate, type ReportPreset, type ReportRange, type ResolvedRange } from './reportRange'
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

export default function ReportingDatePicker({ value, resolved, onChange, resolvePreset }: {
  value: ReportRange; resolved?: ResolvedRange; onChange: (range: ReportRange) => void
  resolvePreset: (preset: ReportPreset) => Promise<ResolvedRange>
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
  const previewId = useRef(0)
  const [loading, setLoading] = useState(false)
  const [previewError, setPreviewError] = useState('')
  useEffect(() => () => { previewId.current += 1 }, [])
  const stopPreview = () => { previewId.current += 1; setLoading(false); setPreviewError('') }
  const choosePreset = async (preset: ReportPreset) => {
    const request = ++previewId.current
    setDraft(preset)
    setFrom('')
    setTo('')
    setPickingEnd(false)
    setLoading(true)
    setPreviewError('')
    try {
      const dates = await resolvePreset(preset)
      if (request !== previewId.current) return
      if (rangeError(dates.range_start, dates.range_end)) throw new Error('Invalid report dates')
      setFrom(dates.range_start)
      setTo(dates.range_end)
      setMonth(dates.range_start.slice(0, 7))
      setFocusedDay(dates.range_start)
    } catch {
      if (request === previewId.current) setPreviewError('Could not load this period. Try again or enter custom dates.')
    } finally {
      if (request === previewId.current) setLoading(false)
    }
  }
  useEffect(() => {
    const compact = window.matchMedia('(max-width: 900px)')
    const keepFocusedMonthVisible = () => {
      if (compact.matches && validDate(focusedDay)) setMonth(focusedDay.slice(0, 7))
    }
    keepFocusedMonthVisible()
    compact.addEventListener('change', keepFocusedMonthVisible)
    return () => compact.removeEventListener('change', keepFocusedMonthVisible)
  }, [focusedDay])
  const error = rangeError(from, to)
  const label = value.range === 'custom' ? 'Custom range' : REPORT_PRESETS[value.range]
  const actual = value.range === 'custom' ? { range_start: value.from_date, range_end: value.to_date } : resolved
  const close = () => { stopPreview(); dialog.current?.close(); setOpen(false); trigger.current?.focus() }
  const launch = () => {
    stopPreview()
    setDraft(value.range)
    setFrom(actual?.range_start || '')
    setTo(actual?.range_end || '')
    setMonth((actual?.range_start || iso(new Date())).slice(0, 7))
    setFocusedDay(actual?.range_start || iso(new Date()))
    setPickingEnd(false)
    setOpen(true)
    dialog.current?.showModal()
    if (!actual && value.range !== 'custom') void choosePreset(value.range)
  }
  const chooseDay = (day: string) => {
    stopPreview()
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
          const selected = Boolean(from) && day >= from && day <= (to || from)
          const edge = Boolean(from) && (day === from || day === to)
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
            {Object.entries(REPORT_PRESETS).map(([key, text]) => <button type="button" key={key} aria-pressed={draft === key} onClick={() => void choosePreset(key as ReportPreset)}><span>{text}</span><Check size={16} aria-hidden="true" /></button>)}
            <button type="button" aria-pressed={draft === 'custom'} onClick={() => { stopPreview(); setDraft('custom') }}><span>Custom range</span><Check size={16} aria-hidden="true" /></button>
          </aside>
          <div className="db-report-picker__selection">
            <div className="db-report-picker__fields">
              <label>Start date<input type="date" aria-label="Start date" value={from} onChange={e => { stopPreview(); setFrom(e.target.value); setDraft('custom'); setPickingEnd(false); if (validDate(e.target.value)) { setMonth(e.target.value.slice(0, 7)); setFocusedDay(e.target.value) } }} /></label>
              <label>End date<input type="date" aria-label="End date" value={to} onChange={e => { stopPreview(); setTo(e.target.value); setDraft('custom'); setPickingEnd(false) }} /></label>
            </div>
            <div className="db-report-picker__navigation"><button type="button" aria-label="Previous month" onClick={() => { setMonth(shiftMonth(month, -1)); setFocusedDay(`${shiftMonth(month, -1)}-01`) }}><ChevronLeft size={18} /></button><span>{pickingEnd ? 'Choose an end date' : 'Choose a start date, then an end date'}</span><button type="button" aria-label="Next month" onClick={() => { setMonth(shiftMonth(month, 1)); setFocusedDay(`${shiftMonth(month, 1)}-01`) }}><ChevronRight size={18} /></button></div>
            <div className="db-report-picker__months">{calendar(0)}{calendar(1)}</div>
            <p className="db-report-picker__summary" role="status">{loading ? 'Loading shop-local dates…' : previewError || error || `${draft === 'custom' ? 'Custom range' : REPORT_PRESETS[draft]} · ${formatReportDate(from)} – ${formatReportDate(to)}`}</p>
            {previewError && draft !== 'custom' && <button type="button" onClick={() => void choosePreset(draft)}>Retry period</button>}
          </div>
        </div>
        <footer><span>Applies to date-filtered reports. Inventory is current value.</span><div><button type="button" onClick={close}>Cancel</button><button type="button" className="db-report-picker__apply" disabled={loading || Boolean(error) || Boolean(previewError)} onClick={() => { onChange(draft === 'custom' ? { range: draft, from_date: from, to_date: to } : { range: draft }); close() }}>Apply period</button></div></footer>
      </div>
    </dialog>
  </div>
}
