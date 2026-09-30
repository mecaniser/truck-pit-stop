import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import type { MotiveConnection } from './MotiveIntegrationPanel'
import { motiveError } from './motiveErrors'
import { takeMotiveCallback } from '@/lib/motiveCallback'

/** Consume the provider code once, then keep it out of URL history and UI. */
export default function MotiveCallback() {
  const navigate = useNavigate()
  const user = useAuthStore((state) => state.user)
  const started = useRef(false)
  const [message, setMessage] = useState('Finishing your Motive connection…')
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    if (started.current) return
    started.current = true
    const { state, code, error } = takeMotiveCallback()
    if (!state || (!code && !error) || !['garage_owner', 'garage_admin'].includes(user?.role ?? '')) {
      setMessage('This connection request is invalid or expired. Start again from Integrations.')
      setFailed(true)
      return
    }
    // Never retry a callback automatically: state and code are single-use.
    api.post<MotiveConnection>('/fleet/motive/callback', { state, ...(code ? { code } : {}), ...(error ? { error } : {}) }, { skipAuthRefresh: true })
      .then(({ data }) => {
        if (error || data.status !== 'connected') {
          setMessage(error ? 'Motive connection was cancelled. Your existing connection has not been replaced.' : 'Motive could not be connected. Start again from Integrations.')
          setFailed(true)
          return
        }
        navigate(`/fleet?integrations=motive&company=${encodeURIComponent(data.fleet_customer_id)}`, { replace: true })
      })
      .catch((failure: unknown) => {
        setMessage(motiveError(failure))
        setFailed(true)
      })
  }, [navigate, user?.role])
  return <main className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-6">
    <section className="max-w-md space-y-4" aria-label="Motive authorization">
      <h1 className="text-xl font-semibold">Connect Motive</h1>
      <p role={failed ? 'alert' : 'status'}>{message}</p>
      {failed && <button className="rounded-lg bg-amber-300 text-slate-950 px-4 py-3" onClick={() => navigate('/fleet?integrations=motive', { replace: true })}>Return to integrations</button>}
    </section>
  </main>
}
