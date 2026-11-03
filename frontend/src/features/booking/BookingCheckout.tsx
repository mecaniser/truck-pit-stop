import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import type { Stripe } from '@stripe/stripe-js'
import { ControlButton } from '@/components/ui/Controls'
import { LoadingLine } from '@/components/ui'
import QuickBooksPaymentPanel from '@/features/customer-portal/QuickBooksPaymentPanel'
import { formatMoney } from '@/features/customer-portal/portal-ui'
import { moneyToCents } from '@/features/payments/money'
import { getStripeForAccount } from '@/lib/stripe'
import api from '@/lib/api'
import type { Vehicle } from '@/types'
import { vehicleIdentity } from '@/features/customer-portal/portal-context'
import type { BookingCapability, BookingPaymentResult, BookingReservation } from './booking-contract'

function savedVisitTime(scheduledAt: string, timezone?: string): string {
  if (!timezone) return 'Unavailable'
  try { return new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short', timeZone: timezone }).format(new Date(scheduledAt)) } catch { return 'Unavailable' }
}
function approvedTokenUrl(value?: string | null): boolean {
  if (!value) return false
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && ['api.intuit.com', 'sandbox.api.intuit.com'].includes(url.hostname) && url.pathname === '/quickbooks/v4/payments/tokens' && !url.username && !url.password && !url.port && !url.search && !url.hash
  } catch { return false }
}
function StripeBookingForm({ verify, pause }: { verify: () => Promise<void>; pause: () => void }) {
  const stripe = useStripe()
  const elements = useElements()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return <form className="space-y-4" onSubmit={async event => {
    event.preventDefault()
    if (!stripe || !elements || busy) return
    setBusy(true); setError(null)
    try {
      const result = await stripe.confirmPayment({ elements, redirect: 'if_required', confirmParams: { return_url: window.location.href } })
      if (result.error) {
        if (['validation_error', 'card_error'].includes(result.error.type)) setError(result.error.message || 'Check your payment details.')
        else pause()
        return
      }
      await verify()
    } catch { pause() }
    finally { setBusy(false) }
  }}><PaymentElement />{error && <p role="alert">{error}</p>}<ControlButton className="cp-primary" type="submit" disabled={!stripe || !elements || busy}>{busy ? 'Verifying payment…' : 'Pay and reserve'}</ControlButton></form>
}

