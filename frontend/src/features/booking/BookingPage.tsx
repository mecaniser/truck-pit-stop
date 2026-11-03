import { ControlButton } from '@/components/ui/Controls'
import { useState, useEffect, useMemo, useRef } from 'react'
import { Spinner, LoadingLine } from '@/components/ui'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { format, addDays } from 'date-fns'
import api from '../../lib/api'
import type { Service, Vehicle, TimeSlot } from '../../types'
import { ArrowLeft, Check, CheckCircle, Truck } from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import { formatMoney } from '@/features/customer-portal/portal-ui'
import { getPortalItems, resolveVehicleScope, scopedPortalPath, vehicleIdentity, vehicleIdentityCollisions } from '@/features/customer-portal/portal-context'

type BookingStep = 'vehicle' | 'datetime' | 'details' | 'confirm' | 'payment' | 'success'

export default function BookingPage() {
  const { serviceId } = useParams<{ serviceId: string }>()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const user = useAuthStore(state => state.user)
  const tenant = user?.tenant_id
  const customer = user?.customer_id
  const requestedVehicle = params.get('vehicle_id')
  const preselectionApplied = useRef(false)
  const [step, setStep] = useState<BookingStep>('vehicle')
  const [selectedVehicle, setSelectedVehicle] = useState<string | null>(null)
  const [selectedDate, setSelectedDate] = useState<Date>(addDays(new Date(), 1))
  const [selectedTime, setSelectedTime] = useState<string | null>(null)
  const [notes, setNotes] = useState('')
  const [appointmentId, setAppointmentId] = useState<string | null>(null)
  const [confirmationNumber, setConfirmationNumber] = useState<string | null>(null)
  const serviceQuery = useQuery<Service>({ queryKey: ['service', serviceId, tenant, customer], queryFn: async () => (await api.get(`/services/${serviceId}`)).data, enabled: !!serviceId })
  const { data: service } = serviceQuery
  const vehiclesQuery = useQuery({ queryKey: ['vehicles', tenant, customer], queryFn: ({ signal }) => getPortalItems<Vehicle>('/vehicles', {}, signal) })
  const vehicles = useMemo(() => vehiclesQuery.data || [], [vehiclesQuery.data])
  const scope = resolveVehicleScope(vehicles, requestedVehicle)
  const collisions = vehicleIdentityCollisions(vehicles)
  const vehicle = vehicles.find(item => item.id === selectedVehicle)
  const validVehicle = !!vehicle && !collisions.has(vehicle.id)
  const slotsQuery = useQuery<TimeSlot[]>({
    queryKey: ['time-slots', serviceId, format(selectedDate, 'yyyy-MM-dd'), tenant, customer],
    queryFn: async () => (await api.get(`/appointments/available-slots/${serviceId}?date=${format(selectedDate, 'yyyy-MM-dd')}`)).data,
    enabled: !!serviceId && (step === 'datetime' || step === 'confirm'),
  })
  const availableSlots = (slotsQuery.data || []).filter(slot => slot.available)
  const selectedSlot = availableSlots.find(slot => slot.time === selectedTime)
  const slotClock = selectedSlot || slotsQuery.data?.[0]
  const timeZoneLabel = slotClock?.timezone && slotClock.starts_at
    ? new Intl.DateTimeFormat('en-US', { timeZone: slotClock.timezone, timeZoneName: 'long' }).formatToParts(new Date(slotClock.starts_at)).find(part => part.type === 'timeZoneName')?.value || 'shop local time'
    : 'shop local time'
  const canContinueTime = !!selectedTime && !!selectedSlot?.starts_at && !!selectedSlot?.timezone && !slotsQuery.isError && !slotsQuery.isFetching && availableSlots.some(slot => slot.time === selectedTime)

  // Create appointment mutation
  const createAppointment = useMutation({
    mutationFn: async () => {
      if (!canContinueTime || (service?.requires_vehicle && !validVehicle)) throw new Error('Booking selection unavailable')
      const response = await api.post('/appointments', {
        service_id: serviceId,
        vehicle_id: selectedVehicle,
        scheduled_at: selectedSlot!.starts_at,
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


  // Reset local choices when the authenticated customer, service, or URL context changes.
  useEffect(() => {
    preselectionApplied.current = false
    setSelectedVehicle(null)
    setSelectedTime(null)
    setNotes('')
    setStep('vehicle')
    setAppointmentId(null)
    setConfirmationNumber(null)
  }, [tenant, customer, serviceId, requestedVehicle])
  useEffect(() => {
    if (vehiclesQuery.isSuccess && !vehiclesQuery.isFetching && service) {
      setSelectedVehicle(current => !service.requires_vehicle ? null : current && vehicles.some(item => item.id === current) ? current : scope.vehicleId)
    }
  }, [vehiclesQuery.isSuccess, vehiclesQuery.isFetching, scope.vehicleId, service, vehicles])
  useEffect(() => {
    if (preselectionApplied.current || !vehiclesQuery.isSuccess || vehiclesQuery.isFetching || !service) return
    preselectionApplied.current = true
    if (service.requires_vehicle && scope.vehicleId && !scope.invalid && !scope.ambiguous) setStep('datetime')
  }, [vehiclesQuery.isSuccess, vehiclesQuery.isFetching, service, scope.vehicleId, scope.invalid, scope.ambiguous, tenant, customer, serviceId, requestedVehicle])
  useEffect(() => {
    if (service && !service.requires_vehicle && step === 'vehicle' && !scope.invalid) {
      setSelectedVehicle(null)
      setStep('datetime')
    }
  }, [service, step, scope.invalid])

  if (serviceQuery.isLoading || vehiclesQuery.isLoading) return <div className="cp-root"><Spinner size="xl" /></div>
  if (serviceQuery.isError || vehiclesQuery.isError) return <div className="cp-root" role="alert"><h1>Booking unavailable</h1><p>We couldn’t load this service and your vehicles.</p><ControlButton className="cp-secondary" onClick={() => { void serviceQuery.refetch(); void vehiclesQuery.refetch() }}>Try again</ControlButton></div>
  if (!service || !service.is_active) return <div className="cp-root"><h1>Service unavailable</h1><ControlButton className="cp-secondary" onClick={() => navigate(scopedPortalPath('/portal/services', scope.vehicleId))}>Choose another service</ControlButton></div>
  if (scope.invalid) return <div className="cp-root" role="alert"><h1>Vehicle unavailable</h1><p>This vehicle is not available for your booking. Choose one of your vehicles to continue.</p><ControlButton className="cp-secondary" onClick={() => navigate('/portal/services')}>Choose another vehicle</ControlButton></div>
  const nextDays = Array.from({ length: 14 }, (_, i) => addDays(new Date(), i + 1))
  const steps = [{ key: 'vehicle', label: 'Vehicle' }, { key: 'datetime', label: 'Date & time' }, { key: 'details', label: 'Details' }, { key: 'confirm', label: 'Review' }].filter(item => item.key !== 'vehicle' || service.requires_vehicle)
  return <div className="cp-root">
    <ControlButton className="cp-text cp-back" onClick={() => navigate(scopedPortalPath('/portal/services', selectedVehicle || scope.vehicleId))}><ArrowLeft size={16} />Choose another service</ControlButton>
    <div className="cp-title"><div><h1>Book a service</h1><p>{service.name}</p></div></div>
    <div className="cp-booking-grid"><div>
      <ol className="cp-steps">{steps.map((item, i) => <li key={item.key} aria-current={step === item.key ? 'step' : undefined}><span>{steps.findIndex(candidate => candidate.key === step) > i ? <Check size={14} /> : i + 1}</span>{item.label}</li>)}</ol>
      <section className="cp-panel cp-book-step">
        {step === 'vehicle' && service.requires_vehicle && <>
          <h2>Which vehicle?</h2>
          {scope.ambiguous && <p role="alert">Vehicle details need review. Contact the shop if you cannot identify your vehicle.</p>}
          {!vehicles.length && <p>No vehicles registered. Add a vehicle before booking this service.</p>}
          <div className="cp-vehicle-choices">{vehicles.map(item => <ControlButton controlKind="content" key={item.id} disabled={collisions.has(item.id)} aria-pressed={selectedVehicle === item.id} onClick={() => setSelectedVehicle(item.id)}><Truck /><span><strong>{vehicleIdentity(item)}</strong>{collisions.has(item.id) && <span>Details need review — contact the shop</span>}</span>{selectedVehicle === item.id && <Check size={18} />}</ControlButton>)}</div>
          <ControlButton className="cp-primary" disabled={!validVehicle} onClick={() => setStep('datetime')}>Continue</ControlButton>
        </>}
        {step === 'datetime' && <>
          <h2>Choose a date and time</h2><h3>Date</h3>
          <div className="cp-date-choices">{nextDays.map(date => <ControlButton key={format(date, 'yyyy-MM-dd')} aria-pressed={format(selectedDate, 'yyyy-MM-dd') === format(date, 'yyyy-MM-dd')} onClick={() => { setSelectedDate(date); setSelectedTime(null) }}>{format(date, 'EEE, MMM d')}</ControlButton>)}</div>
          <h3>Available times</h3>{slotsQuery.data?.[0]?.timezone && <p>Times in {timeZoneLabel}</p>}
          {slotsQuery.isLoading ? <LoadingLine>Loading available times…</LoadingLine> : slotsQuery.isError ? <div role="alert"><p>Available times couldn’t be loaded.</p><ControlButton className="cp-secondary" onClick={() => { setSelectedTime(null); void slotsQuery.refetch() }}>Try again</ControlButton></div> : availableSlots.length ? <div className="cp-date-choices">{availableSlots.map(slot => <ControlButton key={slot.time} aria-pressed={selectedTime === slot.time} onClick={() => setSelectedTime(slot.time)}>{slot.time}</ControlButton>)}</div> : <p>No available times for this date. Choose another date.</p>}
          <div className="cp-step-actions">{service.requires_vehicle && <ControlButton className="cp-secondary" onClick={() => setStep('vehicle')}>Back</ControlButton>}<ControlButton className="cp-primary" disabled={!canContinueTime || (service.requires_vehicle && !validVehicle)} onClick={() => setStep('details')}>Continue</ControlButton></div>
        </>}
        {step === 'details' && <><h2>Anything the shop should know?</h2><label className="cp-field">Notes (optional)<textarea value={notes} onChange={event => setNotes(event.target.value)} placeholder="Describe a concern or anything to check." rows={4} /></label><div className="cp-step-actions"><ControlButton className="cp-secondary" onClick={() => setStep('datetime')}>Back</ControlButton><ControlButton className="cp-primary" onClick={() => setStep('confirm')}>Review visit</ControlButton></div></>}
        {step === 'confirm' && <><h2>Review your visit</h2>{[['Service', service.name], ...(service.requires_vehicle ? [['Vehicle', vehicle ? vehicleIdentity(vehicle) : 'Vehicle unavailable']] : []), ['Date', format(selectedDate, 'EEEE, MMM d')], ['Time', `${selectedTime} (${timeZoneLabel})`], ['Duration', `${service.duration_minutes} min`], ['Total', formatMoney(service.computed_total_price)], ...(notes ? [['Notes', notes]] : [])].map(([label, value]) => <div className="cp-review-line" key={label}><span>{label}</span><strong>{value}</strong></div>)}{(!canContinueTime && !slotsQuery.isFetching) && <div role="alert"><p>This time is no longer available or couldn’t be verified. Choose an available time to continue.</p><ControlButton className="cp-secondary" onClick={() => setStep('datetime')}>Choose another time</ControlButton></div>}{slotsQuery.isFetching && <LoadingLine>Checking availability…</LoadingLine>}{createAppointment.isError && <p role="alert">Your booking couldn’t be created. Please try again.</p>}<div className="cp-step-actions"><ControlButton className="cp-secondary" onClick={() => setStep('details')}>Back</ControlButton><ControlButton className="cp-primary" disabled={createAppointment.isPending || !canContinueTime || (service.requires_vehicle && !validVehicle)} onClick={() => createAppointment.mutate()}>{createAppointment.isPending ? 'Creating…' : 'Continue to payment'}</ControlButton></div></>}
        {/* Payment */}
        {step === 'payment' && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-white">Payment</h2>

            <div className="rounded-lg border border-[#8b7cf7]/30 bg-[#8b7cf7]/10 p-4 text-center">
              <p className="mb-2 text-[#c9bfff]">
                Stripe payment integration will be added here
              </p>
              <p className="text-gray-400 text-sm">
                For now, click below to simulate a successful payment
              </p>
            </div>

            <div className="bg-white/5 rounded-lg p-4">
              <div className="flex justify-between text-lg">
                <span className="text-gray-400">Amount Due</span>
                <span className="font-extrabold text-[#eceef4] tabular-nums">
                  ${parseFloat(service.computed_total_price).toFixed(2)}
                </span>
              </div>
            </div>

            <ControlButton
              onClick={() => confirmPayment.mutate()}
              disabled={confirmPayment.isPending}
              className="w-full rounded-[11px] bg-[#8b7cf7]  font-extrabold text-[#0e1118] hover:brightness-110 disabled:opacity-50"
            >
              {confirmPayment.isPending ? 'Processing...' : 'Complete Payment'}
            </ControlButton>
          </div>
        )}

        {/* Success */}
        {step === 'success' && (
          <div className="text-center space-y-4 py-6">
            <div className="flex justify-center mb-4">
              <CheckCircle className="w-12 h-12 text-emerald-400" />
            </div>
            <h2 className="text-2xl font-bold text-white">Booking Confirmed!</h2>
            <p className="text-gray-400">
              Your appointment has been scheduled successfully.
            </p>

            <div className="bg-white/5 rounded-lg p-4 inline-block">
              <div className="text-sm text-gray-400">Confirmation Number</div>
              <div className="text-2xl font-mono font-extrabold text-[#c9bfff]">
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
              <ControlButton
                onClick={() => navigate(scopedPortalPath('/portal/appointments', selectedVehicle || scope.vehicleId))}
                className="flex-1  bg-white/10 hover:bg-white/20 text-white font-medium rounded-lg transition-colors"
              >
                View Appointments
              </ControlButton>
              <ControlButton
                onClick={() => navigate(scopedPortalPath('/portal', selectedVehicle || scope.vehicleId))}
                className="flex-1 rounded-[11px] bg-[#8b7cf7]  font-extrabold text-[#0e1118] hover:brightness-110"
              >
                Back to Dashboard
              </ControlButton>
            </div>
          </div>
        )}

      </section></div><aside className="cp-panel cp-book-summary"><h2>Your visit</h2><h3>{service.name}</h3><p>{service.duration_minutes} min · {formatMoney(service.computed_total_price)}</p><hr />{service.requires_vehicle ? <><strong>{vehicle ? vehicleIdentity(vehicle) : 'Vehicle not selected'}</strong></> : <p>No vehicle required</p>}{selectedTime && <p>{format(selectedDate, 'EEE, MMM d')} · {selectedTime} ({timeZoneLabel})</p>}</aside></div>
    </div>
}
