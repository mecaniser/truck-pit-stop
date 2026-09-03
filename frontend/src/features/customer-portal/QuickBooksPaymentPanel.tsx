import { ChangeEvent, FormEvent, useState } from 'react'
import { CreditCard } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../../lib/api'

interface QuickBooksPaymentPanelProps {
  invoiceId?: string
  tokenUrl: string
  onSuccess: () => void
  onToken?: (token: string) => Promise<void>
  submitLabel?: string
  tone?: 'dark' | 'light'
}

type CardFields = {
  name: string
  number: string
  expiry: string
  cvc: string
  postalCode: string
}

type CardFieldErrors = Partial<Record<keyof CardFields, string>>

const EMPTY_FIELDS: CardFields = { name: '', number: '', expiry: '', cvc: '', postalCode: '' }

const digitsOnly = (value: string, limit: number) => value.replace(/\D/g, '').slice(0, limit)

const formatCardNumber = (value: string) => digitsOnly(value, 19).replace(/(.{4})/g, '$1 ').trim()

const formatExpiry = (value: string) => {
  const digits = digitsOnly(value, 6)
  return digits.length > 2 ? `${digits.slice(0, 2)} / ${digits.slice(2)}` : digits
}

const formatPostalCode = (value: string) => {
  const digits = digitsOnly(value, 9)
  return digits.length > 5 ? `${digits.slice(0, 5)}-${digits.slice(5)}` : digits
}

const validateFields = (fields: CardFields): CardFieldErrors => {
  const errors: CardFieldErrors = {}
  const cardDigits = digitsOnly(fields.number, 19)
  const expiryDigits = digitsOnly(fields.expiry, 6)
  const cvcDigits = digitsOnly(fields.cvc, 4)
  const postalDigits = digitsOnly(fields.postalCode, 9)

  if (!fields.name.trim()) errors.name = 'Enter the name shown on the card.'
  if (cardDigits.length < 13 || cardDigits.length > 19) errors.number = 'Enter a valid 13–19 digit card number.'

  if (expiryDigits.length !== 6) {
    errors.expiry = 'Enter expiry as MM / YYYY.'
  } else {
    const month = Number(expiryDigits.slice(0, 2))
    const year = Number(expiryDigits.slice(2))
    const now = new Date()
    const currentMonth = now.getMonth() + 1
    const currentYear = now.getFullYear()
    if (month < 1 || month > 12 || year < currentYear || (year === currentYear && month < currentMonth)) {
      errors.expiry = 'Enter a valid future expiry date.'
    }
  }

  if (cvcDigits.length < 3 || cvcDigits.length > 4) errors.cvc = 'Enter a 3 or 4 digit security code.'
  if (![5, 9].includes(postalDigits.length)) errors.postalCode = 'Enter a 5 digit ZIP or ZIP+4.'
  return errors
}

