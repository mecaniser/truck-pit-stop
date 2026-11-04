import { ControlButton, ControlInput } from '@/components/ui/Controls'
import { useState, useEffect, useMemo, useRef } from 'react'
import { Spinner, LoadingLine } from '@/components/ui'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, addDays } from 'date-fns'
import api from '../../lib/api'
import type { Service, Vehicle, TimeSlot } from '../../types'
import { ArrowLeft, Check, CheckCircle, Truck } from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import { formatMoney } from '@/features/customer-portal/portal-ui'
import { getPortalItems, resolveVehicleScope, scopedPortalPath, vehicleIdentity, vehicleIdentityCollisions } from '@/features/customer-portal/portal-context'
import BookingCheckout from './BookingCheckout'
import type { BookingCapability, BookingReservation, VisitRequestResult } from './booking-contract'

type BookingKind = 'reserve' | 'request'
type BookingStep = 'choice' | 'vehicle' | 'datetime' | 'details' | 'confirm' | 'payment' | 'success'

export default function BookingPage() {
  const queryClient = useQueryClient()
  const { serviceId } = useParams<{ serviceId: string }>()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const user = useAuthStore(state => state.user)
  const tenant = user?.tenant_id
  const customer = user?.customer_id
  const requestedVehicle = params.get('vehicle_id')
  const reservationId = params.get('reservation_id')
  const actorContext = `${tenant}:${customer}:${serviceId}:${requestedVehicle}`
  const latestContext = useRef(actorContext)
  latestContext.current = actorContext
  const stepHeadingRef = useRef<HTMLHeadingElement>(null)
  const stepFocusRequested = useRef(false)
  const submissionKey = useRef(crypto.randomUUID())
  const [step, setStep] = useState<BookingStep>('choice')
  const [kind, setKind] = useState<BookingKind | null>(null)
  const [selectedVehicle, setSelectedVehicle] = useState<string | null>(null)
  const [selectedDate, setSelectedDate] = useState<Date>(addDays(new Date(), 1))
  const [preferredDate, setPreferredDate] = useState('')
  const [selectedTime, setSelectedTime] = useState<string | null>(null)
  const [notes, setNotes] = useState('')
  const [reservation, setReservation] = useState<BookingReservation | null>(null)
  const [request, setRequest] = useState<VisitRequestResult | null>(null)
  const serviceQuery = useQuery<Service>({ queryKey: ['service', serviceId, tenant, customer], queryFn: async ({ signal }) => (await api.get(`/services/${serviceId}`, { signal })).data, enabled: !!serviceId })
  const { data: service } = serviceQuery
  const recoveredReservation = useQuery<BookingReservation>({ queryKey: ['booking-recovery', reservationId, tenant, customer], queryFn: async ({ signal }) => (await api.get(`/appointments/${reservationId}`, { signal })).data, enabled: !!reservationId })
  const capability = useQuery<BookingCapability>({ queryKey: ['booking-payment-capability', serviceId, tenant, customer], queryFn: async ({ signal }) => (await api.get('/appointments/payment-capability', { params: { service_id: serviceId }, signal })).data, enabled: !!serviceId })
  const vehiclesQuery = useQuery({ queryKey: ['vehicles', tenant, customer], queryFn: ({ signal }) => getPortalItems<Vehicle>('/vehicles', {}, signal) })
  const vehicles = useMemo(() => vehiclesQuery.data || [], [vehiclesQuery.data])
  const scope = resolveVehicleScope(vehicles, requestedVehicle)
  const collisions = vehicleIdentityCollisions(vehicles)
  const vehicle = vehicles.find(item => item.id === selectedVehicle)
  const validVehicle = !!vehicle && !collisions.has(vehicle.id)
  const slotsQuery = useQuery<TimeSlot[]>({
    queryKey: ['time-slots', serviceId, format(selectedDate, 'yyyy-MM-dd'), tenant, customer],
    queryFn: async ({ signal }) => (await api.get(`/appointments/available-slots/${serviceId}?date=${format(selectedDate, 'yyyy-MM-dd')}`, { signal })).data,
    enabled: !!serviceId && kind === 'reserve' && (step === 'datetime' || step === 'confirm'),
  })
  const availableSlots = (slotsQuery.data || []).filter(slot => slot.available)
  const selectedSlot = availableSlots.find(slot => slot.time === selectedTime)
  const slotClock = selectedSlot || slotsQuery.data?.[0]
  const timeZoneLabel = slotClock?.timezone && slotClock.starts_at
    ? new Intl.DateTimeFormat('en-US', { timeZone: slotClock.timezone, timeZoneName: 'long' }).formatToParts(new Date(slotClock.starts_at)).find(part => part.type === 'timeZoneName')?.value || 'shop local time'
    : 'shop local time'
  const canContinueTime = !!selectedTime && !!selectedSlot?.starts_at && !!selectedSlot?.timezone && !slotsQuery.isError && !slotsQuery.isFetching
  const goToStep = (next: BookingStep) => { stepFocusRequested.current = true; setStep(next) }
  const submit = useMutation({
    mutationFn: async () => {
      if (!kind || (service?.requires_vehicle && !validVehicle)) throw new Error('Booking selection unavailable')
      const config = { headers: { 'Idempotency-Key': submissionKey.current } }
      const common = { service_id: serviceId, vehicle_id: service?.requires_vehicle ? selectedVehicle : null, customer_notes: notes || null }
      if (kind === 'request') return { context: actorContext, payload: (await api.post('/visit-requests', { ...common, preferred_date: preferredDate || null }, config)).data as VisitRequestResult }
      if (!canContinueTime || !capability.data?.available || capability.isError) throw new Error('Booking selection unavailable')
      return { context: actorContext, payload: (await api.post('/appointments', { ...common, booking_kind: 'reserve', scheduled_at: selectedSlot!.starts_at }, config)).data as BookingReservation }
    },
    onSuccess: ({ context, payload: data }) => {
      if (latestContext.current !== context) return
      if (data.booking_kind === 'request') {
        setRequest(data); goToStep('success')
        void queryClient.invalidateQueries({ queryKey: ['visit-requests', tenant, customer] })
      }
      else {
        setReservation(data); goToStep('payment')
        setParams(previous => { const next = new URLSearchParams(previous); next.set('reservation_id', data.id); return next }, { replace: true })
      }
    },
  })
  useEffect(() => {
    stepFocusRequested.current = false
    submissionKey.current = crypto.randomUUID()
    setSelectedVehicle(null); setSelectedTime(null); setNotes(''); setPreferredDate(''); setKind(null); setStep('choice'); setReservation(null); setRequest(null)
  }, [tenant, customer, serviceId, requestedVehicle])
  useEffect(() => {
    if (vehiclesQuery.isSuccess && !vehiclesQuery.isFetching && service) setSelectedVehicle(current => !service.requires_vehicle ? null : current && vehicles.some(item => item.id === current) ? current : scope.vehicleId)
  }, [vehiclesQuery.isSuccess, vehiclesQuery.isFetching, scope.vehicleId, service, vehicles])
  useEffect(() => {
    if (!stepFocusRequested.current) return
    stepFocusRequested.current = false
    stepHeadingRef.current?.focus()
  }, [step])
  const chooseKind = (next: BookingKind) => {
    setKind(next)
    submit.reset()
    submissionKey.current = crypto.randomUUID()
    goToStep(service?.requires_vehicle && !validVehicle ? 'vehicle' : 'datetime')
  }
  if (reservationId) {
    if (recoveredReservation.isLoading && !reservation) return <div className="cp-root"><LoadingLine>Checking your reservation…</LoadingLine></div>
    const recovered = recoveredReservation.data || reservation
    if (recoveredReservation.isError || !recovered || recovered.service_id !== serviceId || recovered.customer_id !== customer || recovered.booking_kind !== 'reserve') return <div className="cp-root" role="alert"><h1>Reservation unavailable</h1><p>This reservation could not be checked. Contact the shop before making another payment.</p><ControlButton className="cp-secondary" onClick={() => { void recoveredReservation.refetch() }}>Try again</ControlButton></div>
    return <div className="cp-root cp-panel cp-book-step cp-book-checkout"><BookingCheckout tenantId={tenant} key={recovered.id} appointment={recovered} vehicle={vehiclesQuery.isError ? null : vehicles.find(item => item.id === recovered.vehicle_id && !collisions.has(item.id))} capability={capability.data} onDone={() => navigate(scopedPortalPath('/portal/appointments', requestedVehicle))} /></div>
  }
  if (serviceQuery.isLoading || vehiclesQuery.isLoading) return <div className="cp-root"><Spinner size="xl" /></div>
  if (serviceQuery.isError || vehiclesQuery.isError) return <div className="cp-root" role="alert"><h1>Booking unavailable</h1><p>We couldn’t load this service and your vehicles.</p><ControlButton className="cp-secondary" onClick={() => { void serviceQuery.refetch(); void vehiclesQuery.refetch() }}>Try again</ControlButton></div>
  if (!service || !service.is_active) return <div className="cp-root"><h1>Service unavailable</h1><ControlButton className="cp-secondary" onClick={() => navigate(scopedPortalPath('/portal/services', scope.vehicleId))}>Choose another service</ControlButton></div>
  if (scope.invalid) return <div className="cp-root" role="alert"><h1>Vehicle unavailable</h1><p>This vehicle is not available for your booking. Choose one of your vehicles to continue.</p><ControlButton className="cp-secondary" onClick={() => navigate('/portal/services')}>Choose another vehicle</ControlButton></div>
  const nextDays = Array.from({ length: 14 }, (_, i) => addDays(new Date(), i + 1))
  const steps = [{ key: 'vehicle', label: 'Vehicle' }, { key: 'datetime', label: kind === 'request' ? 'Visit details' : 'Date & time' }, { key: 'details', label: 'Details' }, { key: 'confirm', label: 'Review' }].filter(item => (item.key !== 'vehicle' || service.requires_vehicle) && (item.key !== 'details' || kind !== 'request'))
  const canReserve = capability.data?.available && !capability.isError
  return <div className="cp-root">
    <ControlButton className="cp-text cp-back" onClick={() => navigate(scopedPortalPath('/portal/services', selectedVehicle || scope.vehicleId))}><ArrowLeft size={16} />Choose another service</ControlButton>
    <div className="cp-title"><div><h1>{kind === 'request' ? 'Request a visit' : kind === 'reserve' ? 'Reserve a time' : 'Book a service'}</h1><p>{service.name}</p></div>{kind && !reservation && !request && <ControlButton className="cp-text" onClick={() => goToStep('choice')}>Change booking type</ControlButton>}</div>
    <div className="cp-booking-grid"><div>
      {step !== 'choice' && step !== 'payment' && step !== 'success' && <ol className="cp-steps">{steps.map((item, i) => <li key={item.key} aria-current={step === item.key ? 'step' : undefined}><span>{steps.findIndex(candidate => candidate.key === step) > i ? <Check size={14} /> : i + 1}</span>{item.label}</li>)}</ol>}
      <section className="cp-panel cp-book-step">
        {step === 'choice' && <><h2 ref={stepHeadingRef} tabIndex={-1}>How would you like to visit?</h2><div className="cp-vehicle-choices"><ControlButton controlKind="content" disabled={!canReserve} onClick={() => chooseKind('reserve')}><span><strong>Reserve a time</strong><span>Choose an available start time. Pay in full to confirm.</span><span>Checkout holds your time for 15 minutes.</span></span></ControlButton><ControlButton controlKind="content" onClick={() => chooseKind('request')}><span><strong>Request a visit</strong><span>No payment now. The shop will confirm availability.</span><span>A request does not reserve a start time.</span></span></ControlButton></div>{capability.isLoading ? <LoadingLine>Checking reservation availability…</LoadingLine> : !canReserve && <div role="status"><p>{capability.isError ? 'Reservations are temporarily unavailable.' : capability.data?.message || 'Online reservations are unavailable.'}</p><ControlButton className="cp-text" onClick={() => { void capability.refetch() }}>Check again</ControlButton></div>}</>}
        {step === 'vehicle' && <><h2 ref={stepHeadingRef} tabIndex={-1}>Which vehicle?</h2>{scope.ambiguous && <p role="alert">Vehicle details need review. Contact the shop if you cannot identify your vehicle.</p>}{!vehicles.length && <p>No vehicles registered. Add a vehicle before booking this service.</p>}<div className="cp-vehicle-choices">{vehicles.map(item => <ControlButton controlKind="content" key={item.id} disabled={collisions.has(item.id)} aria-pressed={selectedVehicle === item.id} onClick={() => setSelectedVehicle(item.id)}><Truck /><span><strong>{vehicleIdentity(item)}</strong>{collisions.has(item.id) && <span>Details need review — contact the shop</span>}</span>{selectedVehicle === item.id && <Check size={18} />}</ControlButton>)}</div><ControlButton className="cp-primary" disabled={!validVehicle} onClick={() => goToStep('datetime')}>Continue</ControlButton></>}
        {step === 'datetime' && <><h2 ref={stepHeadingRef} tabIndex={-1}>{kind === 'request' ? 'Your visit details' : 'Choose a date and time'}</h2>{kind === 'request' ? <><label className="cp-field">Preferred visit date (optional)<ControlInput type="date" min={format(new Date(), 'yyyy-MM-dd')} value={preferredDate} onChange={event => setPreferredDate(event.target.value)} /></label><label className="cp-field">Notes (optional)<textarea value={notes} onChange={event => setNotes(event.target.value)} placeholder="Describe a concern or anything to check." rows={4} /></label><p>The shop will confirm availability. No start time is reserved.</p></> : <><h3>Date</h3><div className="cp-date-choices">{nextDays.map(date => <ControlButton key={format(date, 'yyyy-MM-dd')} aria-pressed={format(selectedDate, 'yyyy-MM-dd') === format(date, 'yyyy-MM-dd')} onClick={() => { setSelectedDate(date); setSelectedTime(null) }}>{format(date, 'EEE, MMM d')}</ControlButton>)}</div><h3>Available times</h3>{slotsQuery.data?.[0]?.timezone && <p>Times in {timeZoneLabel}</p>}{slotsQuery.isLoading ? <LoadingLine>Loading available times…</LoadingLine> : slotsQuery.isError ? <div role="alert"><p>Available times couldn’t be loaded.</p><ControlButton className="cp-secondary" onClick={() => { setSelectedTime(null); void slotsQuery.refetch() }}>Try again</ControlButton></div> : availableSlots.length ? <div className="cp-date-choices">{availableSlots.map(slot => <ControlButton key={slot.time} aria-pressed={selectedTime === slot.time} onClick={() => setSelectedTime(slot.time)}>{slot.time}</ControlButton>)}</div> : <p>No available times for this date. Choose another date.</p>}</>}<div className="cp-step-actions">{service.requires_vehicle && <ControlButton className="cp-secondary" onClick={() => goToStep('vehicle')}>Back</ControlButton>}<ControlButton className="cp-primary" disabled={(kind === 'reserve' && !canContinueTime) || (service.requires_vehicle && !validVehicle)} onClick={() => goToStep(kind === 'request' ? 'confirm' : 'details')}>{kind === 'request' ? 'Review request' : 'Continue'}</ControlButton></div></>}
        {step === 'details' && <><h2 ref={stepHeadingRef} tabIndex={-1}>Anything the shop should know?</h2><label className="cp-field">Notes (optional)<textarea value={notes} onChange={event => setNotes(event.target.value)} placeholder="Describe a concern or anything to check." rows={4} /></label><div className="cp-step-actions"><ControlButton className="cp-secondary" onClick={() => goToStep('datetime')}>Back</ControlButton><ControlButton className="cp-primary" onClick={() => goToStep('confirm')}>{kind === 'request' ? 'Review request' : 'Review visit'}</ControlButton></div></>}
        {step === 'confirm' && <><h2 ref={stepHeadingRef} tabIndex={-1}>{kind === 'request' ? 'Review your request' : 'Review your visit'}</h2>{[['Service', service.name], ...(service.requires_vehicle ? [['Vehicle', vehicle ? vehicleIdentity(vehicle) : 'Vehicle unavailable']] : []), ...(kind === 'request' ? [['Preferred date', preferredDate ? format(new Date(`${preferredDate}T12:00:00`), 'EEEE, MMM d') : 'No preference'], ['Payment', 'No payment now']] : [['Date', format(selectedDate, 'EEEE, MMM d')], ['Time', `${selectedTime} (${timeZoneLabel})`], ['Duration', `${service.duration_minutes} min`], ['Total', formatMoney(service.computed_total_price)]]), ...(notes ? [['Notes', notes]] : [])].map(([label, value]) => <div className="cp-review-line" key={label}><span>{label}</span><strong>{value}</strong></div>)}{kind === 'request' ? <p className="mt-5">The shop will confirm availability. Sending a request does not reserve a start time.</p> : <>{(!canContinueTime && !slotsQuery.isFetching) && <div role="alert"><p>This time is no longer available or couldn’t be verified. Choose an available time to continue.</p><ControlButton className="cp-secondary" onClick={() => goToStep('datetime')}>Choose another time</ControlButton></div>}{slotsQuery.isFetching && <LoadingLine>Checking availability…</LoadingLine>}<p className="mt-5">Your time is confirmed only after full payment. Checkout holds it for 15 minutes.</p></>}{submit.isError && <p role="alert">{kind === 'request' ? 'Your request couldn’t be sent.' : 'Your time couldn’t be held.'} Please try again. Your submission will not be duplicated.</p>}<div className="cp-step-actions"><ControlButton className="cp-secondary" disabled={submit.isPending} onClick={() => goToStep(kind === 'request' ? 'datetime' : 'details')}>Back</ControlButton><ControlButton className="cp-primary" disabled={submit.isPending || (kind === 'reserve' && (!canContinueTime || !canReserve))} onClick={() => submit.mutate()}>{submit.isPending ? 'Submitting…' : kind === 'request' ? 'Send request' : 'Continue to payment'}</ControlButton></div></>}
        {step === 'payment' && reservation && <BookingCheckout tenantId={tenant} key={reservation.id} appointment={reservation} vehicle={vehiclesQuery.isError ? null : vehicles.find(item => item.id === reservation.vehicle_id && !collisions.has(item.id))} capability={capability.data} onDone={() => navigate(scopedPortalPath('/portal/appointments', selectedVehicle || scope.vehicleId))} />}
        {step === 'success' && request && <div className="space-y-4"><CheckCircle className="text-emerald-400" size={36} /><h2 ref={stepHeadingRef} tabIndex={-1}>Visit request sent</h2><p>The shop will review your request. Check this request for the accepted arrival date before coming in. No start time is reserved.</p><p>Request reference: <strong>{request.request_reference}</strong></p><ControlButton className="cp-primary" onClick={() => navigate(scopedPortalPath(`/portal/appointments?request_id=${encodeURIComponent(request.id)}`, selectedVehicle || scope.vehicleId))}>View request</ControlButton></div>}
      </section></div><aside className="cp-panel cp-book-summary"><h2>Your visit</h2><h3>{service.name}</h3>{kind !== 'request' && <p>{service.duration_minutes} min · {formatMoney(reservation?.price || service.computed_total_price)}</p>}<hr />{service.requires_vehicle ? <strong>{vehicle ? vehicleIdentity(vehicle) : 'Vehicle not selected'}</strong> : <p>No vehicle required</p>}{kind === 'reserve' && selectedTime && <p>{format(selectedDate, 'EEE, MMM d')} · {selectedTime} ({timeZoneLabel})</p>}{kind === 'request' && <p>{preferredDate ? `Preferred date: ${preferredDate}` : 'No preferred date'} · Availability to be confirmed</p>}</aside></div>
  </div>
}
