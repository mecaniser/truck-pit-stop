import { type MouseEvent } from 'react'
import { flushSync } from 'react-dom'

interface PortalViewTransition {
  skipTransition: () => void
  finished: Promise<void>
}
type TransitionDocument = Document & {
  startViewTransition?: (update: () => void) => PortalViewTransition
}

let activeTransition: PortalViewTransition | undefined
let transitionGeneration = 0

/** Animate pointer navigation without delaying keyboard or reduced-motion updates. */
export function transitionPortal(event: MouseEvent<HTMLAnchorElement>, update: () => void) {
  const doc = document as TransitionDocument
  const generation = ++transitionGeneration
  const keyboard = event.detail === 0
  document.documentElement.toggleAttribute('data-portal-keyboard-navigation', keyboard)
  activeTransition?.skipTransition()
  activeTransition = undefined

  if (keyboard || matchMedia('(prefers-reduced-motion: reduce)').matches || !doc.startViewTransition) {
    update()
    return
  }

  const trigger = event.currentTarget.getBoundingClientRect()
  const workspace = document.querySelector('[data-customer-portal] main')?.getBoundingClientRect()
  document.documentElement.style.setProperty('--portal-trigger-x', `${Math.max(0, trigger.left + trigger.width / 2 - (workspace?.left ?? 0))}px`)
  document.documentElement.style.setProperty('--portal-trigger-y', `${Math.max(0, trigger.top + trigger.height / 2 - (workspace?.top ?? 0))}px`)

  const transition = doc.startViewTransition(() => {
    // A skipped transition may still invoke its queued callback. Never let it
    // restore an older destination after a newer pointer or keyboard action.
    if (generation === transitionGeneration) flushSync(update)
  })
  activeTransition = transition
  void transition.finished.catch(() => {}).finally(() => {
    if (activeTransition === transition) activeTransition = undefined
  })
}
