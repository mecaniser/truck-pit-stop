import { useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { getPortalItems, resolveVehicleScope, scopedPortalPath, vehicleIdentity } from '@/features/customer-portal/portal-context'
import PortalVehicleScope from '@/features/customer-portal/PortalVehicleScope'
import { ControlButton } from '@/components/ui/Controls'
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarDays } from 'lucide-react'
import { Link } from 'react-router-dom'
import { format } from 'date-fns'

import { Spinner } from '@/components/ui'
import api from '@/lib/api'
import type { Appointment, Vehicle } from '@/types'
import { DateBlock, formatMoney, Pill } from '@/features/customer-portal/portal-ui'
import type { VisitRequestResult } from '@/features/booking/booking-contract'

const statusStyles: Record<string, string> = {
  pending: 'border-[#8b7cf7]/35 bg-[#8b7cf7]/10 text-[#c9bfff]',
  confirmed: 'border-[#8b7cf7]/35 bg-[#8b7cf7]/10 text-[#c9bfff]',
  in_progress: 'border-[#f0b959]/35 bg-[#f0b959]/10 text-[#f0b959]',
  completed: 'border-[#3ecf6f]/30 bg-[#3ecf6f]/10 text-[#3ecf6f]',
  cancelled: 'border-[#ff6b6e]/30 bg-[#ff6b6e]/10 text-[#ff8b8d]',
  no_show: 'border-[#272d3d] bg-[#191d2a] text-[#8b92a5]',
}

