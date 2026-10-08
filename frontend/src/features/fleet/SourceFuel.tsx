import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import { X } from 'lucide-react'
import { summarizeFuel, type FuelDaily } from './fuelDaily'
const num = (n: number | null) => n === null ? 'Not reported' : n.toLocaleString(undefined, { maximumFractionDigits: 1 })
/** Never add modeled trip gallons to provider report gallons. */
export default function SourceFuel({ records, vehicleId, start, end }: { records: FuelDaily[]; vehicleId?: string; start?: string; end?: string }) {
  const fuel = summarizeFuel(records, vehicleId, start, end)
  if (!fuel) return <span className="otr-fuel-missing">No fuel report</span>
  return <Popover className="otr-source-fuel">
    <PopoverButton className="otr-source-fuel-trigger" aria-label={`Motive fuel details: ${num(fuel.driving)}${fuel.driving !== null ? ' gallons' : ''} driving, ${num(fuel.idling)}${fuel.idling !== null ? ' gallons' : ''} idling`}>
      <span><strong>{num(fuel.driving)} {fuel.driving !== null && <small>gal</small>}</strong><small>Driving{fuel.drivingDays < fuel.days && fuel.drivingDays > 0 ? ' · partial' : ''}</small></span>
      <span><strong>{num(fuel.idling)} {fuel.idling !== null && <small>gal</small>}</strong><small>Idling{fuel.idlingDays < fuel.days && fuel.idlingDays > 0 ? ' · partial' : ''}</small></span>
    </PopoverButton>
    <PopoverPanel anchor={{ to: 'bottom end', gap: 8, padding: 12 }} className="otr-activity-popover" role="dialog" aria-label="Motive fuel report">
      {({ close }) => <><header><div><small>{fuel.first} – {fuel.last}</small><h4>Motive fuel report</h4></div><button aria-label="Close fuel details" onClick={() => close()}><X size={18} /></button></header>
        <table className="otr-facts"><tbody><tr><th>Driving fuel</th><td>{num(fuel.driving)} {fuel.driving !== null ? 'gal' : ''}</td></tr><tr><th>Idling fuel</th><td>{num(fuel.idling)} {fuel.idling !== null ? 'gal' : ''}</td></tr><tr><th>Reported total</th><td>{num(fuel.total)} {fuel.total !== null ? 'gal' : ''}</td></tr><tr><th>Fuel-report distance</th><td>{num(fuel.miles)} {fuel.miles !== null ? 'mi' : ''}</td></tr><tr><th>Dates with reports</th><td>{fuel.days}</td></tr><tr><th>Driving / idling dates</th><td>{fuel.drivingDays} / {fuel.idlingDays}</td></tr></tbody></table>
        <p className="otr-popover-note">Partial coverage · source report dates. {fuel.timezone ? `Report timezone: ${fuel.timezone}.` : 'Motive’s report timezone is unverified.'} Report distance may differ from trips; missing reports are not zero fuel. Totals may differ slightly from driving + idling due to source rounding.</p>
      </>}
    </PopoverPanel>
  </Popover>
}
