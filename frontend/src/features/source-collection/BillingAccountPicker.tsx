import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import CustomerSelect, { type CustomerSelectItem } from '@/components/CustomerSelect'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'

export default function BillingAccountPicker({ sourceCustomerId, sourceCustomerName, value, valueName, onChange }: {
  sourceCustomerId: string; sourceCustomerName: string; value: string; valueName?: string; onChange: (id: string, name?: string) => void
}) {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<CustomerSelectItem | null>(null)
  const query = useDebouncedValue(search.trim(), 250)
  const user = useAuthStore(state => state.user)
  const { data = [], isFetching, isError } = useQuery<CustomerSelectItem[]>({
    queryKey: ['collection-bill-to', user?.tenant_id, user?.id, query],
    queryFn: async ({ signal }) => (await api.get('/customers/typeahead', { signal, params: { q: query || undefined, limit: 20 } })).data,
    retry: false,
  })
  const customers = useMemo(() => {
    const result = new Map<string, CustomerSelectItem>()
    result.set(sourceCustomerId, { id: sourceCustomerId, first_name: '', last_name: '', company_name: sourceCustomerName })
    if (valueName) result.set(value, { id: value, first_name: '', last_name: '', company_name: valueName })
    data.forEach(customer => result.set(customer.id, customer))
    if (selected) result.set(selected.id, selected)
    return [...result.values()]
  }, [sourceCustomerId, sourceCustomerName, value, valueName, data, selected])
  return <div className="mt-3 space-y-2">
    <p className="text-xs font-semibold">Customer account for this invoice</p>
    <CustomerSelect customers={customers} value={value} allowAddNew={false} onQueryChange={setSearch} searchLoading={isFetching} onChange={id => {
      const customer = customers.find(customer => customer.id === id) ?? null
      setSelected(customer)
      onChange(id, customer?.company_name || `${customer?.first_name ?? ''} ${customer?.last_name ?? ''}`.trim())
    }} />
    <p className="text-xs text-slate-500">A different account requires a recorded review confirming the same legal business.</p>
    {isError && <p role="alert" className="text-xs text-red-700">Customer search unavailable. Retry the search before selecting a different account.</p>}
  </div>
}
