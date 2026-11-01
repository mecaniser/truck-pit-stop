import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

export function ImportedBillingTooltip({ children, icon, description, tone }: {
  children: ReactNode; icon: ReactNode; description: string; tone: string
}) {
  const id = useId()
  const trigger = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const timer = useRef<ReturnType<typeof setTimeout>>()
  const pinned = useRef(false)
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState({ left: 0, top: 0 })
  const cancel = () => clearTimeout(timer.current)
  const dismiss = useCallback(() => { clearTimeout(timer.current); pinned.current = false; setOpen(false) }, [])
  const leave = () => { cancel(); if (!pinned.current && !trigger.current?.matches(':focus-visible')) timer.current = setTimeout(() => setOpen(false), 120) }
  useEffect(() => () => clearTimeout(timer.current), [])
  useLayoutEffect(() => {
    if (!open) return
    const place = () => {
      if (!trigger.current || !panel.current) return
      const anchor = trigger.current.getBoundingClientRect()
      const box = panel.current.getBoundingClientRect()
      const above = anchor.top - box.height - 8
      setPosition({ left: Math.max(16, Math.min(anchor.right - box.width, innerWidth - box.width - 16)),
        top: Math.max(16, Math.min(above >= 16 ? above : anchor.bottom + 8, innerHeight - box.height - 16)) })
    }
    const outside = (event: PointerEvent) => {
      if (!trigger.current?.contains(event.target as Node) && !panel.current?.contains(event.target as Node)) dismiss()
    }
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') dismiss() }
    place()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(place)
    if (panel.current) observer?.observe(panel.current)
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', escape)
    }
  }, [open, dismiss])
  return <>
    <button ref={trigger} type="button" aria-label="ETS billing details" aria-description={description}
      aria-describedby={open ? id : undefined} aria-expanded={open} data-severity={tone}
      className="db-imported-billing-indicator inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-600"
      onPointerEnter={event => { if (event.pointerType !== 'touch') { cancel(); setOpen(true) } }}
      onPointerLeave={leave}
      onFocus={event => { if (event.currentTarget.matches(':focus-visible')) { cancel(); setOpen(true) } }}
      onBlur={dismiss}
      onClick={() => { cancel(); if (pinned.current) dismiss(); else { pinned.current = true; setOpen(true) } }}>
      {icon}
    </button>
    {open && createPortal(<div ref={panel} id={id} role="tooltip" aria-label="ETS billing details"
      className="db-imported-billing-tooltip fixed z-[100] w-80 max-w-[calc(100vw-2rem)] overflow-y-auto rounded-xl p-4 text-left text-xs shadow-lg"
      style={{ ...position, maxHeight: 'calc(100dvh - 32px)' }} onPointerEnter={cancel} onPointerLeave={leave}>
      {children}
    </div>, document.body)}
  </>
}
