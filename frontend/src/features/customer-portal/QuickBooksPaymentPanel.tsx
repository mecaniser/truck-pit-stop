import { FormEvent, useState } from 'react'
import { CreditCard } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../../lib/api'

interface QuickBooksPaymentPanelProps {
  invoiceId: string
  tokenUrl: string
  onSuccess: () => void
}

export default function QuickBooksPaymentPanel({ invoiceId, tokenUrl, onSuccess }: QuickBooksPaymentPanelProps) {
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = event.currentTarget
    const values = new FormData(form)
    const expiry = String(values.get('expiry') || '').split('/').map(value => value.trim())
    if (expiry.length !== 2 || !expiry[0] || !expiry[1]) {
      setError('Enter the expiry date as MM / YYYY.')
      return
    }

    setIsProcessing(true)
    setError(null)
    try {
      // Intuit receives card data directly. DieselBridge receives only the opaque token.
      const tokenResponse = await fetch(tokenUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          card: {
            number: values.get('number'),
            cvc: values.get('cvc'),
            expMonth: expiry[0],
            expYear: expiry[1],
            name: values.get('name'),
            address: {
              country: 'US',
              postalCode: values.get('postalCode'),
            },
          },
        }),
      })
      const tokenPayload = await tokenResponse.json().catch(() => null)
      form.reset()
      if (!tokenResponse.ok || typeof tokenPayload?.value !== 'string') {
        throw new Error('QuickBooks could not securely prepare this payment.')
      }

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
    <form onSubmit={submit} className="space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="text-sm text-gray-300 sm:col-span-2">
          Name on card
          <input required name="name" autoComplete="cc-name" className="mt-1 w-full rounded-lg border border-gray-600 bg-slate-900 px-3 py-2 text-white" />
        </label>
        <label className="text-sm text-gray-300 sm:col-span-2">
          Card number
          <input required name="number" inputMode="numeric" autoComplete="cc-number" className="mt-1 w-full rounded-lg border border-gray-600 bg-slate-900 px-3 py-2 text-white" />
        </label>
        <label className="text-sm text-gray-300">
          Expiry
          <input required name="expiry" inputMode="numeric" autoComplete="cc-exp" placeholder="MM / YYYY" className="mt-1 w-full rounded-lg border border-gray-600 bg-slate-900 px-3 py-2 text-white" />
        </label>
        <label className="text-sm text-gray-300">
          Security code
          <input required name="cvc" inputMode="numeric" autoComplete="cc-csc" className="mt-1 w-full rounded-lg border border-gray-600 bg-slate-900 px-3 py-2 text-white" />
        </label>
        <label className="text-sm text-gray-300 sm:col-span-2">
          Billing ZIP code
          <input required name="postalCode" autoComplete="postal-code" className="mt-1 w-full rounded-lg border border-gray-600 bg-slate-900 px-3 py-2 text-white" />
        </label>
      </div>
      {error && <p className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">{error}</p>}
      <button type="submit" disabled={isProcessing} className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 py-3 font-semibold text-white hover:bg-emerald-700 disabled:bg-gray-600">
        <CreditCard className="h-5 w-5" />
        {isProcessing ? 'Processing...' : 'Pay with QuickBooks'}
      </button>
    </form>
  )
}
