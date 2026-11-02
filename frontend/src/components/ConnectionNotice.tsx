import { useEffect, useState } from 'react'
import { useRequestActivity } from '../lib/requestActivity'

export default function ConnectionNotice() {
  const [offline, setOffline] = useState(() => !navigator.onLine)
  const slow = useRequestActivity(s => s.slow > 0)
  useEffect(() => {
    const update = () => setOffline(!navigator.onLine)
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    update()
    return () => {
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
    }
  }, [])
  if (!offline && !slow) return null
  return <aside role="status" aria-live="polite" className="fixed left-4 right-4 top-4 z-[150] mx-auto max-w-lg rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 shadow-lg">
    <p className="font-semibold">{offline ? 'You’re offline' : 'This is taking longer than usual'}</p>
    <p className="mt-1">{offline
      ? 'Check your internet connection. Keep this page open; changes may not have been saved.'
      : 'We’re still waiting for a response. Keep this page open. Before submitting again, check whether your change was saved.'}</p>
  </aside>
}
