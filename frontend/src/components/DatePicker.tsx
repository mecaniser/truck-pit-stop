import { useEffect, useId, useRef, useState } from 'react'
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react'
import {
  WEEKDAY_LABELS,
  formatDay,
  isoToday,
  leadingBlanks,
  monthLabel,
  monthOf,
  daysOf,
  outOfRange,
  shiftDay,
  shiftMonth,
  validDay,
} from './calendarGrid'
import './DatePicker.css'

export interface DayLoad {
  /** ISO `YYYY-MM-DD`. */
  day: string
  count: number
  /** Unit numbers already booked that day; shown on hover and to screen readers. */
  units?: string[]
  /** Corrective repair work booked that day, kept separate from the PM count so
      a day busy with repairs is not read as a day busy with PMs. */
  booked_count?: number
  booked_units?: string[]
}

export interface DatePickerProps {
  value: string
  onChange: (day: string) => void
  label: string
  /** Earliest selectable day, ISO `YYYY-MM-DD`. */
  min?: string
  /** Latest selectable day — e.g. today, for "PM performed date". */
  max?: string
  id?: string
  disabled?: boolean
  placeholder?: string
  /** Hint rendered under the field; the caller owns the wording. */
  hint?: React.ReactNode
  /** Inline filter rows carry no visible label; the name moves to aria-label
      so the control still announces itself. */
  compact?: boolean
  /** Days that already carry scheduled work, so the calendar can show what is
      booked before another truck is committed to a date. Omit for a plain
      calendar. */
  dayLoad?: DayLoad[]
  /** Called with the `YYYY-MM` now on screen, so the caller can fetch that
      month's load as the user navigates. */
  onMonthChange?: (month: string) => void
  /** Some panels (invoice creation) paint their own light surface inside the
      shell regardless of appearance mode. 'light' pins the control to that
      surface instead of the shell tokens, so it cannot render a dark field on
      a white card. */
  surface?: 'shell' | 'light'
  className?: string
}

/* A single-date control that owns its calendar.
   Native <input type="date"> hands the popup to the browser, which paints it
   from the OS theme: on the dark staff shell that is dark text on a dark
   surface, unreadable, and unreachable by app CSS because the popup lives
   outside the page. This renders the calendar itself so the appearance-mode
   tokens (light / dark / high_contrast) apply to it like any other surface.

   The text field stays a real text input so typing and paste keep working and
   screen readers still announce a date field; the calendar is an addition to
   it, not a replacement. */
