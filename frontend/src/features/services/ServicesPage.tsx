import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Search, Wrench, ClipboardCheck, Truck, AlertCircle, ChevronRight, Clock3, ArrowLeft } from 'lucide-react'
import { ControlButton, ControlInput } from '@/components/ui/Controls'
import PortalVehicleScope from '@/features/customer-portal/PortalVehicleScope'
import { Spinner } from '@/components/ui'
import { useAuthStore } from '@/stores/authStore'
import type { Service, ServiceCategory, Vehicle } from '@/types'
import { formatMoney } from '@/features/customer-portal/portal-ui'
import { getPortalItems, resolveVehicleScope, scopedPortalPath } from '@/features/customer-portal/portal-context'

const needs = [
  { name: 'Maintenance', detail: 'Oil changes and scheduled service', pattern: /maintenance|\bpm\b|oil|lube|lubrication|filter/i, icon: Wrench },
  { name: 'Inspection', detail: 'Annual and safety inspections', pattern: /inspect|\bdot\b|safety/i, icon: ClipboardCheck },
  { name: 'Brakes & tires', detail: 'Braking or tire concerns', pattern: /brake|braking|tire|tyre|wheel/i, icon: Truck },
  { name: 'Something wrong', detail: 'Warning light, noise, leak, or not sure', pattern: /diagnos|troubleshoot|warning|noise|leak|repair/i, icon: AlertCircle },
]

export default function ServicesPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const requestedVehicle = params.get('vehicle_id')
  const user = useAuthStore(state => state.user)
  const tenant = user?.tenant_id
  const customer = user?.customer_id
  const [category, setCategory] = useState('Common needs')
  const [search, setSearch] = useState('')
  const categoriesQuery = useQuery({ queryKey: ['service-categories', tenant, customer], queryFn: ({ signal }) => getPortalItems<ServiceCategory>('/services/categories', {}, signal) })
  const servicesQuery = useQuery({ queryKey: ['services', 'portal-all', tenant, customer], queryFn: ({ signal }) => getPortalItems<Service>('/services', {}, signal) })
  const vehiclesQuery = useQuery({ queryKey: ['vehicles', tenant, customer], queryFn: ({ signal }) => getPortalItems<Vehicle>('/vehicles', {}, signal) })
  const services = useMemo(() => (servicesQuery.data || []).filter(service => service.is_active), [servicesQuery.data])
  const vehicles = vehiclesQuery.data || []
  const scope = resolveVehicleScope(vehicles, requestedVehicle)
  const categories = categoriesQuery.data || []
  const matchingNeeds = needs.map(need => ({ ...need, services: services.filter(service => need.pattern.test(`${service.name} ${service.description || ''} ${categories.find(item => item.id === service.category_id)?.name || ''}`)) }))
  const visible = services.filter(service => {
    if (search.trim()) return `${service.name} ${service.description || ''}`.toLowerCase().includes(search.trim().toLowerCase())
    const need = matchingNeeds.find(item => item.name === category)
    return need ? need.services.some(item => item.id === service.id) : category === 'All services' || service.category_id === category
  })
  const readError = servicesQuery.isError || categoriesQuery.isError || vehiclesQuery.isError
  if (servicesQuery.isLoading || categoriesQuery.isLoading || vehiclesQuery.isLoading) return <div className="cp-root"><Spinner size="xl" /></div>
  if (readError) return <div className="cp-root" role="alert"><h1>Services unavailable</h1><p>We couldn’t load the service catalog and your vehicles.</p><ControlButton className="cp-secondary" onClick={() => { void servicesQuery.refetch(); void categoriesQuery.refetch(); void vehiclesQuery.refetch() }}>Try again</ControlButton></div>
  return <div className="cp-root">
    <Link data-db-control="action" className="cp-text cp-return-link" to={scopedPortalPath('/portal/appointments', scope.invalid ? null : scope.vehicleId)}><ArrowLeft size={16} aria-hidden="true"/>Back to appointments</Link>
    <div className="cp-title"><div><h1>Book a service</h1><p>What does your truck need?</p></div></div>
    <div className="cp-book-context"><div><strong>Vehicle</strong><PortalVehicleScope vehicles={vehicles} requested={requestedVehicle} onChange={id => setParams(id ? { vehicle_id: id } : {})} />{scope.invalid && <p role="alert">This vehicle is unavailable. Choose one of your vehicles to continue.</p>}{scope.ambiguous && <p role="alert">Vehicle details need review. Contact the shop before booking.</p>}{!scope.vehicle && !scope.invalid && !scope.ambiguous && <p>{vehicles.length ? 'Choose your vehicle during scheduling.' : 'No vehicles registered. Services without a vehicle are still available.'}</p>}</div></div>
    <label className="cp-search"><Search size={20} /><ControlInput aria-label="Search services or describe a concern" placeholder="Search services or describe a concern" value={search} onChange={event => setSearch(event.target.value)} /></label>
    <div className="cp-category-nav" aria-label="Service categories">{['Common needs', 'All services'].map(name => <ControlButton key={name} aria-pressed={category === name} className={category === name ? 'cp-active' : ''} onClick={() => setCategory(name)}>{name}</ControlButton>)}</div>
    {category === 'Common needs' && !search.trim() ? <div className="cp-needs">{matchingNeeds.map(need => <ControlButton controlKind="content" key={need.name} disabled={!need.services.length} onClick={() => setCategory(need.name)}><span className="cp-need-icon"><need.icon /></span><span><strong>{need.name}</strong><span>{need.services.length ? need.detail : 'No matching services available'}</span></span><ChevronRight size={20} /></ControlButton>)}</div> : <>
      <div className="cp-list-heading"><h2>{search.trim() ? `Results for “${search}”` : matchingNeeds.some(need => need.name === category) || category === 'All services' ? category : categories.find(item => item.id === category)?.name}</h2>{category !== 'All services' && <ControlButton className="cp-text" onClick={() => { setSearch(''); setCategory('Common needs') }}>All common needs</ControlButton>}</div>
      {category === 'All services' && !search.trim() && <div className="cp-category-nav">{categories.filter(item => services.some(service => service.category_id === item.id)).map(item => <ControlButton key={item.id} className="cp-text" onClick={() => setCategory(item.id)}>{item.name}</ControlButton>)}</div>}
      <div className="cp-service-list">{visible.map(service => <article key={service.id}><div><h3>{service.name}</h3>{service.description && <p>{service.description}</p>}<p>{formatMoney(service.computed_total_price)}</p></div><span className="cp-duration"><Clock3 size={15} />{service.duration_minutes} min</span><ControlButton className="cp-secondary" disabled={scope.invalid || (service.requires_vehicle && scope.ambiguous)} onClick={() => navigate(scopedPortalPath(`/portal/book/${service.id}`, scope.vehicleId))}>Choose<ChevronRight size={15} /></ControlButton></article>)}</div>
      {!visible.length && <div className="cp-panel cp-empty"><Search /><h2>No matching services</h2><p>Try another search or browse all services.</p><ControlButton className="cp-secondary" onClick={() => { setSearch(''); setCategory('All services') }}>All services</ControlButton></div>}
    </>}
    {!services.length && <div className="cp-panel cp-empty"><h2>No services available</h2><p>Contact the shop for help scheduling a visit.</p></div>}
  </div>
}
