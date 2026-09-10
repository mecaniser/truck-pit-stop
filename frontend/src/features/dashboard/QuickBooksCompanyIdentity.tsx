import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Copy } from 'lucide-react'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'

interface Connection {
  is_connected: boolean
  realm_id: string | null
  connected_at: string | null
}

interface CompanyIdentity {
  status: 'available' | 'not_connected' | 'unavailable'
  environment: 'production' | 'sandbox' | 'unknown'
  realm_id: string | null
  company: {
    name: string | null
    legal_name: string | null
    address_lines: string[]
    email: string | null
    phone: string | null
  } | null
}

export default function QuickBooksCompanyIdentity({ open, connection }: { open: boolean; connection: Connection }) {
  const { user } = useAuthStore()
  const [copyStatus, setCopyStatus] = useState('')
  const { data, isLoading } = useQuery<CompanyIdentity>({
    queryKey: ['quickbooks-company-identity', user?.id, user?.tenant_id, connection.realm_id, connection.connected_at],
    queryFn: async () => (await api.get('/quickbooks/company-identity')).data,
    enabled: Boolean(open && connection.is_connected && connection.realm_id && user?.tenant_id),
    staleTime: 5 * 60 * 1000,
    retry: false,
  })

  if (!open || !connection.is_connected) return null
  if (isLoading) return <p role="status" className="mb-5 text-sm text-[var(--text-secondary)]">Loading connected company…</p>
  const company = data?.status === 'available' && data.realm_id === connection.realm_id ? data.company : null
  if (!company) return <p role="status" className="mb-5 text-sm text-[var(--text-secondary)]">Company details are temporarily unavailable. Your QuickBooks connection has not been changed.</p>

  return (
    <section aria-label="Connected QuickBooks company" className="mb-5 min-w-0 space-y-3 text-sm text-[var(--text-primary)]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="break-words text-base font-semibold">{company.name || company.legal_name || 'Connected QuickBooks company'}</h3>
        {data?.environment !== 'unknown' && <span className="text-xs text-[var(--text-secondary)]">{data?.environment === 'production' ? 'Production' : 'Sandbox'}</span>}
      </div>
      {company.legal_name && company.name && company.legal_name !== company.name && <p className="break-words text-[var(--text-secondary)]">Legal name: {company.legal_name}</p>}
      {company.address_lines.length > 0 && <address className="break-words not-italic text-[var(--text-secondary)]">{company.address_lines.map((line, index) => <div key={index}>{line}</div>)}</address>}
      {(company.email || company.phone) && <div className="flex flex-wrap gap-x-5 gap-y-1 text-[var(--text-secondary)]">
        {company.email && <p className="min-w-0 break-all">{company.email}</p>}
        {company.phone && <p>{company.phone}</p>}
      </div>}
      <div className="flex flex-wrap items-center gap-x-3 text-xs text-[var(--text-secondary)]">
        <p className="min-w-0 break-all">Company ID: <span className="select-all tabular-nums">{connection.realm_id}</span></p>
        <button type="button" aria-label="Copy QuickBooks company ID" className="inline-flex min-h-11 items-center gap-1.5 rounded px-2 hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-500)]" onClick={async () => {
          try { await navigator.clipboard.writeText(connection.realm_id!); setCopyStatus('Company ID copied') }
          catch { setCopyStatus('Unable to copy. Select the company ID to copy it manually.') }
        }}><Copy className="h-3.5 w-3.5" aria-hidden="true" />Copy</button>
        <span role="status">{copyStatus}</span>
      </div>
    </section>
  )
}