export default function AppointmentsPage() {
  const queryClient = useQueryClient()
  const user = useAuthStore(state=>state.user)
  const [params,setParams] = useSearchParams()
  const requestedVehicle=params.get('vehicle_id')
  const requestedAppointment=params.get('appointment_id')
  const [filter, setFilter] = useState<'upcoming' | 'past' | 'all'>('upcoming')

  const { data: appointments = [], isLoading, isError, refetch } = useQuery<Appointment[]>({
    queryKey: ['appointments',user?.tenant_id,user?.customer_id],
    queryFn: ({ signal }) => getPortalItems<Appointment>('/appointments', {}, signal),
  })
  const vehiclesQuery = useQuery({queryKey:['vehicles',user?.tenant_id,user?.customer_id],queryFn: ({ signal }) => getPortalItems<Vehicle>('/vehicles', {}, signal)})
  const requestsQuery = useQuery({ queryKey: ['visit-requests', user?.tenant_id, user?.customer_id], queryFn: ({ signal }) => getPortalItems<VisitRequestResult>('/visit-requests', {}, signal) })
  const vehicles=vehiclesQuery.data || []
  const scope=resolveVehicleScope(vehicles,requestedVehicle)
  const requests = requestsQuery.isError ? [] : (requestsQuery.data || []).filter(request => request.status !== 'withdrawn' && (!scope.vehicleId || !request.vehicle_id || request.vehicle_id === scope.vehicleId))

  const cancelMutation = useMutation({
    mutationFn: async (appointmentId: string) => api.post(`/appointments/${appointmentId}/cancel`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['appointments',user?.tenant_id,user?.customer_id] }),
  })

  const filtered = useMemo(() => appointments
    .filter(appointment => {
      if(scope.vehicleId && appointment.vehicle_id && appointment.vehicle_id!==scope.vehicleId) return false
      if(requestedAppointment) return appointment.id===requestedAppointment
      const past = new Date(appointment.scheduled_at) < new Date()
        || ['cancelled', 'completed', 'no_show'].includes(appointment.status)
      if (filter === 'upcoming') return !past
      if (filter === 'past') return past
      return true
    })
    .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime()), [appointments, filter, scope.vehicleId, requestedAppointment])

  if(isLoading || vehiclesQuery.isLoading) return <Spinner size="xl"/>
  if(isError || vehiclesQuery.isError) return <div role="alert"><h1>Appointments unavailable</h1><p>We couldn’t load your visits. Please try again.</p><ControlButton onClick={()=>{void refetch();void vehiclesQuery.refetch()}}>Try again</ControlButton></div>
  if(scope.invalid) return <div role="alert"><h1>Vehicle unavailable</h1><PortalVehicleScope vehicles={vehicles} requested={requestedVehicle} onChange={id=>setParams(id?{vehicle_id:id}:{})}/></div>

  return (
    <div className="space-y-4">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-extrabold tracking-[-0.01em]">Appointments</h1>
          <p className="mt-1 text-[13px] text-[#8b92a5]">
            {scope.vehicle ? `Visits for ${vehicleIdentity(scope.vehicle)} and your account` : 'Your reservations and visit requests'}
          </p>
        </div>
        <div className="flex gap-2 overflow-x-auto">
          {(['upcoming', 'past', 'all'] as const).map(value => (
            <Pill key={value} active={filter === value} onClick={() => setFilter(value)}>
              {value.charAt(0).toUpperCase() + value.slice(1)}
            </Pill>
          ))}
        </div>
      </header>

      <section aria-label="Visit requests" className="space-y-3">
        <h2 className="text-base font-bold">Awaiting shop confirmation</h2>
        {requestsQuery.isLoading ? <p role="status">Loading visit requests…</p> : requestsQuery.isError ? <div role="alert"><p>Visit requests couldn’t load.</p><ControlButton className="cp-secondary" onClick={() => { void requestsQuery.refetch() }}>Try requests again</ControlButton></div> : requests.length ? requests.map(request => <article key={request.id} className="cp-panel p-4 space-y-2"><h3 className="font-bold">{request.service_name || 'Service visit request'}</h3><p className="text-sm text-[#a2a9bb]">{vehicles.some(vehicle => vehicle.id === request.vehicle_id) ? vehicleIdentity(vehicles.find(vehicle => vehicle.id === request.vehicle_id)!) : 'Vehicle not specified'}</p><p className="text-sm">The shop will confirm availability. No start time is reserved.</p>{request.preferred_date && <p className="text-sm">Preferred date: <time dateTime={request.preferred_date}>{format(new Date(`${request.preferred_date}T12:00:00`), 'MMM d, yyyy')}</time></p>}<p className="text-xs">Request {request.request_reference}</p></article>) : <p className="text-sm text-[#a2a9bb]">No visit requests awaiting confirmation.</p>}
      </section>

      {filtered.length === 0 ? (
        <section className="rounded-2xl border border-[#232939] bg-[#161a26] px-5 py-9 text-center sm:px-6">
          <div className="mx-auto flex h-[46px] w-[46px] items-center justify-center rounded-xl border border-[#272d3d] bg-[#12161f] text-[#5c6375]">
            <CalendarDays className="h-5 w-5" />
          </div>
          <h2 className="mt-3.5 text-base font-extrabold">{requestedAppointment ? 'Visit unavailable' : <>No {filter === 'all' ? '' : filter} visits</>}</h2>
          <p className="mx-auto mt-1.5 max-w-[420px] text-[13px] leading-5 text-[#8b92a5]">
            Your appointments will appear here as soon as a service is booked.
          </p>
        </section>
      ) : (
        <div className="space-y-2">
          {filtered.map(appointment => {
            const paymentState = appointment.booking_payment_state
            const verifiedBooking = Boolean(paymentState)
            const paymentLabels: Record<string, string> = { unpaid_hold: 'Payment needed · time not confirmed', expired_unpaid: 'Checkout expired', payment_processing: 'Payment verification pending', payment_received_review: 'Payment received · shop review needed', refund_pending: 'Refund review pending', refunded: 'Refund recorded', paid: appointment.status === 'confirmed' && appointment.receipt ? 'Confirmed · payment verified' : 'Payment received · confirmation unavailable' }
            const canCancel = ['pending', 'confirmed'].includes(appointment.status)
              && new Date(appointment.scheduled_at) >= new Date()
              && !verifiedBooking
            return (
              <article key={appointment.id} className="flex items-center gap-3 rounded-xl border border-[#232939] bg-[#161a26] p-3 hover:border-[#343b52] sm:gap-4 sm:px-4">
                <DateBlock value={appointment.scheduled_at} />
                <div className="min-w-0 flex-1">
                  <p className="mb-1 text-xs text-[#a4abba]">{vehicles.find(v=>v.id===appointment.vehicle_id) ? vehicleIdentity(vehicles.find(v=>v.id===appointment.vehicle_id)!) : 'Account visit · Vehicle not specified'}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="truncate text-[13px] font-bold sm:text-sm">{appointment.service_name}</h2>
                    <span className={`rounded-md border px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.05em] ${statusStyles[appointment.status] || statusStyles.pending}`}>
                      {paymentState ? paymentLabels[paymentState] || 'Reservation needs review' : appointment.status.replace('_', ' ')}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-[#8b92a5]">{format(new Date(appointment.scheduled_at), 'h:mm a')} · {appointment.duration_minutes} min</p>
                  <p className="mt-0.5 truncate text-[11px] text-[#a2a9bb]">{verifiedBooking ? 'Booking reference' : 'Confirmation'} {appointment.confirmation_number}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-sm font-extrabold tabular-nums">{formatMoney(appointment.price)}</p>
                  {verifiedBooking && <Link className="cp-text" to={scopedPortalPath(`/portal/book/${encodeURIComponent(appointment.service_id)}?reservation_id=${encodeURIComponent(appointment.id)}`, appointment.vehicle_id)}>Check reservation</Link>}
                  {canCancel && (
                    <ControlButton
                      type="button"
                      onClick={() => {
                        if (window.confirm('Cancel this appointment?')) cancelMutation.mutate(appointment.id)
                      }}
                      disabled={cancelMutation.isPending}
                      className="mt-2 text-xs font-bold text-[#ff8b8d] hover:text-white disabled:opacity-50"
                    >
                      Cancel
                    </ControlButton>
                  )}
                </div>
              </article>
            )
          })}
        </div>
      )}

      <Link data-db-control="action" to={scopedPortalPath('/portal/services',scope.vehicleId)} className="cp-secondary">Book a service</Link>
    </div>
  )
}
