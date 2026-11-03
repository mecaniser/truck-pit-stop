import { QueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'

export const createSessionClient = () => new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      // A 429 means the client is rate-limited, not that the request
      // failed transiently — the default exponential-backoff retry just
      // adds more load to an already-saturated limiter and can chain into
      // a self-sustaining pile of retrying requests during fast navigation
      // (e.g. paging through many repair orders quickly). Every other
      // failure still gets one retry as before.
      retry: (failureCount, err) => !(isAxiosError(err) && err.response?.status === 429) && failureCount < 1,
    },
  },
})

let activeClient: QueryClient | undefined
export function activeMutationCount() {
  return activeClient?.isMutating() ?? 0
}

export function trackSessionClient(client: QueryClient) {
  activeClient = client
  return () => {
    activeClient = undefined
    // StrictMode briefly unmounts then remounts the same client in development.
    queueMicrotask(() => { if (activeClient !== client) client.clear() })
  }
}
