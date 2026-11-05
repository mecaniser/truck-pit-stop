import { Popover, PopoverBackdrop, PopoverButton, PopoverPanel, Portal } from '@headlessui/react'
import { MapPin, X } from 'lucide-react'
import { ControlButton } from '@/components/ui/Controls'
import type { BoardTruck } from './types'
import { fleetUnitLabel } from './helpers'
import { readingCaption, readingSummary, retained, truckCurrentSpeed, useTelemetryClock } from './telemetry'
import './unitLocationPopover.css'

/** Keep each unit's location and independently timed speed behind one marker. */
export default function UnitLocationPopover({ truck }: { truck: BoardTruck }) {
  const now = useTelemetryClock()
  const location = retained(truck.telemetry?.location, now)
  const speed = truckCurrentSpeed(truck, now)
  const oldSpeed = retained(truck.telemetry?.speed, now)
  const label = `Location and speed for ${fleetUnitLabel(truck)}`
  const address = location?.label || (location?.lat != null && location.lng != null ? `${location.lat.toFixed(5)}, ${location.lng.toFixed(5)}` : 'Unavailable')
  return <Popover as="span" className="unit-location" onClick={event => event.stopPropagation()} onKeyDown={event => event.stopPropagation()}>
    {({ close }) => <>
      <PopoverButton data-db-control="icon" className="unit-location-trigger" aria-label={label} title={label}><MapPin size={17} aria-hidden="true" /></PopoverButton>
      <Portal><PopoverBackdrop className="unit-location-backdrop" onMouseDown={event => event.preventDefault()} onClick={event => { event.stopPropagation(); close() }} /></Portal>
      <PopoverPanel anchor={{ to: 'bottom end', gap: 8, padding: 12 }} portal focus className="unit-location-panel" role="dialog" aria-label={label}>
        <header><h3>{fleetUnitLabel(truck)}</h3><ControlButton controlKind="icon" type="button" className="unit-location-close" aria-label="Close location and speed" onClick={() => close()}><X size={17} aria-hidden="true" /></ControlButton></header>
        <dl><div><dt>Address</dt><dd>{address}</dd>{location && <small title={readingCaption(location)}>{readingSummary(location, now)}</small>}</div>
          <div><dt>Speed</dt><dd aria-label={!speed ? 'Speed unavailable' : undefined}>{speed ? `${speed.value.toLocaleString(undefined, { maximumFractionDigits: 1 })} mph` : 'Unavailable'}</dd>
            {speed ? <small title={readingCaption(speed)}>{readingSummary(speed, now)}</small> : <small>{oldSpeed?.observed_at && Number.isFinite(Date.parse(oldSpeed.observed_at)) ? `Last observed${oldSpeed.observed_precision === 'minute' ? ' around' : ''} ${new Date(oldSpeed.observed_at).toLocaleString()}` : 'No recent speed reading.'}</small>}
          </div></dl>
      </PopoverPanel>
    </>}
  </Popover>
}
