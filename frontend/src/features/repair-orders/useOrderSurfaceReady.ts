import { useEffect, useState } from 'react'
import { useIsFetching } from '@tanstack/react-query'

// Mount children immediately so their reads run concurrently, then reveal the
// initial body once. Background refreshes must never hide an already open body.
export function useOrderSurfaceReady(orderId: string, scope: string, primaryPending: boolean) {
  const identity = `${scope}:${orderId}`
  const [revealed, setRevealed] = useState<string | null>(null)
  const pendingSections = useIsFetching({ predicate: query =>
    ['order-checklist', 'order-operations', 'recommended-work', 'vehicle-issues'].includes(String(query.queryKey[0]))
    && query.queryKey.includes(orderId)
    && query.state.data === undefined,
  })
  const ready = revealed === identity
  useEffect(() => {
    if (ready || primaryPending || pendingSections) return
    // Allow child query subscriptions to register before committing the reveal.
    const timer = window.setTimeout(() => setRevealed(identity), 80)
    return () => window.clearTimeout(timer)
  }, [identity, ready, primaryPending, pendingSections])
  return ready
}
