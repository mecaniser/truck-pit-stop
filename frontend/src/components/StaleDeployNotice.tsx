import { RefreshCw } from 'lucide-react'
import { useStaleDeploy } from '../lib/staleDeploy'

/**
 * Shown when the running build's assets are gone from the server. The page is
 * already broken at this point, so this is the only route back — but it is
 * framed as a new version rather than a failure, because nothing the person
 * did caused it.
 */
export default function StaleDeployNotice() {
  const stale = useStaleDeploy((state) => state.stale)
  const handled = useStaleDeploy((state) => state.handled)
  if (!stale || handled) return null

  return (
    <aside className="fixed bottom-4 left-4 right-4 z-[100] mx-auto flex max-w-lg flex-wrap items-center gap-3 rounded-xl border border-sky-300 bg-sky-50 p-4 text-sky-950 shadow-lg">
      <div role="status" aria-live="polite" className="min-w-0 flex-1 basis-56">
        <p className="text-sm font-semibold">A new version of DieselBridge is available</p>
        <p className="mt-1 text-sm leading-5">Reload to finish updating. Anything you have typed but not saved will be lost.</p>
      </div>
      <button
        type="button"
        className="flex min-h-11 items-center gap-2 rounded-lg border border-sky-700 px-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-800"
        onClick={() => window.location.reload()}
      >
        <RefreshCw size={16} aria-hidden="true" />Reload now
      </button>
    </aside>
  )
}
