import { Component, type ErrorInfo, type ReactNode } from 'react'
import { RefreshCw } from 'lucide-react'
import { isStaleChunkError, markStaleDeployHandled } from '../lib/staleDeploy'

/**
 * `React.lazy` re-throws a failed chunk import during render. Without a
 * boundary React unmounts the whole tree, so the page goes blank and even a
 * recovery notice mounted beside the routes is torn down with it — the
 * observed production symptom. This boundary keeps something on screen and,
 * for a stale chunk, makes the reload reachable.
 */
type State = { error: Error | null }

export default class RouteErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    if (isStaleChunkError(error)) markStaleDeployHandled()
    // Keep the original diagnostics; this boundary changes what the person
    // sees, not what a developer can debug.
    console.error('Route render failed', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    const stale = isStaleChunkError(error)
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div role="alert" className="max-w-md rounded-xl border border-slate-300 bg-white p-6 text-slate-900 shadow-lg">
          <p className="text-base font-semibold">
            {stale ? 'A new version of DieselBridge is available' : 'Something went wrong'}
          </p>
          <p className="mt-2 text-sm leading-5 text-slate-700">
            {stale
              ? 'Reload to finish updating. Anything you have typed but not saved will be lost.'
              : 'This page could not be displayed. Reloading may help; if it keeps happening, tell us what you were doing.'}
          </p>
          <button
            type="button"
            className="mt-4 flex min-h-11 items-center gap-2 rounded-lg border border-slate-700 px-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            onClick={() => window.location.reload()}
          >
            <RefreshCw size={16} aria-hidden="true" />Reload now
          </button>
        </div>
      </div>
    )
  }
}
