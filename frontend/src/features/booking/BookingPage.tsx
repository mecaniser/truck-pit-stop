import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { format, addDays } from 'date-fns'
import api from '../../lib/api'
import { Service, Vehicle, TimeSlot } from '../../types'

type BookingStep = 'vehicle' | 'datetime' | 'confirm' | 'payment' | 'success'

export default function BookingPage() {
  const { serviceId } = useParams<{ serviceId: string }>()
  const navigate = useNavigate()

  const [step, setStep] = useState<BookingStep>('vehicle')
  const [selectedVehicle, setSelectedVehicle] = useState<string | null>(null)
  const [selectedDate, setSelectedDate] = useState<Date>(addDays(new Date(), 1))
  const [selectedTime, setSelectedTime] = useState<string | null>(null)
  const [notes, setNotes] = useState('')
  const [appointmentId, setAppointmentId] = useState<string | null>(null)
  const [confirmationNumber, setConfirmationNumber] = useState<string | null>(null)

  // Fetch service details
  const { data: service, isLoading: serviceLoading } = useQuery<Service>({
    queryKey: ['service', serviceId],
    queryFn: async () => {
      const response = await api.get(`/services/${serviceId}`)
      return response.data
    },
    enabled: !!serviceId,
  })

  // Fetch customer vehicles
  const { data: vehicles } = useQuery<Vehicle[]>({
    queryKey: ['vehicles'],
    queryFn: async () => {
      const response = await api.get('/vehicles')
      return response.data
    },
  })

  // Fetch available time slots
  const { data: timeSlots, isLoading: slotsLoading } = useQuery<TimeSlot[]>({
    queryKey: ['time-slots', serviceId, format(selectedDate, 'yyyy-MM-dd')],
    queryFn: async () => {
      const response = await api.get(
        `/appointments/available-slots/${serviceId}?date=${format(selectedDate, 'yyyy-MM-dd')}`
      )
      return response.data
    },
    enabled: !!serviceId && step === 'datetime',
  })

  // Create appointment mutation
  const createAppointment = useMutation({
    mutationFn: async () => {
      const scheduledAt = new Date(selectedDate)
      const [hours, minutes] = selectedTime!.split(':').map(Number)
      scheduledAt.setHours(hours, minutes, 0, 0)

      const response = await api.post('/appointments', {
        service_id: serviceId,
        vehicle_id: selectedVehicle,
        scheduled_at: scheduledAt.toISOString(),
        customer_notes: notes || null,
      })
      return response.data
    },
    onSuccess: (data) => {
      setAppointmentId(data.id)
      setStep('payment')
    },
  })

  // Confirm payment mutation
  const confirmPayment = useMutation({
    mutationFn: async () => {
      const response = await api.post(`/appointments/${appointmentId}/confirm-payment`)
      return response.data
    },
    onSuccess: (data) => {
      setConfirmationNumber(data.confirmation_number)
      setStep('success')
    },
  })

  // Skip vehicle selection if not required
  useEffect(() => {
    if (service && !service.requires_vehicle && step === 'vehicle') {
      setStep('datetime')
    }
  }, [service, step])

  if (serviceLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  if (!service) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-400">Service not found</p>
      </div>
    )
  }

  const nextDays = Array.from({ length: 14 }, (_, i) => addDays(new Date(), i + 1))

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/portal/services')}
          className="p-2 rounded-lg bg-white/5 hover:bg-white/10 transition-colors"
        >
          <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-white">Book {service.name}</h1>
          <p className="text-gray-400 text-sm">
            ${parseFloat(service.base_price).toFixed(2)} • ~{service.duration_minutes} min
          </p>
        </div>
      </div>

      {/* Progress Steps */}
      <div className="flex items-center gap-2 text-sm">
        {['vehicle', 'datetime', 'confirm', 'payment'].map((s, i) => {
          if (s === 'vehicle' && !service.requires_vehicle) return null
          const stepIndex = service.requires_vehicle ? i : i - 1
          const currentIndex = ['vehicle', 'datetime', 'confirm', 'payment'].indexOf(step)
          const isActive = step === s
          const isCompleted = currentIndex > i

          return (
            <div key={s} className="flex items-center gap-2">
              {i > 0 && (s !== 'vehicle' || service.requires_vehicle) && (
                <div className={`w-8 h-0.5 ${isCompleted ? 'bg-amber-500' : 'bg-white/20'}`} />
              )}
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium ${
                  isActive
                    ? 'bg-amber-500 text-white'
                    : isCompleted
                    ? 'bg-amber-500/20 text-amber-400'
                    : 'bg-white/10 text-gray-500'
                }`}
              >
                {isCompleted ? '✓' : stepIndex + 1}
              </div>
            </div>
          )
        })}
      </div>

      {/* Step Content */}
      <div className="bg-white/5 rounded-xl p-5 border border-white/10">
        {/* Vehicle Selection */}
        {step === 'vehicle' && service.requires_vehicle && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-white">Select Your Vehicle</h2>
            
            {vehicles && vehicles.length > 0 ? (
              <div className="space-y-2">
                {vehicles.map((vehicle) => (
                  <button
                    key={vehicle.id}
                    onClick={() => setSelectedVehicle(vehicle.id)}
                    className={`w-full p-4 rounded-lg border text-left transition-all ${
                      selectedVehicle === vehicle.id
                        ? 'bg-amber-500/20 border-amber-500'
                        : 'bg-white/5 border-white/10 hover:border-white/30'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-2xl">🚛</span>
                      <div>
                        <div className="font-medium text-white">
                          {vehicle.year} {vehicle.make} {vehicle.model}
                        </div>
                        <div className="text-sm text-gray-400">
                          {vehicle.license_plate || 'No plate'}
                        </div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-gray-400">No vehicles registered. Please add a vehicle first.</p>
            )}

            <button
              onClick={() => setStep('datetime')}
              disabled={!selectedVehicle}
              className="w-full py-3 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
            >
              Continue
            </button>
          </div>
        )}

        {/* Date & Time Selection */}
        {step === 'datetime' && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-white">Choose Date & Time</h2>

            {/* Date Selection */}
            <div>
              <label className="text-sm text-gray-400 mb-2 block">Select Date</label>
              <div className="overflow-x-auto -mx-5 px-5">
                <div className="flex gap-2 min-w-max">
                  {nextDays.map((date) => (
                    <button
                      key={date.toISOString()}
                      onClick={() => {
                        setSelectedDate(date)
                        setSelectedTime(null)
                      }}
                      className={`p-3 rounded-lg text-center min-w-[70px] transition-all ${
                        format(selectedDate, 'yyyy-MM-dd') === format(date, 'yyyy-MM-dd')
                          ? 'bg-amber-500 text-white'
                          : 'bg-white/5 text-gray-300 hover:bg-white/10'
                      }`}
                    >
                      <div className="text-xs uppercase">{format(date, 'EEE')}</div>
                      <div className="text-lg font-bold">{format(date, 'd')}</div>
                      <div className="text-xs">{format(date, 'MMM')}</div>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Time Selection */}
            <div>
              <label className="text-sm text-gray-400 mb-2 block">Select Time</label>
              {slotsLoading ? (
                <div className="text-gray-400">Loading available times...</div>
              ) : (
                <div className="grid grid-cols-4 sm:grid-cols-6 gap-2">
                  {timeSlots?.map((slot) => (
                    <button
                      key={slot.time}
                      onClick={() => slot.available && setSelectedTime(slot.time)}
                      disabled={!slot.available}
                      className={`py-2 px-3 rounded-lg text-sm font-medium transition-all ${
                        selectedTime === slot.time
                          ? 'bg-amber-500 text-white'
                          : slot.available
                          ? 'bg-white/5 text-gray-300 hover:bg-white/10'
                          : 'bg-white/5 text-gray-600 cursor-not-allowed line-through'
                      }`}
                    >
                      {slot.time}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="flex gap-3">
              {service.requires_vehicle && (
                <button
                  onClick={() => setStep('vehicle')}
                  className="flex-1 py-3 bg-white/10 hover:bg-white/20 text-white font-medium rounded-lg transition-colors"
                >
                  Back
                </button>
              )}
              <button
                onClick={() => setStep('confirm')}
                disabled={!selectedTime}
                className="flex-1 py-3 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {/* Confirmation */}
        {step === 'confirm' && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-white">Confirm Your Booking</h2>

            <div className="bg-white/5 rounded-lg p-4 space-y-3">
              <div className="flex justify-between">
                <span className="text-gray-400">Service</span>
                <span className="text-white font-medium">{service.name}</span>
              </div>
              {selectedVehicle && vehicles && (
                <div className="flex justify-between">
                  <span className="text-gray-400">Vehicle</span>
                  <span className="text-white">
                    {(() => {
                      const v = vehicles.find((v) => v.id === selectedVehicle)
                      return v ? `${v.year} ${v.make} ${v.model}` : ''
                    })()}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-gray-400">Date & Time</span>
                <span className="text-white">
                  {format(selectedDate, 'EEEE, MMM d')} at {selectedTime}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Duration</span>
                <span className="text-white">~{service.duration_minutes} minutes</span>
              </div>
              <div className="border-t border-white/10 pt-3 flex justify-between">
                <span className="text-gray-400">Total</span>
                <span className="text-xl font-bold text-amber-400">
                  ${parseFloat(service.base_price).toFixed(2)}
                </span>
              </div>
            </div>

            <div>
              <label className="text-sm text-gray-400 mb-2 block">Notes (optional)</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Any special requests or information..."
                className="w-full p-3 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:border-amber-500"
                rows={3}
              />
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setStep('datetime')}
                className="flex-1 py-3 bg-white/10 hover:bg-white/20 text-white font-medium rounded-lg transition-colors"
              >
                Back
              </button>
              <button
                onClick={() => createAppointment.mutate()}
                disabled={createAppointment.isPending}
                className="flex-1 py-3 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-600/50 text-white font-medium rounded-lg transition-colors"
              >
                {createAppointment.isPending ? 'Creating...' : 'Proceed to Payment'}
              </button>
            </div>
          </div>
        )}

        {/* Payment */}
        {step === 'payment' && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-white">Payment</h2>

            <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 text-center">
              <p className="text-amber-400 mb-2">
                Stripe payment integration will be added here
              </p>
              <p className="text-gray-400 text-sm">
                For now, click below to simulate a successful payment
              </p>
            </div>

            <div className="bg-white/5 rounded-lg p-4">
              <div className="flex justify-between text-lg">
                <span className="text-gray-400">Amount Due</span>
                <span className="font-bold text-amber-400">
                  ${parseFloat(service.base_price).toFixed(2)}
                </span>
              </div>
            </div>

            <button
              onClick={() => confirmPayment.mutate()}
              disabled={confirmPayment.isPending}
              className="w-full py-3 bg-green-500 hover:bg-green-600 disabled:bg-green-600/50 text-white font-medium rounded-lg transition-colors"
            >
              {confirmPayment.isPending ? 'Processing...' : 'Complete Payment'}
            </button>
          </div>
        )}

        {/* Success */}
        {step === 'success' && (
          <div className="text-center space-y-4 py-6">
            <div className="text-6xl mb-4">✅</div>
            <h2 className="text-2xl font-bold text-white">Booking Confirmed!</h2>
            <p className="text-gray-400">
              Your appointment has been scheduled successfully.
            </p>

            <div className="bg-white/5 rounded-lg p-4 inline-block">
              <div className="text-sm text-gray-400">Confirmation Number</div>
              <div className="text-2xl font-mono font-bold text-amber-400">
                {confirmationNumber}
              </div>
            </div>

            <div className="bg-white/5 rounded-lg p-4 text-left space-y-2">
              <div className="flex justify-between">
                <span className="text-gray-400">Service</span>
                <span className="text-white">{service.name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Date & Time</span>
                <span className="text-white">
                  {format(selectedDate, 'EEEE, MMM d')} at {selectedTime}
                </span>
              </div>
            </div>

            <div className="flex gap-3 pt-4">
              <button
                onClick={() => navigate('/portal/appointments')}
                className="flex-1 py-3 bg-white/10 hover:bg-white/20 text-white font-medium rounded-lg transition-colors"
              >
                View Appointments
              </button>
              <button
                onClick={() => navigate('/portal')}
                className="flex-1 py-3 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg transition-colors"
              >
                Back to Dashboard
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
