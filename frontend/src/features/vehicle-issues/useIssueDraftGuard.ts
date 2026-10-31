import { useContext, useEffect } from 'react'
import { UNSAFE_NavigationContext } from 'react-router-dom'

/** BrowserRouter has no data-router blocker. Guard its navigator plus native
 * back/forward while the focus-trapped editor owns an unsaved draft. */
export function useIssueDraftGuard(dirty: boolean, requestLeave: (continueNavigation: () => void) => void) {
  const { navigator } = useContext(UNSAFE_NavigationContext)
  useEffect(() => {
    if (!dirty) return
    const push = navigator.push.bind(navigator)
    const replace = navigator.replace.bind(navigator)
    const go = navigator.go.bind(navigator)
    const originalPush = navigator.push
    const originalReplace = navigator.replace
    const originalGo = navigator.go
    const guardedPush: typeof navigator.push = (...args) => requestLeave(() => push(...args))
    const guardedReplace: typeof navigator.replace = (...args) => requestLeave(() => replace(...args))
    const guardedGo: typeof navigator.go = (...args) => requestLeave(() => go(...args))
    navigator.push = guardedPush
    navigator.replace = guardedReplace
    navigator.go = guardedGo
    let restoring = false
    let bypass = false
    const index = window.history.state?.idx as number | undefined
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    const pop = (event: PopStateEvent) => {
      if (bypass) return
      const nextIndex = event.state?.idx as number | undefined
      if (index === undefined || nextIndex === undefined) return
      event.stopImmediatePropagation()
      if (restoring) { restoring = false; return }
      const delta = index - nextIndex
      if (!delta) return
      restoring = true
      window.history.go(delta)
      requestLeave(() => { bypass = true; window.history.go(-delta) })
    }
    window.addEventListener('beforeunload', unload)
    window.addEventListener('popstate', pop, true)
    return () => {
      if (navigator.push === guardedPush) navigator.push = originalPush
      if (navigator.replace === guardedReplace) navigator.replace = originalReplace
      if (navigator.go === guardedGo) navigator.go = originalGo
      window.removeEventListener('beforeunload', unload)
      window.removeEventListener('popstate', pop, true)
    }
  }, [dirty, navigator, requestLeave])
}
