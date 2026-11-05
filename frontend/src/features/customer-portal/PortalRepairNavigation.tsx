import { Link, useLocation } from 'react-router-dom'
import { scopedPortalPath } from './portal-context'

export default function PortalRepairNavigation({ vehicleId }: { vehicleId: string | null }) {
  const { pathname, search } = useLocation()
  const active = pathname === '/portal/appointments' ? 'appointments'
    : new URLSearchParams(search).get('view') === 'active' ? 'current' : 'history'
  const sections = [
    { id: 'current', label: 'Current repairs', path: '/portal/repairs?view=active' },
    { id: 'appointments', label: 'Appointments', path: '/portal/appointments' },
    { id: 'history', label: 'Repair history', path: '/portal/repairs' },
  ]
  return <nav aria-label="Repair sections" className="cp-repair-navigation">
    {sections.map(section => <Link key={section.id} data-db-control="action"
      aria-current={active === section.id ? 'page' : undefined}
      to={scopedPortalPath(section.path, vehicleId)}>{section.label}</Link>)}
  </nav>
}
