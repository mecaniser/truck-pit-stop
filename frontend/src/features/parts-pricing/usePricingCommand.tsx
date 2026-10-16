import { useEffect, useRef, useState } from 'react'
import SlidePanelForm from '@/components/SlidePanelForm'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { PricingCancelled, parsePricingPreview, pricingError, pricingMoney, previewTotal, priceSourceLabel, type PricingPreview, type ResolveRequest } from './contract'
import './parts-pricing.css'

export type PricingConfirmation = { pricing_preview_fingerprint: string; pricing_presentation: 'shop' | 'fleet' }
type Write = (confirmation: PricingConfirmation, options: { signal: AbortSignal; headers: { 'Idempotency-Key': string }; skipAuthRefresh: true }) => Promise<unknown>
type Review = { preview: PricingPreview; previous?: PricingPreview; message?: string }
type Attempt = { key: string; requestId: string; preview: PricingPreview }

/** The only retry loop is an operator accepting a fresh conflict preview. Network
 * failures retain their UUID and original fingerprint for an explicit retry. */
export function usePricingCommand(contextKey: string) {
  const user = useAuthStore(state => state.user)
  const epoch = useAuthStore(state => state.authSessionEpoch)
  const identity = JSON.stringify([user?.tenant_id, user?.id, user?.role, epoch, contextKey])
  const currentIdentity = useRef(identity)
  currentIdentity.current = identity
  const mounted = useRef(true)
  const pending = useRef(false)
  const abort = useRef<AbortController | null>(null)
  const awaiting = useRef<{ accept: () => void; cancel: () => void } | null>(null)
  const attempts = useRef(new Map<string, Attempt>())
  const [busy, setBusy] = useState(false)
  const [commandError, setCommandError] = useState<string | null>(null)
  const [review, setReview] = useState<Review | null>(null)
  useEffect(() => {
    mounted.current = true
    const retainedAttempts = attempts.current
    return () => {
      mounted.current = false; abort.current?.abort(); awaiting.current?.cancel(); awaiting.current = null; retainedAttempts.clear()
    }
  }, [])
  useEffect(() => {
    abort.current?.abort(); awaiting.current?.cancel(); awaiting.current = null; attempts.current.clear()
    setReview(null); setCommandError(null); setBusy(false); pending.current = false
  }, [identity])
  const execute = async <T,>(request: ResolveRequest, write: Write, mutationIdentity?: unknown, forceReview = false): Promise<T> => {
    if (pending.current) throw new PricingCancelled()
    const owner = identity
    const auth = useAuthStore.getState()
    const actor = auth.user
    const valid = () => {
      const next = useAuthStore.getState()
      return mounted.current && currentIdentity.current === owner && !next.logoutInProgress && next.authSessionEpoch === auth.authSessionEpoch
        && next.user?.id === actor?.id && next.user?.tenant_id === actor?.tenant_id && next.user?.role === actor?.role
    }
    if (!actor?.tenant_id || !valid()) throw new PricingCancelled()
    const controller = new AbortController(); abort.current = controller
    const active = () => valid() && !controller.signal.aborted
    const key = JSON.stringify([request, mutationIdentity])
    const accept = async (next: Review) => {
      if (!active()) throw new PricingCancelled()
      setReview(next)
      await new Promise<void>((resolve, reject) => { awaiting.current = { accept: resolve, cancel: () => reject(new PricingCancelled()) } })
      awaiting.current = null
      if (!active()) throw new PricingCancelled()
      setReview(null)
    }
    pending.current = true; setBusy(true); setCommandError(null)
    try {
      let current = attempts.current.get(key) ?? null
      if (!current) {
        const response = await api.post('/parts-pricing/resolve', request, { signal: controller.signal })
        if (!active()) throw new PricingCancelled()
        const preview = parsePricingPreview(response.data, request, actor.role)
        if (forceReview || preview.confirmation_required) await accept({ preview })
        current = { key, requestId: crypto.randomUUID(), preview }
        attempts.current.set(key, current)
      }
      for (;;) {
        try {
          const result = await write({ pricing_preview_fingerprint: current.preview.pricing_preview_fingerprint, pricing_presentation: current.preview.projection }, { signal: controller.signal, headers: { 'Idempotency-Key': current.requestId }, skipAuthRefresh: true })
          if (!active()) throw new PricingCancelled()
          attempts.current.delete(key)
          return result as T
        } catch (error) {
          if (!active()) throw new PricingCancelled()
          const response = (error as { response?: { status?: number; data?: { detail?: { code?: string; message?: string; preview?: unknown } } } }).response
          const detail = response?.data?.detail
          if (response?.status !== 409 || !['pricing_preview_required', 'pricing_preview_changed', 'bundle_availability_changed'].includes(detail?.code ?? '')) throw error
          attempts.current.delete(key)
          // Older adapters may report a conflict without embedding its fresh quote.
          // Refetch for review; never replay the write just because that read succeeds.
          const data = detail?.preview ?? (await api.post('/parts-pricing/resolve', request, { signal: controller.signal })).data
          if (!active()) throw new PricingCancelled()
          const preview = parsePricingPreview(data, request, actor.role, true)
          await accept({ preview, previous: current.preview, message: detail?.message })
          current = { key, requestId: crypto.randomUUID(), preview }; attempts.current.set(key, current)
        }
      }
    } catch (error) {
      if (active() && !(error instanceof PricingCancelled)) setCommandError(pricingError(error, 'Pricing could not be confirmed. Your draft is kept. Try again.'))
      throw error
    } finally {
      if (active()) { pending.current = false; setBusy(false); setReview(null); awaiting.current = null }
    }
  }
  const cancel = () => { awaiting.current?.cancel() }
  const dialog = review ? <SlidePanelForm portalToShell isOpen={Boolean(review)} onClose={cancel} title={review?.previous ? 'Review changed price' : 'Review parts pricing'} category="Parts pricing" panelClassName="db-parts-pricing" overlayClassName="db-parts-pricing-overlay" width="sm:w-[580px]" submitLabel={review?.previous ? 'Accept new price' : 'Confirm price'} onSubmit={event => { event.preventDefault(); awaiting.current?.accept() }}>
    {review && <>
      {review.message && <p role="alert">{review.message}</p>}
      <div className="db-parts-pricing__total"><span>Resulting {review.preview.totals.kind === 'counter_sale' ? 'sale' : 'repair'} total</span><strong>{pricingMoney(previewTotal(review.preview))}</strong></div>
      {review.previous && <p className="db-parts-pricing__muted">Previously {pricingMoney(previewTotal(review.previous))}</p>}
      <ul className="db-parts-pricing__quote-lines">{review.preview.lines.map(line => <li key={line.line_key}>
        <div><strong>{line.name}</strong><span className="db-parts-pricing__muted">{line.quantity} {line.unit_type} · {line.disposition === 'retained' ? 'Saved line' : line.disposition === 'omitted' ? 'Not included' : line.disposition === 'removed' ? 'Removed' : 'New line'}</span></div>
        {'pricing' in line && <div><strong>{pricingMoney(line.pricing.charged_unit_price)}</strong><span className="db-parts-pricing__muted">{priceSourceLabel(line.pricing.current_source)}</span>{(() => { const previous = review.previous?.projection === 'shop' ? review.previous.lines.find(old => old.line_key === line.line_key) : undefined; return previous && 'pricing' in previous && (previous.pricing.charged_unit_price !== line.pricing.charged_unit_price || previous.pricing.current_source !== line.pricing.current_source) ? <small>Was {pricingMoney(previous.pricing.charged_unit_price)} · {priceSourceLabel(previous.pricing.current_source)}</small> : null })()}</div>}
      </li>)}</ul>
      {review.preview.warnings.map((warning, index) => <p role="status" key={`${warning.code}:${warning.line_key}:${index}`}>{warning.message}</p>)}
    </>}
  </SlidePanelForm> : commandError ? <p className="db-parts-pricing__error" role="alert">{commandError}</p> : null
  return { execute, busy, dialog, clearError: () => setCommandError(null) }
}
