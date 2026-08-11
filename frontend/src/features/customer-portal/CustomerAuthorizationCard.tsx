import { CheckCircle, FileText } from 'lucide-react'
import type { Quote, RepairOrderHistoryEvent } from '@/types'
import { AuthorizationHistoryList, AuthorizationSummary } from '@/features/quotes/AuthorizationSummary'
import {
  authorizationDecisionLabel,
  authorizationTitle,
  isAdditionalWorkAuthorization,
} from '@/features/quotes/authorization'

type Props = {
  quote: Quote
  historyEvents?: RepairOrderHistoryEvent[]
  approvePending: boolean
  declinePending: boolean
  showDeclineForm: boolean
  declineNotes: string
  onApprove: () => void
  onShowDecline: () => void
  onDeclineNotesChange: (value: string) => void
  onDecline: () => void
  onCancelDecline: () => void
}

export default function CustomerAuthorizationCard({
  quote,
  historyEvents = [],
  approvePending,
  declinePending,
  showDeclineForm,
  declineNotes,
  onApprove,
  onShowDecline,
  onDeclineNotesChange,
  onDecline,
  onCancelDecline,
}: Props) {
  const isAdditional = isAdditionalWorkAuthorization(quote)

  if (quote.is_declined) {
    return (
      <section className="rounded-xl border border-red-400/30 bg-red-500/10 p-4 sm:p-6" aria-label={`${authorizationTitle(quote)} declined`}>
        <div className="flex items-start gap-3">
          <FileText className="h-6 w-6 shrink-0 text-red-300" />
          <div>
            <h3 className="font-semibold text-white">
              {isAdditional ? 'Additional work declined' : 'Estimate declined'}
            </h3>
            <p className="mt-1 text-sm text-gray-300">
              {isAdditional
                ? 'Your earlier approved amount remains authorized. The shop can revise or remove the added work.'
                : 'The shop received your decision and can prepare a new revision.'}
            </p>
          </div>
        </div>
        <div className="mt-4">
          <AuthorizationSummary quote={quote} />
        </div>
        {quote.decline_notes && (
          <p className="mt-3 rounded-lg bg-black/15 p-3 text-sm text-gray-300">
            Your note: {quote.decline_notes}
          </p>
        )}
        <div className="mt-4">
          <AuthorizationHistoryList events={historyEvents} />
        </div>
      </section>
    )
  }

  return (
    <section className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 sm:p-6" aria-label={authorizationTitle(quote)}>
      <div className="mb-4 flex items-start gap-3">
        <FileText className="h-6 w-6 shrink-0 text-amber-400" />
        <div>
          <h3 className="font-semibold text-white">
            {authorizationTitle(quote)} · {quote.quote_number}
          </h3>
          <p className="mt-1 text-sm text-gray-300">
            {isAdditional
              ? 'Review only the added amount. Your earlier approval remains valid.'
              : 'Review the shop’s estimate before authorizing work.'}
          </p>
        </div>
      </div>

      <AuthorizationSummary quote={quote} />

      {quote.expires_at && (
        <p className="mt-2 text-xs text-gray-400">
          Valid until {new Date(quote.expires_at).toLocaleDateString(undefined, {
            month: 'long', day: 'numeric', year: 'numeric',
          })}
        </p>
      )}

      <div className="mt-4">
        <AuthorizationHistoryList events={historyEvents} />
      </div>

      {!showDeclineForm ? (
        <div className="mt-4 flex flex-col gap-3 sm:flex-row">
          <button
            type="button"
            onClick={onApprove}
            disabled={approvePending || declinePending}
            className="flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-3 font-medium text-white transition-colors hover:bg-violet-500 disabled:bg-gray-500"
          >
            <CheckCircle className="h-5 w-5" />
            {approvePending ? 'Authorizing…' : authorizationDecisionLabel(quote)}
          </button>
          <button
            type="button"
            onClick={onShowDecline}
            disabled={approvePending || declinePending}
            className="min-h-[44px] flex-1 rounded-xl border border-white/20 bg-white/10 px-4 py-3 font-medium text-white transition-colors hover:bg-white/20 disabled:opacity-50"
          >
            Decline this revision
          </button>
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          <label className="block text-sm text-gray-300" htmlFor={`decline-${quote.id}`}>
            Tell the shop what should change (optional)
          </label>
          <textarea
            id={`decline-${quote.id}`}
            value={declineNotes}
            onChange={(event) => onDeclineNotesChange(event.target.value)}
            placeholder={isAdditional ? 'For example: please defer this added work.' : 'For example: please revise the repair scope.'}
            className="w-full resize-none rounded-xl border border-[#30384b] bg-[#0d1118] px-3 py-3 text-base text-white placeholder-gray-500 focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
            rows={3}
          />
          <div className="flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={onDecline}
              disabled={declinePending || approvePending}
              className="min-h-[44px] flex-1 rounded-xl bg-violet-600 px-4 py-3 font-medium text-white transition-colors hover:bg-violet-500 disabled:bg-gray-500"
            >
              {declinePending ? 'Sending…' : 'Confirm decline'}
            </button>
            <button
              type="button"
              onClick={onCancelDecline}
              disabled={declinePending}
              className="min-h-[44px] rounded-xl bg-white/10 px-4 py-3 font-medium text-white transition-colors hover:bg-white/20 disabled:opacity-50"
            >
              Keep reviewing
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
