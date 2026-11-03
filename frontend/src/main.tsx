import React from 'react'
import ReactDOM from 'react-dom/client'
import { activeMutationCount } from './lib/sessionQueryClient'
import { SessionQueryProvider } from './components/SessionQueryProvider'
import { captureWorkOSLoginReturn } from './lib/workosLoginReturn'
import { watchSessionBoundary } from './stores/authStore'
import App from './App.tsx'
import { startStaleDeployWatch } from './lib/staleDeploy'
import { startStaleBuildWatch } from './lib/staleBuild'
import './index.css'
import { captureMotiveCallback } from './lib/motiveCallback'

// Remove OAuth parameters before session bootstrap or analytics can mount.
captureMotiveCallback()
captureWorkOSLoginReturn()
watchSessionBoundary()


startStaleDeployWatch()

// DB-076: a tab parked for days never requests new code, so nothing would
// otherwise tell it a deploy has happened. The mutation count comes from the
// query client so a save in flight is never cut off by a reload.
startStaleBuildWatch({ mutationsInFlight: activeMutationCount })

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <SessionQueryProvider>
      <App />
    </SessionQueryProvider>
  </React.StrictMode>,
)
