import { useLayoutEffect, useRef, type ReactNode } from 'react'

const ROW_SELECTOR = '.cp-task,.cp-activity,.cp-service,.cp-history-record,.cp-invoice-row,section > [class*="space-y-"] > a,section > [class*="space-y-"] > div.relative'
const DETAIL_SELECTOR = 'button,a,svg,section,[role=region],[role=dialog],[role=tabpanel],.cp-panel'

export default function PortalMotion({ children }: { children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null)
  const keyboard = useRef(false)

  useLayoutEffect(() => {
    const element = root.current
    if (!element) return
    const reduced = matchMedia('(prefers-reduced-motion: reduce)')
    const running = new Set<Animation>()
    const animate = (node: Element, index: number) => {
      if (reduced.matches || keyboard.current || document.documentElement.hasAttribute('data-portal-keyboard-navigation') || typeof node.animate !== 'function') return
      const animation = node.animate([
        { opacity: 0, transform: 'translateY(5px)', clipPath: 'inset(0 0 8% 0)' },
        { opacity: 1, transform: 'translateY(0)', clipPath: 'inset(0)' },
      ], { duration: 200, delay: Math.min(index, 3) * 30, easing: 'cubic-bezier(0.23, 1, 0.32, 1)' })
      running.add(animation)
      void animation.finished.then(() => running.delete(animation), () => running.delete(animation))
    }
    element.querySelectorAll(ROW_SELECTOR).forEach(animate)
    const observer = new MutationObserver(records => {
      records.flatMap(record => Array.from(record.addedNodes))
        .filter((node): node is Element => node instanceof Element)
        .forEach((node, index) => {
          if (node.matches(DETAIL_SELECTOR)) animate(node, index)
        })
    })
    observer.observe(element, { childList: true, subtree: true })
    const cancel = () => { if (reduced.matches) running.forEach(animation => animation.cancel()) }
    reduced.addEventListener('change', cancel)
    return () => {
      observer.disconnect()
      reduced.removeEventListener('change', cancel)
      running.forEach(animation => animation.cancel())
    }
  }, [])

  return <div
    ref={root}
    className="portal-motion"
    onKeyDownCapture={() => {
      keyboard.current = true
      root.current?.getAnimations?.({ subtree: true }).forEach(animation => animation.cancel())
    }}
    onPointerDownCapture={() => {
      keyboard.current = false
      document.documentElement.removeAttribute('data-portal-keyboard-navigation')
    }}
  >{children}</div>
}
