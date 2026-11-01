import { ControlButton } from './ui/Controls'

export default function ReadFailure({ subject, retrying, onRetry }: { subject: string; retrying: boolean; onRetry: () => void }) {
  return <div role="alert" className="m-4 rounded-lg border border-amber-400/40 bg-amber-100 p-4 text-sm text-amber-950" aria-busy={retrying}>
    <p>Could not load {subject}. Check your connection and try again.</p>
    <ControlButton type="button" onClick={onRetry} disabled={retrying}>{retrying ? 'Retrying…' : `Retry ${subject}`}</ControlButton>
  </div>
}
