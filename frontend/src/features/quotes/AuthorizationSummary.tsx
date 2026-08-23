import type { Quote, RepairOrderHistoryEvent } from '@/types'
import {
  authorizationTitle,
  formatAuthorizationEventDetail,
  isAdditionalWorkAuthorization,
} from './authorization'

const formatMoney = (value: string): string =>
  (Number.parseFloat(value || '0') || 0).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
  })

export function AuthorizationSummary({
  quote,
  theme = 'dark',
}: {
  quote: Quote
  theme?: 'dark' | 'light'
}) {
  const isAdditional = isAdditionalWorkAuthorization(quote)
  const shell = theme === 'dark'
    ? 'border-white/10 bg-white/5 text-white'
    : 'border-amber-200 bg-amber-50 text-gray-900'
  const muted = theme === 'dark' ? 'text-gray-400' : 'text-gray-600'
  const emphasis = theme === 'dark' ? 'text-amber-200' : 'text-amber-900'

  return (
    <section className={`rounded-xl border p-4 ${shell}`} aria-label={`${authorizationTitle(quote)} amounts`}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className={`text-xs font-bold uppercase tracking-[0.12em] ${emphasis}`}>
          {authorizationTitle(quote)}
        </span>
        <span className={`text-xs font-medium ${muted}`}>Revision {quote.revision}</span>
      </div>
      <dl className="space-y-2 text-sm tabular-nums">
        {isAdditional ? (
          <>
            <div className="flex items-center justify-between gap-4">
              <dt className={muted}>Previously authorized</dt>
              <dd className="font-semibold">{formatMoney(quote.previously_authorized_amount)}</dd>
            </div>
            <div className={`flex items-center justify-between gap-4 ${emphasis}`}>
              <dt className="font-semibold">Additional work</dt>
              <dd className="font-bold">+{formatMoney(quote.delta_amount)}</dd>
            </div>
            <div className="flex items-center justify-between gap-4 border-t border-current/10 pt-2">
              <dt className="font-semibold">Resulting authorized total</dt>
              <dd className="font-bold">{formatMoney(quote.total_amount)}</dd>
            </div>
          </>
        ) : (
          <div className="flex items-center justify-between gap-4">
            <dt className={muted}>Estimated repair total</dt>
            <dd className="text-lg font-bold">{formatMoney(quote.total_amount)}</dd>
          </div>
        )}
      </dl>
    </section>
  )
}

export function AuthorizationHistoryList({
  events,
  theme = 'dark',
}: {
  events: RepairOrderHistoryEvent[]
  theme?: 'dark' | 'light'
}) {
  if (!events.length) return null
  const text = theme === 'dark' ? 'text-gray-200' : 'text-gray-800'
  const muted = theme === 'dark' ? 'text-gray-400' : 'text-gray-500'
  const border = theme === 'dark' ? 'border-white/10' : 'border-gray-200'

  return (
    <details className={`rounded-xl border p-4 ${border}`}>
      <summary className={`cursor-pointer text-sm font-semibold ${text}`}>
        Authorization history · {events.length} event{events.length === 1 ? '' : 's'}
      </summary>
      <ol className={`mt-3 space-y-3 border-t pt-3 ${border}`}>
        {events.map((event) => (
          <li key={event.id} className="text-sm">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className={`font-semibold ${text}`}>{event.label}</p>
              <time className={`text-xs ${muted}`} dateTime={event.created_at}>
                {new Date(event.created_at).toLocaleString(undefined, {
                  month: 'short',
                  day: 'numeric',
                  hour: 'numeric',
                  minute: '2-digit',
                })}
              </time>
            </div>
            {(event.actor_name || event.detail) && (
              <p className={`mt-1 text-xs leading-5 ${muted}`}>
                {event.actor_name && <span className="font-semibold">{event.actor_name} · </span>}
                {formatAuthorizationEventDetail(event.detail)}
              </p>
            )}
          </li>
        ))}
      </ol>
    </details>
  )
}
