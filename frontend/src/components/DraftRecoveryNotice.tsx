import { useState } from 'react'
import { ControlButton } from './ui/Controls'

export default function DraftRecoveryNotice({ subject, uncertain, restore, discard }: {
  subject: string; uncertain: boolean; restore: () => Promise<void> | void; discard: () => void
}) {
  const [checked, setChecked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  return <aside role="status" className="m-4 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950">
    <p className="font-semibold">Your unfinished {subject} is available</p>
    <p>Restore the saved fields and review them before saving. Nothing will be submitted automatically.</p>
    {uncertain && <label className="my-2 block"><input type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)} /> I checked existing records. The previous submission may already have saved.</label>}
    {error && <p role="alert">Could not restore this draft with your current access. Check your connection and try again, or discard it.</p>}
    <div className="mt-2 flex gap-2">
      <ControlButton type="button" disabled={busy || (uncertain && !checked)} onClick={async () => {
        setBusy(true); setError(false)
        try { await restore() } catch { setError(true) } finally { setBusy(false) }
      }}>{busy ? 'Restoring…' : 'Restore draft'}</ControlButton>
      <ControlButton type="button" disabled={busy} onClick={discard}>Discard draft</ControlButton>
    </div>
  </aside>
}
