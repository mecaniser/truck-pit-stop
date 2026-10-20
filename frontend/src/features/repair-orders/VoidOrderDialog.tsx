import { useRef, useState } from 'react'
import { Description, Dialog, DialogBackdrop, DialogPanel, DialogTitle } from '@headlessui/react'
import { CircleSlash, X } from 'lucide-react'
import { errorDetail } from '@/features/service-checklists/queries'

export default function VoidOrderDialog({ orderNumber, invoiceNumber, pending, onClose, onConfirm }: {
  orderNumber: string
  invoiceNumber: string
  pending: boolean
  onClose: () => void
  onConfirm: (args: { reason: string; password: string }) => Promise<void> | void
}) {
  const [animate] = useState(() => !document.activeElement?.matches(':focus-visible'))
  const [reason, setReason] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const submittingRef = useRef(false)
  const busy = pending || submitting
  const dismiss = () => { if (!busy) onClose() }

  return (
    <Dialog open onClose={dismiss} className="fixed inset-0 z-[150]" onKeyDownCapture={event => {
      // Escape belongs to this confirmation, not the order workspace behind it.
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        dismiss()
      }
    }}>
      <DialogBackdrop transition={animate} className="fixed inset-0 bg-slate-950/45 transition-opacity duration-150 ease-out data-[closed]:opacity-0 motion-reduce:transition-none" />
      <div className="fixed inset-x-0 flex items-center justify-center p-3 sm:p-6" style={{ top: 'var(--db-workspace-viewport-top, 0px)', height: 'var(--db-workspace-viewport-height, 100dvh)' }}>
        <DialogPanel transition={animate} className="flex max-h-full w-full max-w-md flex-col overflow-hidden rounded-2xl bg-white text-slate-950 shadow-xl transition-opacity duration-150 ease-out data-[closed]:opacity-0 motion-reduce:transition-none">
          <header className="flex shrink-0 items-center gap-3 px-5 pb-3 pt-4">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-50 text-red-700"><CircleSlash size={20} aria-hidden="true" /></span>
            <DialogTitle className="flex-1 text-lg font-semibold">Void entire order?</DialogTitle>
            <button type="button" disabled={busy} onClick={dismiss} aria-label="Close void dialog" className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-700 disabled:opacity-50"><X size={20} /></button>
          </header>
          <form className="flex min-h-0 flex-col" onSubmit={async event => {
            event.preventDefault()
            if (pending || submittingRef.current || reason.trim().length < 3 || reason.trim().length > 1000 || !password) return
            submittingRef.current = true
            setSubmitting(true)
            setError('')
            try {
              await onConfirm({ reason: reason.trim(), password })
              onClose()
            } catch (failure) {
              // The parent also reports the error; keep the reason available for retry.
              setError(errorDetail(failure, 'Could not void this order. Enter your password to try again.'))
            } finally {
              setPassword('')
              submittingRef.current = false
              setSubmitting(false)
            }
          }}>
            <div className="min-h-0 space-y-4 overflow-y-auto px-5 pb-5">
              <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
                <p className="break-words font-semibold">Order {orderNumber}</p>
                <p className="mt-0.5 break-words text-slate-600">Invoice {invoiceNumber}</p>
              </div>
              <Description className="text-sm leading-5 text-slate-600">Cancels this repair order and voids its invoice. Both records and your reason stay in history.</Description>
              <label className="block text-sm font-medium">Reason for voiding
                <textarea data-autofocus required minLength={3} maxLength={1000} disabled={busy} rows={3} value={reason} onChange={event => setReason(event.target.value)} placeholder="Tell us why this order is being voided" className="mt-1.5 block w-full resize-none rounded-lg border border-slate-300 bg-white px-3 py-2 text-base font-normal text-slate-950 placeholder:text-slate-500 focus:border-slate-500 focus:outline focus:outline-2 focus:outline-offset-2 focus:outline-slate-500 disabled:opacity-60" />
              </label>
              <label className="block text-sm font-medium">Your password
                <input required type="password" autoComplete="current-password" disabled={busy} value={password} onChange={event => setPassword(event.target.value)} className="mt-1.5 block min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base font-normal text-slate-950 focus:border-slate-500 focus:outline focus:outline-2 focus:outline-offset-2 focus:outline-slate-500 disabled:opacity-60" />
              </label>
              {error && <p role="alert" className="break-words text-sm text-red-700">{error}</p>}
            </div>
            <footer className="flex shrink-0 justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3">
              <button type="button" disabled={busy} onClick={dismiss} className="min-h-11 whitespace-nowrap rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-700 disabled:opacity-50">Cancel</button>
              <button type="submit" disabled={busy || reason.trim().length < 3 || reason.trim().length > 1000 || !password} className="min-h-11 whitespace-nowrap rounded-lg bg-red-700 px-4 text-sm font-semibold text-white hover:bg-red-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-700 disabled:opacity-50">{busy ? 'Voiding…' : 'Void entire order'}</button>
            </footer>
          </form>
        </DialogPanel>
      </div>
    </Dialog>
  )
}
