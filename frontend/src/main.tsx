import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import App from './App.tsx'
import { startStaleDeployWatch } from './lib/staleDeploy'
import { startStaleBuildWatch } from './lib/staleBuild'
import './index.css'

const queryClient = new QueryClient({
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

startStaleDeployWatch()

// DB-076: a tab parked for days never requests new code, so nothing would
// otherwise tell it a deploy has happened. The mutation count comes from the
// query client so a save in flight is never cut off by a reload.
startStaleBuildWatch({ mutationsInFlight: () => queryClient.isMutating() })

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)