export default function QuickBooksPaymentPanel({ invoiceId, tokenUrl, onSuccess, onToken, submitLabel, tone = 'dark' }: QuickBooksPaymentPanelProps) {
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fields, setFields] = useState<CardFields>(EMPTY_FIELDS)
  const [fieldErrors, setFieldErrors] = useState<CardFieldErrors>({})
  const isDark = tone === 'dark'
  const labelClass = isDark ? 'text-[#c9cdd8]' : 'text-slate-600'
  const inputClass = isDark
    ? 'border-[#272d3d] bg-[#161a26] text-white focus:border-[#8b7cf7] focus:ring-[#8b7cf7]'
    : 'border-slate-300 bg-white text-slate-950 placeholder:text-slate-400 focus:border-[var(--accent-600,#b9472f)] focus:ring-[var(--accent-600,#b9472f)]'

  const updateField = (field: keyof CardFields, formatter?: (value: string) => string) => (event: ChangeEvent<HTMLInputElement>) => {
    const value = formatter ? formatter(event.target.value) : event.target.value.slice(0, 64)
    setFields(current => ({ ...current, [field]: value }))
    setFieldErrors(current => ({ ...current, [field]: undefined }))
    setError(null)
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const validationErrors = validateFields(fields)
    if (Object.keys(validationErrors).length > 0) {
      setFieldErrors(validationErrors)
      setError('Check the highlighted payment fields.')
      return
    }

    const cardDigits = digitsOnly(fields.number, 19)
    const expiryDigits = digitsOnly(fields.expiry, 6)

    setIsProcessing(true)
    setError(null)
    try {
      // Intuit receives card data directly. DieselBridge receives only the opaque token.
      const tokenResponse = await fetch(tokenUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          card: {
            number: cardDigits,
            cvc: digitsOnly(fields.cvc, 4),
            expMonth: expiryDigits.slice(0, 2),
            expYear: expiryDigits.slice(2),
            name: fields.name.trim(),
            address: {
              country: 'US',
              postalCode: fields.postalCode,
            },
          },
        }),
      })
      const tokenPayload = await tokenResponse.json().catch(() => null)
      if (!tokenResponse.ok || typeof tokenPayload?.value !== 'string') {
        throw new Error('QuickBooks could not securely prepare this payment.')
      }
      setFields(EMPTY_FIELDS)

      if (onToken) {
        await onToken(tokenPayload.value)
        toast.success('Payment successful!')
        onSuccess()
        return
      }
      if (!invoiceId) throw new Error('The invoice payment target is unavailable.')
      const response = await api.post('/quickbooks/payments/charge', {
        invoice_id: invoiceId,
        token: tokenPayload.value,
        idempotency_key: crypto.randomUUID(),
      })
      const result = response.data as { status: string; message: string }
      if (['CAPTURED', 'SUCCEEDED', 'COMPLETED'].includes(result.status)) {
        toast.success(result.message || 'Payment successful!')
        onSuccess()
      } else {
        toast(result.message || 'Your payment is processing.')
      }
    } catch (cause: unknown) {
      const detail = typeof cause === 'object' && cause && 'response' in cause
        ? (cause as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : null
      setError(typeof detail === 'string' ? detail : 'Payment could not be completed. Please try another method.')
    } finally {
      setIsProcessing(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className={`text-sm sm:col-span-2 ${labelClass}`}>
          Name on card
          <input required name="name" autoComplete="cc-name" maxLength={64} value={fields.name} onChange={updateField('name')} aria-invalid={Boolean(fieldErrors.name)} aria-describedby={fieldErrors.name ? 'qbp-name-error' : undefined} className={`mt-1 h-12 w-full rounded-xl border px-3 text-base outline-none focus:ring-2 ${inputClass}`} />
          {fieldErrors.name && <span id="qbp-name-error" className="mt-1 block text-xs text-red-600">{fieldErrors.name}</span>}
        </label>
        <label className={`text-sm sm:col-span-2 ${labelClass}`}>
          Card number
          <input required name="number" type="text" inputMode="numeric" autoComplete="cc-number" maxLength={23} value={fields.number} onChange={updateField('number', formatCardNumber)} aria-invalid={Boolean(fieldErrors.number)} aria-describedby={fieldErrors.number ? 'qbp-number-error' : undefined} className={`mt-1 h-12 w-full rounded-xl border px-3 font-mono text-base tracking-wide outline-none focus:ring-2 ${inputClass}`} />
          {fieldErrors.number && <span id="qbp-number-error" className="mt-1 block text-xs text-red-600">{fieldErrors.number}</span>}
        </label>
        <label className={`text-sm ${labelClass}`}>
          Expiry
          <input required name="expiry" type="text" inputMode="numeric" autoComplete="cc-exp" placeholder="MM / YYYY" maxLength={9} value={fields.expiry} onChange={updateField('expiry', formatExpiry)} aria-invalid={Boolean(fieldErrors.expiry)} aria-describedby={fieldErrors.expiry ? 'qbp-expiry-error' : undefined} className={`mt-1 h-12 w-full rounded-xl border px-3 font-mono text-base outline-none focus:ring-2 ${inputClass}`} />
          {fieldErrors.expiry && <span id="qbp-expiry-error" className="mt-1 block text-xs text-red-600">{fieldErrors.expiry}</span>}
        </label>
        <label className={`text-sm ${labelClass}`}>
          Security code
          <input required name="cvc" type="password" inputMode="numeric" autoComplete="cc-csc" maxLength={4} value={fields.cvc} onChange={updateField('cvc', value => digitsOnly(value, 4))} aria-invalid={Boolean(fieldErrors.cvc)} aria-describedby={fieldErrors.cvc ? 'qbp-cvc-error' : undefined} className={`mt-1 h-12 w-full rounded-xl border px-3 font-mono text-base outline-none focus:ring-2 ${inputClass}`} />
          {fieldErrors.cvc && <span id="qbp-cvc-error" className="mt-1 block text-xs text-red-600">{fieldErrors.cvc}</span>}
        </label>
        <label className={`text-sm sm:col-span-2 ${labelClass}`}>
          Billing ZIP code
          <input required name="postalCode" type="text" inputMode="numeric" autoComplete="postal-code" maxLength={10} value={fields.postalCode} onChange={updateField('postalCode', formatPostalCode)} aria-invalid={Boolean(fieldErrors.postalCode)} aria-describedby={fieldErrors.postalCode ? 'qbp-postal-error' : undefined} className={`mt-1 h-12 w-full rounded-xl border px-3 font-mono text-base outline-none focus:ring-2 ${inputClass}`} />
          {fieldErrors.postalCode && <span id="qbp-postal-error" className="mt-1 block text-xs text-red-600">{fieldErrors.postalCode}</span>}
        </label>
      </div>
      {error && <p className={`rounded-xl border p-3 text-sm ${isDark ? 'border-red-500/30 bg-red-500/10 text-red-300' : 'border-red-200 bg-red-50 text-red-700'}`}>{error}</p>}
      <button type="submit" disabled={isProcessing} className={`flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl px-4 font-extrabold hover:brightness-110 disabled:opacity-60 ${isDark ? 'bg-[#8b7cf7] text-[#0e1118]' : 'bg-[var(--accent-600,#b9472f)] text-white'}`}>
        <CreditCard className="h-5 w-5" />
        {isProcessing ? 'Processing...' : submitLabel || 'Submit secure payment'}
      </button>
    </form>
  )
}
