import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { format } from 'date-fns'

import { Spinner } from '@/components/ui'
import api from '@/lib/api'
import type { Appointment, Service, Vehicle } from '@/types'
import { DateBlock, formatMoney, Pill, vehicleName } from '@/features/customer-portal/portal-ui'

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
  const [filter, setFilter] = useState<'upcoming' | 'past' | 'all'>('upcoming')

  const { data: appointments = [], isLoading } = useQuery<Appointment[]>({
    queryKey: ['appointments'],
    queryFn: async () => {
      const response = await api.get('/appointments', { params: { paginated: true, skip: 0, limit: 100 } })
      return Array.isArray(response.data) ? response.data : response.data.items
    },
  })
  const { data: services = [] } = useQuery<Service[]>({
    queryKey: ['services', 'portal-quick-book'],
    queryFn: async () => (await api.get('/services')).data,
  })
  const { data: vehicles = [] } = useQuery<Vehicle[]>({
    queryKey: ['vehicles'],
    queryFn: async () => {
      const response = await api.get('/vehicles', { params: { paginated: true, skip: 0, limit: 100 } })
      return Array.isArray(response.data) ? response.data : response.data.items
    },
  })

  const cancelMutation = useMutation({
    mutationFn: async (appointmentId: string) => api.post(`/appointments/${appointmentId}/cancel`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['appointments'] }),
  })

  const filtered = useMemo(() => appointments
    .filter(appointment => {
      const past = new Date(appointment.scheduled_at) < new Date()
        || ['cancelled', 'completed', 'no_show'].includes(appointment.status)
      if (filter === 'upcoming') return !past
      if (filter === 'past') return past
      return true
    })
    .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime()), [appointments, filter])

  const quickBook = useMemo(() => {
    const sorted = [...services].sort((a, b) => {
      const aPm = /pm|prevent/i.test(a.name) ? 0 : 1
      const bPm = /pm|prevent/i.test(b.name) ? 0 : 1
      return aPm - bPm || Number(a.computed_total_price) - Number(b.computed_total_price)
    })
    return sorted.slice(0, 3).map((service, index) => ({
      service,
      tag: index === 0 ? 'DUE SOON' : index === 1 ? 'COMPLIANCE' : 'POPULAR',
      tagClass: index === 0
        ? 'border-[#f0b959]/30 bg-[#f0b959]/10 text-[#f0b959]'
        : index === 1
          ? 'border-[#3ecf6f]/30 bg-[#3ecf6f]/10 text-[#3ecf6f]'
          : 'border-[#8b7cf7]/35 bg-[#8b7cf7]/10 text-[#c9bfff]',
    }))
  }, [services])

  if (isLoading) return <div className="flex min-h-[420px] items-center justify-center"><Spinner size="xl" /></div>

  const primaryVehicle = vehicles[0]
  const mileage = primaryVehicle?.mileage || 0
  const nextPm = mileage ? Math.ceil((mileage + 1) / 5000) * 5000 : 0
  const pmRemaining = nextPm ? nextPm - mileage : 0

  return (
    <div className="space-y-4">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-extrabold tracking-[-0.01em]">Appointments</h1>
          <p className="mt-1 text-[13px] text-[#8b92a5]">
            {primaryVehicle ? `Scheduled visits for ${primaryVehicle.unit_number ? `Unit #${primaryVehicle.unit_number}` : vehicleName(primaryVehicle)}` : 'Your scheduled service visits'}
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

      {filtered.length === 0 ? (
        <section className="rounded-2xl border border-[#232939] bg-[#161a26] px-5 py-9 text-center sm:px-6">
          <div className="mx-auto flex h-[46px] w-[46px] items-center justify-center rounded-xl border border-[#272d3d] bg-[#12161f] text-[#5c6375]">
            <CalendarDays className="h-5 w-5" />
          </div>
          <h2 className="mt-3.5 text-base font-extrabold">No {filter === 'all' ? '' : filter} visits</h2>
          <p className="mx-auto mt-1.5 max-w-[420px] text-[13px] leading-5 text-[#8b92a5]">
            {filter === 'upcoming' && pmRemaining
              ? `Your next PM is due in about ${pmRemaining.toLocaleString()} miles. Book it now and keep the truck earning.`
              : 'Your appointments will appear here as soon as a service is booked.'}
          </p>
        </section>
      ) : (
        <div className="space-y-2">
          {filtered.map(appointment => {
            const canCancel = ['pending', 'confirmed'].includes(appointment.status)
              && new Date(appointment.scheduled_at) >= new Date()
            return (
              <article key={appointment.id} className="flex items-center gap-3 rounded-xl border border-[#232939] bg-[#161a26] p-3 hover:border-[#343b52] sm:gap-4 sm:px-4">
                <DateBlock value={appointment.scheduled_at} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="truncate text-[13px] font-bold sm:text-sm">{appointment.service_name}</h2>
                    <span className={`rounded-md border px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.05em] ${statusStyles[appointment.status] || statusStyles.pending}`}>
                      {appointment.status.replace('_', ' ')}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-[#8b92a5]">{format(new Date(appointment.scheduled_at), 'h:mm a')} · {appointment.duration_minutes} min</p>
                  <p className="mt-0.5 truncate text-[11px] text-[#5c6375]">Confirmation {appointment.confirmation_number}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-sm font-extrabold tabular-nums">{formatMoney(appointment.price)}</p>
                  {canCancel && (
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm('Cancel this appointment?')) cancelMutation.mutate(appointment.id)
                      }}
                      disabled={cancelMutation.isPending}
                      className="mt-2 text-xs font-bold text-[#ff8b8d] hover:text-white disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </article>
            )
          })}
        </div>
      )}

      {quickBook.length > 0 && (
        <section>
          <h2 className="mb-2 text-[11px] font-extrabold uppercase tracking-[0.1em] text-[#8b92a5]">Book in one click</h2>
          <div className="grid gap-2.5 md:grid-cols-3">
            {quickBook.map(({ service, tag, tagClass }) => (
              <article key={service.id} className="flex flex-col rounded-[14px] border border-[#232939] bg-[#161a26] p-4 hover:border-[#343b52]">
                <span className={`w-fit rounded-md border px-2 py-0.5 text-[10px] font-extrabold tracking-[0.05em] ${tagClass}`}>{tag}</span>
                <h3 className="mt-2 text-sm font-extrabold">{service.name}</h3>
                <p className="mt-1 text-xs text-[#8b92a5]">{formatMoney(service.computed_total_price)} · {service.duration_minutes} min</p>
                <Link
                  to={`/portal/book/${service.id}`}
                  className="mt-4 flex h-[42px] items-center justify-center rounded-[10px] bg-[#8b7cf7] px-3 text-[13px] font-extrabold text-[#0e1118] md:h-[38px]"
                >
                  Book {service.name}
                </Link>
              </article>
            ))}
          </div>
        </section>
      )}

      <Link to="/portal/services" className="inline-flex items-center text-[13px] font-bold text-[#a78bfa] hover:text-[#c4b1ff]">
        Browse all {services.length} services <ChevronRight className="h-4 w-4" />
      </Link>
    </div>
  )
}
