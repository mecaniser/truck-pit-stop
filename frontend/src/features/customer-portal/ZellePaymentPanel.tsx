import { ChevronDown, ChevronUp, Copy } from 'lucide-react'

interface ZellePaymentPanelProps {
  garageName?: string | null
  serviceFeeAmount: string | number | null | undefined
  zelleAmount: string
  zelleMemo: string
  zelleEmail?: string | null
  zellePhone?: string | null
  zelleQrImage?: string | null
  pendingConfirmation: boolean
  isOpen: boolean
  isSenderEditing: boolean
  senderEmail: string
  senderPhone: string
  senderNotes: string
  isSubmitting: boolean
  onToggleOpen: () => void
  onCopy: (value: string | null | undefined, label: string) => void
  onToggleSenderEditing: () => void
  onSenderEmailChange: (value: string) => void
  onSenderPhoneChange: (value: string) => void
  onSenderNotesChange: (value: string) => void
  onSubmit: () => void
}

const copyRows = [
  { key: 'amount', label: 'Amount', copyLabel: 'Zelle amount' },
  { key: 'memo', label: 'Memo', copyLabel: 'Zelle memo' },
  { key: 'email', label: 'Send to email', copyLabel: 'Zelle email' },
  { key: 'phone', label: 'Send to phone', copyLabel: 'Zelle phone' },
] as const

export default function ZellePaymentPanel({
  garageName,
  serviceFeeAmount,
  zelleAmount,
  zelleMemo,
  zelleEmail,
  zellePhone,
  zelleQrImage,
  pendingConfirmation,
  isOpen,
  isSenderEditing,
  senderEmail,
  senderPhone,
  senderNotes,
  isSubmitting,
  onToggleOpen,
  onCopy,
  onToggleSenderEditing,
  onSenderEmailChange,
  onSenderPhoneChange,
  onSenderNotesChange,
  onSubmit,
}: ZellePaymentPanelProps) {
  const serviceFee = parseFloat(String(serviceFeeAmount || '0')) || 0
  const rows = copyRows
    .map(row => {
      if (row.key === 'amount') return { ...row, value: `$${zelleAmount}` }
      if (row.key === 'memo') return { ...row, value: zelleMemo }
      if (row.key === 'email') return { ...row, value: zelleEmail }
      return { ...row, value: zellePhone }
    })
    .filter(row => row.value)

  return (
    <div className="overflow-hidden rounded-xl border border-blue-300/25 bg-slate-950/40">
      <button
        type="button"
        onClick={onToggleOpen}
        className="flex w-full items-center justify-between gap-3 border-b border-white/10 bg-blue-500/10 px-4 py-3 text-left hover:bg-blue-500/15"
      >
        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-white">Pay with Zelle</p>
            <span className="rounded-full bg-cyan-400/15 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-cyan-200">
              No card fee
            </span>
            {pendingConfirmation && (
              <span className="rounded-full bg-amber-300/15 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-amber-200">
                Pending review
              </span>
            )}
          </div>
          <p className="text-xs text-blue-100/80">
            {serviceFee > 0 ? `Save $${serviceFee.toFixed(2)} by sending from your bank app.` : 'Copy the payment details into your bank app.'}
          </p>
        </div>
        {isOpen ? <ChevronUp className="h-4 w-4 shrink-0 text-blue-100" /> : <ChevronDown className="h-4 w-4 shrink-0 text-blue-100" />}
      </button>

      {isOpen && (
        <div>
          <div className="px-4 py-3">
            <div className="mb-2">
              <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-blue-200">Use in your bank app</p>
              <p className="mt-1 text-sm text-blue-50">
                Send to {garageName || 'the shop'} and include the invoice memo below.
              </p>
            </div>

            <div className="divide-y divide-white/10">
              {rows.map(row => (
                <div key={row.key} className="grid grid-cols-[minmax(5.5rem,8rem)_1fr_auto] items-center gap-3 py-2.5">
                  <p className="text-[11px] font-bold uppercase tracking-wide text-blue-200">{row.label}</p>
                  <p className={`min-w-0 break-all text-sm ${row.key === 'amount' ? 'font-black text-white' : 'text-blue-50'}`}>
                    {row.value}
                  </p>
                  <button
                    type="button"
                    aria-label={`Copy ${row.label}`}
                    onClick={() => onCopy(row.key === 'amount' ? zelleAmount : row.value, row.copyLabel)}
                    className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-blue-100 hover:bg-blue-500/20 hover:text-white"
                    title={`Copy ${row.label}`}
                  >
                    <Copy className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>

            {zelleQrImage && (
              <>
                <div className="mt-3 hidden justify-center bg-white p-3 sm:flex">
                  <img src={zelleQrImage} alt="Zelle QR" className="h-44 w-44 object-contain" />
                </div>
                <p className="mt-3 text-xs text-blue-100/75 sm:hidden">
                  On mobile, copy either the Zelle email or phone above and paste it into Zelle.
                </p>
              </>
            )}
          </div>

          <div className="border-t border-orange-200/25 bg-orange-400/10 px-4 py-3">
            {pendingConfirmation ? (
              <p className="text-sm text-amber-100">
                Payment is marked as submitted via Zelle and pending staff confirmation.
              </p>
            ) : (
              <>
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-orange-100">Sent to the shop</p>
                    <p className="mt-1 text-xs text-orange-50/80">These details help staff match your bank transfer.</p>
                  </div>
                  <button
                    type="button"
                    onClick={onToggleSenderEditing}
                    className="shrink-0 rounded-md border border-orange-200/40 px-3 py-1.5 text-xs font-bold text-orange-50 hover:bg-orange-300/10"
                  >
                    {isSenderEditing ? 'Done' : 'Edit'}
                  </button>
                </div>

                <div className="space-y-2">
                  <input
                    type="email"
                    value={senderEmail}
                    onChange={event => onSenderEmailChange(event.target.value)}
                    placeholder="Your Zelle sender email"
                    disabled={!isSenderEditing}
                    className="w-full rounded-md border border-orange-200/30 bg-slate-950/20 px-3 py-2 text-white placeholder-orange-100/45 disabled:cursor-not-allowed disabled:opacity-80"
                  />
                  <input
                    type="tel"
                    value={senderPhone}
                    onChange={event => onSenderPhoneChange(event.target.value)}
                    placeholder="Your Zelle sender phone"
                    disabled={!isSenderEditing}
                    className="w-full rounded-md border border-orange-200/30 bg-slate-950/20 px-3 py-2 text-white placeholder-orange-100/45 disabled:cursor-not-allowed disabled:opacity-80"
                  />
                  <textarea
                    value={senderNotes}
                    onChange={event => onSenderNotesChange(event.target.value)}
                    rows={2}
                    placeholder="Memo/details sent to shop staff"
                    disabled={!isSenderEditing}
                    className="w-full resize-none rounded-md border border-orange-200/30 bg-slate-950/20 px-3 py-2 text-white placeholder-orange-100/45 disabled:cursor-not-allowed disabled:opacity-80"
                  />
                </div>

                <button
                  type="button"
                  onClick={onSubmit}
                  disabled={isSubmitting}
                  className="mt-3 w-full rounded-lg bg-blue-600 py-2.5 font-bold text-white hover:bg-blue-500 disabled:bg-gray-600"
                >
                  {isSubmitting ? 'Submitting...' : 'I Sent Payment via Zelle'}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
