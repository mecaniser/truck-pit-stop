import { type ReactNode, useLayoutEffect, useRef } from 'react'

/** Reveal action outcomes within the dialog's existing scroller, never the page. */
export default function PricingFeedback({ children, revision, role = 'alert' }: { children: ReactNode; revision: unknown; role?: 'alert' | 'status' }) {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const feedback = ref.current
    if (!feedback) return
    const scroller = feedback.closest<HTMLElement>('.db-slide-panel-form__content')
    if (scroller) {
      const viewport = scroller.getBoundingClientRect()
      const bounds = feedback.getBoundingClientRect()
      const inset = 8
      const available = viewport.height - inset * 2
      const delta = bounds.height > available || bounds.top < viewport.top + inset
        ? bounds.top - viewport.top - inset
        : bounds.bottom > viewport.bottom - inset ? bounds.bottom - viewport.bottom + inset : 0
      if (delta) scroller.scrollTop = Math.max(0, scroller.scrollTop + delta)
    }
    feedback.focus({ preventScroll: true })
  }, [revision])
  return <div ref={ref} role={role} tabIndex={-1} className="db-parts-pricing__feedback">{children}</div>
}