export default function BookingCheckout({ appointment, capability, onDone, tenantId, vehicle }: { appointment: BookingReservation; capability?: BookingCapability; onDone: () => void; tenantId?: string | null; vehicle?: Vehicle | null }) {
  const heading = useRef<HTMLHeadingElement>(null)
  const attemptKey = useRef(crypto.randomUUID())
  const submissionStarted = useRef(false)
  const pollUntil = useRef(Date.now() + 120000)
  const [result, setResult] = useState<BookingPaymentResult | null>(null)
  const [started, setStarted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [stripe, setStripe] = useState<Stripe | null>(null)
  const [now, setNow] = useState(Date.now())
  const [stripeError, setStripeError] = useState(false)
  const [failedAttemptChecked, setFailedAttemptChecked] = useState(false)
  const [verificationPaused, setVerificationPaused] = useState(false)
  const status = useQuery<BookingReservation>({ queryKey: ['booking-status', appointment.id, tenantId, appointment.customer_id], queryFn: async ({ signal }) => (await api.get(`/appointments/${appointment.id}`, { signal })).data, initialData: appointment, retry: false, refetchInterval: query => Date.now() < pollUntil.current && query.state.dataUpdateCount < 25 && !['confirmed', 'cancelled'].includes(query.state.data?.status || '') ? 5000 : false })
  const current = status.isError ? appointment : status.data || appointment
  const paymentState = current.booking_payment_state
  const confirmed = !status.isError && current.status === 'confirmed' && paymentState === 'paid' && Boolean(current.receipt)
  const review = !status.isError && paymentState === 'payment_received_review'
  const closed = !status.isError && (current.status === 'cancelled' || ['refunded', 'refund_pending'].includes(paymentState))
  const expired = paymentState === 'expired_unpaid'
  const holdElapsed = !Number.isFinite(Date.parse(current.hold_expires_at)) || now >= Date.parse(current.hold_expires_at)
  const stripeAction = result?.provider === 'stripe_connect' && Boolean(result.client_secret && result.stripe_account_id) && ['created', 'requires_action', 'requires_payment_method'].includes(result.state)
  const pending = verificationPaused || (started && status.isError) || (paymentState === 'payment_processing' && !stripeAction) || ['processing', 'creating', 'outcome_unknown', 'succeeded'].includes(result?.state || '') || (started && !result)
  const terminalFailure = ['failed', 'cancelled'].includes(result?.state || '')
  const priceCents = moneyToCents(current.price)
  const validSnapshot = priceCents !== null && priceCents > 0n && current.currency === 'usd' && Number.isInteger(current.version) && current.version > 0 && Boolean(current.price_snapshot_sha256)
  const canStart = validSnapshot && current.status === 'pending' && paymentState === 'unpaid_hold' && !confirmed && !review && !pending && !terminalFailure && !expired && !holdElapsed && !started && !busy && !status.isError && capability?.available
  const canRetryCard = failedAttemptChecked && result?.state === 'failed' && current.status === 'pending' && paymentState === 'unpaid_hold' && validSnapshot && !holdElapsed && !status.isError && !status.isFetching && !busy
  useEffect(() => { heading.current?.focus() }, [confirmed, review])
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer) }, [])
  useEffect(() => {
    let active = true
    if (result?.provider !== 'stripe_connect' || !result.client_secret || !result.stripe_account_id) return
    getStripeForAccount(result.stripe_account_id).then(value => { if (active) setStripe(value) }).catch(() => { if (active) setStripeError(true) })
    return () => { active = false }
  }, [result?.provider, result?.client_secret, result?.stripe_account_id])
  const knownAttemptId = result?.attempt_id || current.payment_attempt_id
  const verify = async () => {
    if (!knownAttemptId || busy) return
    setFailedAttemptChecked(false)
    setBusy(true)
    try {
      const response = await api.post(`/appointments/${appointment.id}/confirm-payment`, { attempt_id: knownAttemptId, expected_version: result?.appointment_version ?? current.version })
      setResult(response.data)
      const checked = await status.refetch()
      setVerificationPaused(checked.isError)
      setFailedAttemptChecked(response.data.state === 'failed' && !checked.isError && checked.data?.booking_payment_state === 'unpaid_hold')
    } catch { setVerificationPaused(true) }
    finally { setBusy(false) }
  }
  const start = async (quickbooksToken?: string) => {
    if (!canStart || submissionStarted.current) return
    submissionStarted.current = true
    setFailedAttemptChecked(false)
    setStarted(true); setBusy(true)
    try {
      const response = await api.post(`/appointments/${appointment.id}/payment-attempts`, { expected_version: current.version, price_snapshot_sha256: current.price_snapshot_sha256, ...(quickbooksToken ? { quickbooks_token: quickbooksToken } : {}) }, { headers: { 'Idempotency-Key': attemptKey.current } })
      setResult(response.data)
      const checked = await status.refetch()
      setVerificationPaused(checked.isError)
      setFailedAttemptChecked(response.data.state === 'failed' && !checked.isError && checked.data?.booking_payment_state === 'unpaid_hold')
    } catch { setVerificationPaused(true) }
    finally { setBusy(false) }
  }
  const remainingSeconds = Math.max(0, Math.ceil((Date.parse(current.hold_expires_at) - now) / 1000))
  const visitSummary = <section aria-label="Your visit" className="space-y-2"><h3>Your visit</h3><dl>{[['Service', current.service_name || 'Unavailable'], ['Vehicle', current.vehicle_id ? vehicle?.id === current.vehicle_id ? vehicleIdentity(vehicle) : 'Unavailable' : 'Vehicle not specified'], ['Scheduled time', savedVisitTime(current.scheduled_at, capability?.shop_timezone)]].map(([label, value]) => <div className="cp-review-line" key={label}><dt>{label}</dt><dd><strong>{value}</strong></dd></div>)}</dl></section>
  if (confirmed) return <div className="space-y-4" role="status"><h2 ref={heading} tabIndex={-1}>Time reserved</h2><p>Your payment was verified and your appointment is confirmed.</p>{visitSummary}<p>Booking reference: <strong>{current.confirmation_number}</strong></p><ControlButton className="cp-primary" onClick={onDone}>View visits</ControlButton></div>
  if (closed) return <div className="space-y-4" role="status"><h2 ref={heading} tabIndex={-1}>{paymentState === 'refunded' ? 'Refund recorded' : paymentState === 'refund_pending' ? 'Refund review pending' : 'Reservation cancelled'}</h2><p>This reservation is not confirmed. {current.receipt ? 'A payment receipt is on record.' : 'No verified payment receipt is available.'}</p>{current.receipt?.amount && <div className="cp-review-line"><span>Recorded payment</span><strong>{formatMoney(current.receipt.amount)}</strong></div>}{current.receipt?.refunded_amount && <div className="cp-review-line"><span>Recorded refund</span><strong>{formatMoney(current.receipt.refunded_amount)}</strong></div>}{paymentState !== 'refunded' && current.receipt && <p>Cancellation does not confirm a refund. Contact the shop about this payment.</p>}<ControlButton className="cp-secondary" onClick={onDone}>View visits</ControlButton></div>
  if (review) return <div className="space-y-4" role="status"><h2 ref={heading} tabIndex={-1}>Payment received; shop review needed</h2><p>Your payment was received, but this start time is not confirmed. Contact the shop before making another payment or reservation.</p><ControlButton className="cp-secondary" onClick={onDone}>View visits</ControlButton></div>
  return <div className="space-y-4"><h2 ref={heading} tabIndex={-1}>Payment</h2><div className="cp-review-line"><span>{status.isError ? 'Reservation status' : pending || expired || holdElapsed ? 'Reservation total' : 'Amount due'}</span><strong>{status.isError ? 'Unavailable' : validSnapshot ? formatMoney(current.price) : 'Amount unavailable'}</strong></div>
    {!validSnapshot && <p role="alert">Reservation details couldn’t be verified. Contact the shop before paying.</p>}
    {expired ? <div role="status"><h3>Checkout expired</h3>{visitSummary}<p>This unpaid reservation expired. Choose another available time before starting a new checkout.</p></div> : holdElapsed && !pending ? <div role="status"><h3>Checkout time elapsed</h3><p>Check this reservation’s status before choosing another time. Do not submit another payment.</p></div> : !pending && !terminalFailure && <p>Time held for <strong className="tabular-nums">{Math.floor(remainingSeconds / 60)}:{String(remainingSeconds % 60).padStart(2, '0')}</strong>. Your appointment is confirmed after full payment is verified.</p>}
    {pending && <div role="status"><h3>Payment verification pending</h3><p>Your start time is not confirmed yet. Do not submit another payment while the outcome is being checked.</p></div>}
    {terminalFailure && !pending && <div role="status"><h3>Payment was not confirmed</h3><p>{canRetryCard ? 'This payment failed. You can try another card while this time is held.' : 'Contact the shop or check the reservation status before starting another checkout.'}</p>{canRetryCard && <ControlButton className="cp-secondary" onClick={() => {
      if (!canRetryCard) return
      attemptKey.current = crypto.randomUUID()
      submissionStarted.current = false
      setFailedAttemptChecked(false); setStarted(false); setResult(null); setStripe(null); setStripeError(false)
    }}>Try another card</ControlButton>}</div>}
    {status.isError && !pending && <p role="alert">Reservation status couldn’t load. Payment is paused until it can be checked.</p>}
    {canStart && capability?.provider === 'quickbooks_payments' && (approvedTokenUrl(capability.token_url) ? <QuickBooksPaymentPanel tokenUrl={capability.token_url!} onToken={start} onTokenHandlesResult onSuccess={() => undefined} submitLabel={`Pay ${formatMoney(current.price)} and reserve`} /> : <p role="alert">Secure checkout is unavailable. Contact the shop before paying.</p>)}
    {canStart && capability?.provider === 'stripe_connect' && <ControlButton className="cp-primary" onClick={() => { void start() }}>Start secure checkout</ControlButton>}
    {result?.provider === 'stripe_connect' && result.client_secret && result.stripe_account_id && !status.isError && !verificationPaused && !pending && !expired && !holdElapsed && !terminalFailure && (stripe ? <Elements stripe={stripe} options={{ clientSecret: result.client_secret, appearance: { theme: 'night' } }}><StripeBookingForm verify={verify} pause={() => setVerificationPaused(true)} /></Elements> : stripeError ? <p role="alert">Secure checkout couldn’t open. Check the reservation status before continuing.</p> : <LoadingLine>Opening secure checkout…</LoadingLine>)}
    {busy && <LoadingLine>Checking payment…</LoadingLine>}
    <ControlButton className="cp-secondary" disabled={busy || status.isFetching} onClick={() => { if (knownAttemptId) void verify(); else void status.refetch() }}>{busy || status.isFetching ? 'Checking…' : 'Check reservation status'}</ControlButton>
    {!started && !capability?.available && <p>Payment is unavailable. Contact the shop for help with this reservation.</p>}
    {expired && <ControlButton className="cp-secondary" onClick={onDone}>View visits</ControlButton>}
  </div>
}