export default function DatePicker({
  value,
  onChange,
  label,
  min,
  max,
  id,
  disabled,
  placeholder = 'YYYY-MM-DD',
  hint,
  dayLoad,
  onMonthChange,
  compact,
  surface = 'shell',
  className,
}: DatePickerProps) {
  const generatedId = useId()
  const fieldId = id || generatedId
  const dialogId = `${fieldId}-calendar`
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const [month, setMonth] = useState(() => monthOf(validDay(value) ? value : isoToday()))
  const [focusedDay, setFocusedDay] = useState(() => (validDay(value) ? value : isoToday()))

  // Follow the value when it changes underneath us — the PM modal recomputes
  // the due date from the odometer target while this control is mounted.
  useEffect(() => {
    if (!validDay(value)) return
    setMonth(monthOf(value))
    setFocusedDay(value)
  }, [value])

  const close = (restoreFocus = true) => {
    setOpen(false)
    if (restoreFocus) trigger.current?.focus()
  }

  // A calendar is a transient surface: it closes on outside pointer and on
  // focus leaving, so it cannot strand itself over the form beneath it.
  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    const onFocusIn = (event: FocusEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('focusin', onFocusIn)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('focusin', onFocusIn)
    }
  }, [open])

  const focusDay = (day: string) => {
    setFocusedDay(day)
    if (monthOf(day) !== month) setMonth(monthOf(day))
    requestAnimationFrame(() => {
      root.current?.querySelector<HTMLButtonElement>(`[data-day="${day}"]`)?.focus()
    })
  }

  const choose = (day: string) => {
    if (outOfRange(day, min, max)) return
    onChange(day)
    close()
  }

  // Index the load once per render so each day cell is a map lookup, not a scan.
  const loadByDay = new Map(
    (dayLoad || [])
      .filter(d => d.count > 0 || (d.booked_count || 0) > 0)
      .map(d => [d.day, d]),
  )

  // Tell the caller which month is on screen so it can fetch that month's load.
  const goToMonth = (next: string) => {
    setMonth(next)
    onMonthChange?.(next)
  }

  const selected = validDay(value) ? value : ''
  const triggerLabel = selected ? `Choose date — ${formatDay(selected)}` : 'Choose date'

  return (
    <div
      className={[
        'db-datepicker',
        compact ? 'db-datepicker--compact' : '',
        surface === 'light' ? 'db-datepicker--light' : '',
        className || '',
      ].filter(Boolean).join(' ')}
      ref={root}
      // Escape is handled for the whole control, not just the calendar: focus
      // is usually still on the trigger that opened it, which sits outside the
      // popup, so a handler on the popup alone would never see the key.
      onKeyDown={(event) => {
        if (event.key === 'Escape' && open) {
          event.preventDefault()
          close()
        }
      }}
    >
      {compact
        ? null
        : <label className="db-datepicker__label" htmlFor={fieldId}>{label}</label>}
      <div className="db-datepicker__control">
        <input
          id={fieldId}
          className="db-datepicker__input"
          aria-label={compact ? label : undefined}
          value={value}
          disabled={disabled}
          placeholder={placeholder}
          inputMode="numeric"
          autoComplete="off"
          onChange={(event) => onChange(event.target.value)}
        />
        <button
          type="button"
          ref={trigger}
          className="db-datepicker__trigger"
          aria-label={triggerLabel}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls={open ? dialogId : undefined}
          disabled={disabled}
          onClick={() => {
            const base = validDay(value) ? value : isoToday()
            setMonth(monthOf(base))
            setFocusedDay(base)
            setOpen((wasOpen) => !wasOpen)
          }}
        >
          <CalendarDays size={16} aria-hidden="true" />
        </button>
      </div>
      {hint ? <p className="db-datepicker__hint">{hint}</p> : null}
      {open && (
        <div
          className="db-datepicker__calendar"
          id={dialogId}
          role="dialog"
          aria-label={label}
          aria-modal="false"
        >
          <div className="db-datepicker__nav">
            <button
              type="button"
              aria-label="Previous month"
              onClick={() => goToMonth(shiftMonth(month, -1))}
            >
              <ChevronLeft size={16} aria-hidden="true" />
            </button>
            <h2>{monthLabel(month)}</h2>
            <button
              type="button"
              aria-label="Next month"
              onClick={() => goToMonth(shiftMonth(month, 1))}
            >
              <ChevronRight size={16} aria-hidden="true" />
            </button>
          </div>
          <div className="db-datepicker__week" aria-hidden="true">
            {WEEKDAY_LABELS.map((day) => <span key={day}>{day}</span>)}
          </div>
          <div className="db-datepicker__days" role="group" aria-label={`Dates in ${monthLabel(month)}`}>
            {Array.from({ length: leadingBlanks(month) }, (_, i) => <span key={`blank-${i}`} />)}
            {daysOf(month).map((day) => {
              const unavailable = outOfRange(day, min, max)
              const booked = loadByDay.get(day)
              // The badge shows total work on the day; the description keeps PM
              // and repair load apart, because a manager avoiding a busy day
              // still needs to know what makes it busy.
              const repairCount = booked?.booked_count || 0
              const total = (booked?.count || 0) + repairCount
              const parts: string[] = []
              if (booked?.count) {
                parts.push(`${booked.count} PM${booked.count === 1 ? '' : 's'} scheduled${
                  booked.units?.length ? `: ${booked.units.join(', ')}` : ''}`)
              }
              if (repairCount) {
                parts.push(`${repairCount} repair job${repairCount === 1 ? '' : 's'} booked${
                  booked?.booked_units?.length ? `: ${booked.booked_units.join(', ')}` : ''}`)
              }
              const bookedNames = parts.join(' · ')
              return (
                <button
                  type="button"
                  key={day}
                  data-day={day}
                  title={bookedNames || undefined}
                  aria-label={booked ? `${formatDay(day)} — ${bookedNames}` : formatDay(day)}
                  aria-pressed={day === selected}
                  aria-current={day === isoToday() ? 'date' : undefined}
                  disabled={unavailable}
                  className={[
                    day === selected ? 'is-selected' : '',
                    day === isoToday() ? 'is-today' : '',
                    booked ? 'has-load' : '',
                  ].filter(Boolean).join(' ')}
                  tabIndex={focusedDay === day ? 0 : -1}
                  onClick={() => choose(day)}
                  onFocus={() => setFocusedDay(day)}
                  onKeyDown={(event) => {
                    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key]
                    if (step) {
                      event.preventDefault()
                      focusDay(shiftDay(day, step))
                    }
                    if (event.key === 'Home' || event.key === 'End') {
                      event.preventDefault()
                      const days = daysOf(month)
                      focusDay(event.key === 'Home' ? days[0] : days[days.length - 1])
                    }
                    if (event.key === 'PageUp' || event.key === 'PageDown') {
                      event.preventDefault()
                      focusDay(`${shiftMonth(month, event.key === 'PageUp' ? -1 : 1)}-01`)
                    }
                  }}
                >
                  {Number(day.slice(8))}
                  {booked && (
                    <span className="db-datepicker__load" aria-hidden="true">{total}</span>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
