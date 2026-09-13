import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useSessionRecovery } from '../lib/sessionRecovery'
import { renewSessionNow } from '../lib/sessionKeepAlive'

export default function SessionRecoveryNotice() {
  const recovering = useSessionRecovery((state) => state.recovering)
  const authenticated = useAuthStore((state) => state.isAuthenticated && !state.logoutInProgress)
  const [retrying, setRetrying] = useState(false)
  if (!recovering || !authenticated) return null

  return (
    <aside className="fixed bottom-4 left-4 right-4 z-[100] mx-auto flex max-w-lg flex-wrap items-center gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-amber-950 shadow-lg">
      <div role="status" aria-live="polite" className="min-w-0 flex-1 basis-56">
        <p className="text-sm font-semibold">Reconnecting your session</p>
        <p className="mt-1 text-sm leading-5">We’re having trouble renewing your session. We’ll retry automatically. Some actions may be unavailable until we reconnect.</p>
      </div>
      <button type="button" disabled={retrying} className="flex min-h-11 items-center gap-2 rounded-lg border border-amber-700 px-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-800 disabled:opacity-60"
        onClick={async () => {
          setRetrying(true)
          try { await renewSessionNow() } finally { setRetrying(false) }
        }}>
        <RefreshCw size={16} aria-hidden="true" />{retrying ? 'Retrying…' : 'Retry now'}
      </button>
    </aside>
  )
}
