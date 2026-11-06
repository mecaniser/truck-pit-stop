import { useEffect, useRef } from 'react'

/** Animate only the current DOM. Never retain prior-shop rows for an exit. */
export function useShopWorkMotion(view: string) {
  const root = useRef<HTMLElement>(null)
  useEffect(() => {
    const media = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (media?.matches || !root.current || !Element.prototype.animate) return
    // Keyboard navigation stays immediate, including focus restoration.
    if (root.current.querySelector(':focus-visible')) return
    const animations = Array.from(root.current.children)
      .filter(element => !element.matches('header, .db-shop-work-new__toolbar'))
      .filter(element => element.querySelector('.db-overview__row, .db-wip__rows, .db-action-ledger__rows, .db-work-activity__days, [role="status"]') || element.matches('.db-overview, .db-wip, .db-shop-work-new__activity'))
      .map(element => element.animate([
        { opacity: .65, transform: 'translateY(4px)', clipPath: 'inset(0 0 6px 0)' },
        { opacity: 1, transform: 'translateY(0)', clipPath: 'inset(0)' },
      ], { duration: 200, easing: 'cubic-bezier(.23, 1, .32, 1)' }))
    const cancel = () => animations.forEach(animation => animation.cancel())
    media?.addEventListener('change', cancel)
    return () => { cancel(); media?.removeEventListener('change', cancel) }
  }, [view])
  return root
}
