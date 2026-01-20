import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { format } from 'date-fns'
import api from '../../lib/api'
import { Appointment, AppointmentStatus } from '../../types'

const STATUS_COLORS: Record<AppointmentStatus, { bg: string; text: string }> = {
  pending: { bg: 'bg-yellow-100', text: 'text-yellow-700' },
  confirmed: { bg: 'bg-green-100', text: 'text-green-700' },
  in_progress: { bg: 'bg-blue-100', text: 'text-blue-700' },
  completed: { bg: 'bg-purple-100', text: 'text-purple-700' },
  cancelled: { bg: 'bg-red-100', text: 'text-red-700' },
  no_show: { bg: 'bg-gray-100', text: 'text-gray-700' },
}

export default function AppointmentsPage() {
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState<'upcoming' | 'past' | 'all'>('upcoming')

  const { data: appointments, isLoading } = useQuery<Appointment[]>({
    queryKey: ['appointments'],
    queryFn: async () => {
      const response = await api.get('/appointments')
      return response.data
    },
  })

  const cancelMutation = useMutation({
    mutationFn: async (appointmentId: string) => {
      const response = await api.post(`/appointments/${appointmentId}/cancel`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['appointments'] })
    },
  })

  const filteredAppointments = appointments?.filter((apt) => {
    const aptDate = new Date(apt.scheduled_at)
    const now = new Date()
    
    if (filter === 'upcoming') {
      return aptDate >= now && !['cancelled', 'completed', 'no_show'].includes(apt.status)
    } else if (filter === 'past') {
      return aptDate < now || ['cancelled', 'completed', 'no_show'].includes(apt.status)
    }
    return true
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white">My Appointments</h1>
          <p className="text-gray-400 mt-1">Manage your scheduled appointments</p>
        </div>
        <Link
          to="/portal/services"
          className="inline-flex items-center justify-center px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg transition-colors"
        >
          + Book New
        </Link>
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-2">
        {(['upcoming', 'past', 'all'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors capitalize ${
              filter === f
                ? 'bg-amber-500 text-white'
                : 'bg-white/10 text-white hover:bg-white/20'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Appointments List */}
      <div className="space-y-3">
        {filteredAppointments?.length === 0 ? (
          <div className="text-center py-12 bg-white/5 rounded-xl border border-white/10">
            <div className="text-4xl mb-3">📅</div>
            <p className="text-gray-400">No {filter} appointments</p>
            <Link
              to="/portal/services"
              className="inline-block mt-4 text-amber-500 hover:text-amber-400"
            >
              Book a service →
            </Link>
          </div>
        ) : (
          filteredAppointments?.map((apt) => {
            const statusStyle = STATUS_COLORS[apt.status]
            const isPast = new Date(apt.scheduled_at) < new Date()
            const canCancel = ['pending', 'confirmed'].includes(apt.status) && !isPast

            return (
              <div
                key={apt.id}
                className="bg-white/5 rounded-xl p-4 sm:p-5 border border-white/10"
              >
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 flex-wrap">
                      <h3 className="font-semibold text-white">{apt.service_name}</h3>
                      <span
                        className={`px-2.5 py-1 rounded-full text-xs font-medium ${statusStyle.bg} ${statusStyle.text}`}
                      >
                        {apt.status.replace('_', ' ')}
                      </span>
                    </div>

                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-gray-400">
                      <span className="flex items-center gap-1">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                        {format(new Date(apt.scheduled_at), 'EEEE, MMM d, yyyy')}
                      </span>
                      <span className="flex items-center gap-1">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        {format(new Date(apt.scheduled_at), 'h:mm a')}
                      </span>
                      <span>~{apt.duration_minutes} min</span>
                    </div>

                    <div className="mt-2 text-xs text-gray-500">
                      Confirmation: <span className="font-mono">{apt.confirmation_number}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <div className="text-lg font-bold text-white">
                        ${parseFloat(apt.price).toFixed(2)}
                      </div>
                      {apt.paid_at && (
                        <div className="text-xs text-green-400">Paid</div>
                      )}
                    </div>

                    {canCancel && (
                      <button
                        onClick={() => {
                          if (confirm('Are you sure you want to cancel this appointment?')) {
                            cancelMutation.mutate(apt.id)
                          }
                        }}
                        disabled={cancelMutation.isPending}
                        className="px-3 py-1.5 text-sm text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg transition-colors"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </div>

                {apt.customer_notes && (
                  <div className="mt-3 pt-3 border-t border-white/5 text-sm text-gray-400">
                    <span className="text-gray-500">Notes:</span> {apt.customer_notes}
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
