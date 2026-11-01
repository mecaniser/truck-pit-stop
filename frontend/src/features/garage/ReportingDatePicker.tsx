import { ControlButton, ControlInput } from '@/components/ui/Controls'
import { useEffect, useRef, useState } from 'react'
import { CalendarDays, Check, ChevronLeft, ChevronRight, X } from 'lucide-react'
import { REPORT_PRESETS, formatReportDate, rangeError, validDate, type ReportPreset, type ReportRange, type ResolvedRange } from './reportRange'
import { daysOf, isoToday, leadingBlanks, monthLabel as formatMonthLabel, shiftDay, shiftMonth, WEEKDAY_LABELS } from '@/components/calendarGrid'
import './ReportingDatePicker.css'

// Operate: draft a reporting window, inspect its dates, then apply once.
// Existing shop-local API presets remain authoritative; no client-side fiscal assumptions.
// Calendar arithmetic is shared with the single-date picker in
// `@/components/calendarGrid` so both grids agree on month length, week start
// and date-only handling.

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
    setMonth((actual?.range_start || isoToday()).slice(0, 7))
    setFocusedDay(actual?.range_start || isoToday())
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
    const weekday = leadingBlanks(current)
    const monthDays = daysOf(current)
    const days = monthDays.length
    const monthLabel = formatMonthLabel(current)
    return <section className={`db-report-calendar ${offset ? 'db-report-calendar--second' : ''}`} aria-label={monthLabel} key={current}>
      <h3>{monthLabel}</h3>
      <div className="db-report-calendar__week" aria-hidden="true">{WEEKDAY_LABELS.map(d => <span key={d}>{d}</span>)}</div>
      <div className="db-report-calendar__days" role="group" aria-label={`Dates in ${monthLabel}`}>
        {Array.from({ length: weekday }, (_, i) => <span key={`blank-${i}`} />)}
        {monthDays.map((day, i) => {
          const selected = Boolean(from) && day >= from && day <= (to || from)
          const edge = Boolean(from) && (day === from || day === to)
          return <ControlButton controlKind="action" type="button" key={day} data-day={day} aria-label={formatReportDate(day)} aria-pressed={selected}
            className={`${selected ? 'is-in-range' : ''} ${edge ? 'is-endpoint' : ''}`}
            tabIndex={focusedDay === day ? 0 : -1}
            onClick={() => chooseDay(day)} onFocus={() => setFocusedDay(day)} onKeyDown={event => {
              const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key]
              if (step) { event.preventDefault(); focusDay(shiftDay(day, step)) }
              if (event.key === 'Home' || event.key === 'End') { event.preventDefault(); focusDay(event.key === 'Home' ? first : `${current}-${days}`) }
              if (event.key === 'PageUp' || event.key === 'PageDown') { event.preventDefault(); focusDay(`${shiftMonth(current, event.key === 'PageUp' ? -1 : 1)}-01`) }
            }}>{i + 1}</ControlButton>
        })}
      </div>
    </section>
  }
  return <div className="db-report-period">
    <ControlButton controlKind="action" className="db-report-period__trigger" type="button" ref={trigger} onClick={launch} aria-haspopup="dialog" aria-expanded={open}>
      <CalendarDays size={18} aria-hidden="true" /><span><strong>{label}</strong><small>{actual ? `${formatReportDate(actual.range_start)} – ${formatReportDate(actual.range_end)}` : 'Choose reporting dates'}</small></span>
    </ControlButton>
    <dialog className="db-report-picker" ref={dialog} aria-labelledby="report-period-title" onCancel={event => { event.preventDefault(); close() }} onClick={event => { if (event.target === event.currentTarget) close() }}>
      <div className="db-report-picker__content">
        <header><div><h2 id="report-period-title">Reporting period</h2><p>Shop-local dates. Start and end dates are included.</p></div><ControlButton controlKind="icon" type="button" aria-label="Close reporting period" onClick={close}><X size={20} /></ControlButton></header>
        <div className="db-report-picker__body">
          <aside aria-label="Reporting shortcuts">
            <h3>Quick periods</h3>
            {Object.entries(REPORT_PRESETS).map(([key, text]) => <ControlButton controlKind="action" type="button" key={key} aria-pressed={draft === key} onClick={() => void choosePreset(key as ReportPreset)}><span>{text}</span><Check size={16} aria-hidden="true" /></ControlButton>)}
            <ControlButton controlKind="action" type="button" aria-pressed={draft === 'custom'} onClick={() => { stopPreview(); setDraft('custom') }}><span>Custom range</span><Check size={16} aria-hidden="true" /></ControlButton>
          </aside>
          <div className="db-report-picker__selection">
            <div className="db-report-picker__fields">
              <label>Start date<ControlInput type="date" aria-label="Start date" value={from} onChange={e => { stopPreview(); setFrom(e.target.value); setDraft('custom'); setPickingEnd(false); if (validDate(e.target.value)) { setMonth(e.target.value.slice(0, 7)); setFocusedDay(e.target.value) } }} /></label>
              <label>End date<ControlInput type="date" aria-label="End date" value={to} onChange={e => { stopPreview(); setTo(e.target.value); setDraft('custom'); setPickingEnd(false) }} /></label>
            </div>
            <div className="db-report-picker__navigation"><ControlButton controlKind="icon" type="button" aria-label="Previous month" onClick={() => { setMonth(shiftMonth(month, -1)); setFocusedDay(`${shiftMonth(month, -1)}-01`) }}><ChevronLeft size={18} /></ControlButton><span>{pickingEnd ? 'Choose an end date' : 'Choose a start date, then an end date'}</span><ControlButton controlKind="icon" type="button" aria-label="Next month" onClick={() => { setMonth(shiftMonth(month, 1)); setFocusedDay(`${shiftMonth(month, 1)}-01`) }}><ChevronRight size={18} /></ControlButton></div>
            <div className="db-report-picker__months">{calendar(0)}{calendar(1)}</div>
            <p className="db-report-picker__summary" role="status">{loading ? 'Loading shop-local dates…' : previewError || error || `${draft === 'custom' ? 'Custom range' : REPORT_PRESETS[draft]} · ${formatReportDate(from)} – ${formatReportDate(to)}`}</p>
            {previewError && draft !== 'custom' && <ControlButton type="button" onClick={() => void choosePreset(draft)}>Retry period</ControlButton>}
          </div>
        </div>
        <footer><span>Applies to date-filtered reports. Inventory is current value.</span><div><ControlButton type="button" onClick={close}>Cancel</ControlButton><ControlButton type="button" className="db-report-picker__apply" disabled={loading || Boolean(error) || Boolean(previewError)} onClick={() => { onChange(draft === 'custom' ? { range: draft, from_date: from, to_date: to } : { range: draft }); close() }}>Apply period</ControlButton></div></footer>
      </div>
    </dialog>
  </div>
}
