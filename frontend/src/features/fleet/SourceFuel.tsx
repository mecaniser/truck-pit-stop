import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import { X } from 'lucide-react'
import { summarizeFuel, medianFuel, type FuelDaily } from './fuelDaily'
const num = (n: number | null) => n === null ? 'Not reported' : n.toLocaleString(undefined, { maximumFractionDigits: 1 })
/** Never add modeled trip gallons to provider report gallons. */
export default function SourceFuel({ records, vehicleId, start, end, medianVehicleIds }: { medianVehicleIds?: string[]; records: FuelDaily[]; vehicleId?: string; start?: string; end?: string }) {
  const scoped = medianVehicleIds ? records.filter(row => medianVehicleIds.includes(row.vehicle_id) && (!start || row.report_date >= start) && (!end || row.report_date <= end)) : records
  const fuel = summarizeFuel(scoped, vehicleId, start, end)
  const median = medianVehicleIds ? medianFuel(scoped, medianVehicleIds) : null
  const driving = median ? median.driving.value : fuel?.driving ?? null
  const idling = median ? median.idling.value : fuel?.idling ?? null
  if (!fuel) return <span className="otr-fuel-missing">No fuel report</span>
  return <Popover className="otr-source-fuel">
    <PopoverButton className="otr-source-fuel-trigger" aria-label={`${median ? 'Fleet fuel median' : 'Motive fuel details'}: ${num(driving)}${driving !== null ? ' gallons' : ''} driving, ${num(idling)}${idling !== null ? ' gallons' : ''} idling`}>
      <span><strong>{num(driving)} {driving !== null && <small>gal</small>}</strong><small>{median ? 'Driving median' : 'Driving'}{!median && fuel.drivingDays < fuel.days && fuel.drivingDays > 0 ? ' · partial' : ''}</small></span>
      <span><strong>{num(idling)} {idling !== null && <small>gal</small>}</strong><small>{median ? 'Idling median' : 'Idling'}{!median && fuel.idlingDays < fuel.days && fuel.idlingDays > 0 ? ' · partial' : ''}</small></span>
    </PopoverButton>
    <PopoverPanel anchor={{ to: 'bottom end', gap: 8, padding: 12 }} className="otr-activity-popover" role="dialog" aria-label="Motive fuel report">
      {({ close }) => <><header><div><small>{fuel.first} – {fuel.last}</small><h4>Motive fuel report</h4></div><button aria-label="Close fuel details" onClick={() => close()}><X size={18} /></button></header>
        {median && <p className="otr-popover-note">Median per truck over selected report dates: driving from {median.driving.count} {median.driving.count === 1 ? 'truck' : 'trucks'}; idling from {median.idling.count} {median.idling.count === 1 ? 'truck' : 'trucks'}. Missing readings are excluded; explicit zero is included. Report coverage may differ between trucks. Fleet totals below.</p>}
        <table className="otr-facts"><tbody><tr><th>Driving fuel</th><td>{num(fuel.driving)} {fuel.driving !== null ? 'gal' : ''}</td></tr><tr><th>Idling fuel</th><td>{num(fuel.idling)} {fuel.idling !== null ? 'gal' : ''}</td></tr><tr><th>Reported total</th><td>{num(fuel.total)} {fuel.total !== null ? 'gal' : ''}</td></tr><tr><th>Fuel-report distance</th><td>{num(fuel.miles)} {fuel.miles !== null ? 'mi' : ''}</td></tr><tr><th>Dates with reports</th><td>{fuel.days}</td></tr><tr><th>Driving / idling dates</th><td>{fuel.drivingDays} / {fuel.idlingDays}</td></tr></tbody></table>
        <p className="otr-popover-note">Partial coverage · source report dates. {fuel.timezone ? `Report timezone: ${fuel.timezone}.` : 'Motive’s report timezone is unverified.'} Report distance may differ from trips; missing reports are not zero fuel. Totals may differ slightly from driving + idling due to source rounding.</p>
      </>}
    </PopoverPanel>
  </Popover>
}
