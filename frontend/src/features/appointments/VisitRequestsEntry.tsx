import { Link } from 'react-router-dom'
import { ClipboardList } from 'lucide-react'
import { getAuthenticatedSessionIdentity, useAuthStore } from '@/stores/authStore'
import { useStaffRequests, visitRequestStaffRoles } from './staffVisitRequestQueries'
import './visit-requests.css'
export default function VisitRequestsEntry() {
  const user = useAuthStore(state => state.user)
  const identity = useAuthStore(getAuthenticatedSessionIdentity)
  const allowed = visitRequestStaffRoles.includes(user?.role || '')
  const query = useStaffRequests(identity, allowed)
  if (!allowed || !identity) return null
  const count = query.isError ? null : query.data?.filter(row => ['requested', 'availability_review'].includes(row.status)).length
  return <section className="visit-requests-entry" aria-label="Service visit intake"><div><strong>Service visits</strong><p>{query.isError ? 'Requests couldn’t load' : count === undefined ? 'Checking requests…' : `${count} ${count === 1 ? 'request' : 'requests'} awaiting review`}</p></div><Link data-db-control="action" className="visit-request-button" to="/dashboard/visit-requests"><ClipboardList size={17} aria-hidden="true"/>Review visits</Link></section>
}
