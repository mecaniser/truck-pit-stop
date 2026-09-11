import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { createIdempotencyKey, paymentApiError } from '@/features/payments/api'

export interface CustomerTaxExemption {
  tax_exempt: boolean
  support_reference: string | null
  version: number
  updated_at: string | null
}

function CustomerTaxExemptionEditor({ customerId, scope }: { customerId: string; scope: string }) {
  const client = useQueryClient()
  const [reloadVersion, setReloadVersion] = useState(0)
  const [saved, setSaved] = useState(false)
  const queryKey = ['customer-tax-exemption', scope, customerId]
  const query = useQuery({
    queryKey,
    queryFn: async () => (await api.get<CustomerTaxExemption>(`/customers/${customerId}/tax-exemption`)).data,
    retry: false,
  })
  if (query.isLoading) return <p role="status" className="text-sm text-slate-600">Loading customer tax setting…</p>
  if (query.error || !query.data) return <div role="alert" className="text-sm text-slate-700">
    <p>Customer tax setting is unavailable. No changes were made.</p>
    <button type="button" onClick={() => void query.refetch()} className="min-h-11 font-semibold underline underline-offset-4">Retry tax setting</button>
  </div>
  return <><TaxSettingForm key={`${scope}:${customerId}:${query.data.version}:${reloadVersion}`} initial={query.data} customerId={customerId}
    onSaved={next => {
      setSaved(true)
      client.setQueryData(queryKey, next)
      for (const key of ['customer', 'customers', 'repair-order-detail', 'price-build', 'quote']) void client.invalidateQueries({ queryKey: [key] })
    }}
    onEdit={() => setSaved(false)}
    onReload={() => { void query.refetch().then(result => { if (!result.error) { setSaved(false); setReloadVersion(value => value + 1) } }) }} />
    {saved && <p role="status" className="text-sm text-emerald-800">Tax setting saved.</p>}
  </>
}

function TaxSettingForm({ customerId, initial, onSaved, onReload, onEdit }: {
  customerId: string
  initial: CustomerTaxExemption
  onSaved: (next: CustomerTaxExemption) => void
  onReload: () => void
  onEdit: () => void
}) {
  const [exempt, setExempt] = useState(initial.tax_exempt)
  const [reference, setReference] = useState(initial.support_reference ?? '')
  const request = useRef<{ key: string; body: { tax_exempt: boolean; support_reference: string | null; expected_version: number } } | null>(null)
  const save = useMutation({
    mutationFn: async () => {
      request.current ??= { key: createIdempotencyKey(), body: {
        tax_exempt: exempt, support_reference: exempt ? reference.trim() || null : null, expected_version: initial.version,
      } }
      return (await api.put<CustomerTaxExemption>(`/customers/${customerId}/tax-exemption`, request.current.body,
        { headers: { 'Idempotency-Key': request.current.key } })).data
    },
    onSuccess: next => { request.current = null; onSaved(next) },
  })
  const changed = exempt !== initial.tax_exempt || (exempt ? reference.trim() || null : null) !== initial.support_reference
  const locked = save.isPending || Boolean(save.error)
  return <section aria-label="Customer sales tax" className="border-y border-slate-200 py-4 text-slate-900">
    <label className="flex min-h-11 cursor-pointer items-start gap-3 py-2">
      <input type="checkbox" checked={exempt} disabled={locked} onChange={event => { setExempt(event.target.checked); onEdit() }}
        className="mt-0.5 h-5 w-5 shrink-0 accent-emerald-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2" />
      <span><span className="block text-sm font-semibold">Customer is tax exempt</span>
        <span className="mt-1 block text-xs leading-relaxed text-slate-600">Applies to new invoices billed to this customer, for any payment method. Issued invoices stay unchanged.</span>
      </span>
    </label>
    {exempt && <label className="mt-3 block text-xs font-semibold text-slate-600">Certificate or supporting reference (optional)
      <input value={reference} disabled={locked} maxLength={255} onChange={event => { setReference(event.target.value); onEdit() }}
        className="mt-2 min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 disabled:opacity-60" />
    </label>}
    {save.error && <div role="alert" className="mt-3 text-sm text-red-800">
      <p>{paymentApiError(save.error, 'The change was not verified. Retry the same change or reload the saved setting.').message}</p>
      <button type="button" onClick={onReload} className="min-h-11 rounded-lg font-semibold underline underline-offset-4">Reload saved tax setting</button>
    </div>}
    {(changed || save.error) && <button type="button" onClick={() => save.mutate()} disabled={save.isPending} className="mt-3 min-h-11 rounded-xl bg-emerald-800 px-4 text-sm font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2 disabled:opacity-60">
      {save.isPending ? 'Saving…' : save.error ? 'Retry tax setting' : 'Save tax setting'}
    </button>}
  </section>
}

export default function CustomerTaxExemptionControl({ customerId }: { customerId: string }) {
  const user = useAuthStore(state => state.user)
  if (!user || !(user.role === 'garage_owner' || (user.role === 'garage_admin' && user.permissions?.payments === true))) return null
  const scope = `${user.tenant_id}:${user.id}`
  return <CustomerTaxExemptionEditor key={`${scope}:${customerId}`} customerId={customerId} scope={scope} />
}
