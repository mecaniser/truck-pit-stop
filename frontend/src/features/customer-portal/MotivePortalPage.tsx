import { Link, useSearchParams } from 'react-router-dom'
import { Link2 } from 'lucide-react'
import { MotiveIntegrationWorkspace } from '../fleet/MotiveIntegrationPanel'
import { useMotiveCompanies } from '../fleet/motiveQueries'

export function MotivePortalEntry() {
  const companies = useMotiveCompanies()
  if (companies.isError || !companies.data?.items?.length) return null
  return <Link to="/portal/integrations" className="inline-flex min-h-[44px] items-center gap-2 rounded-lg px-3 text-sm font-semibold text-[#c9bfff]"><Link2 size={16} />Integrations</Link>
}

export default function MotivePortalPage() {
  const [params] = useSearchParams()
  return <section className="motive-portal max-w-3xl text-slate-100">
    <h1 className="mb-2 text-2xl font-bold">Truck integrations</h1>
    <p className="mb-6 text-sm text-slate-400">Connect your company’s Motive devices and review truck data.</p>
    <MotiveIntegrationWorkspace initialCompanyId={params.get('company') ?? ''} />
  </section>
}
