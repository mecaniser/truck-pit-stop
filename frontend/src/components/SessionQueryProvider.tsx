import { useLayoutEffect, useState, type ReactNode } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { createSessionClient, trackSessionClient } from '../lib/sessionQueryClient'
import toast from 'react-hot-toast'
import { getAuthenticatedSessionIdentity, useAuthStore } from '../stores/authStore'

function SessionCache({ children }: { children: ReactNode }) {
  const [client] = useState(createSessionClient)
  useLayoutEffect(() => trackSessionClient(client), [client])
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

function sessionScope(state: ReturnType<typeof useAuthStore.getState>) {
  return JSON.stringify([getAuthenticatedSessionIdentity(state), state.user?.permissions?.payments === true])
}

export function SessionQueryProvider({ children }: { children: ReactNode }) {
  const scope = useAuthStore(sessionScope)
  // Notifications have a global store outside React Query. Remove them at the
  // same boundary so a previous repair number cannot remount with the next user.
  useLayoutEffect(() => useAuthStore.subscribe((next, previous) => {
    if (sessionScope(next) !== sessionScope(previous)) toast.remove()
  }), [])
  return <SessionCache key={scope}>{children}</SessionCache>
}
