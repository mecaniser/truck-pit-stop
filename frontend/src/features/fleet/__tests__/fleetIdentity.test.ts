import { describe, expect, it } from 'vitest'
import { fleetIdentity, fleetUnitLabel } from '../helpers'

/* The card shows the company where the name already sits and lifts the unit
   number into the empty space beside the status badge, so a truck is
   identifiable at a glance across a wall-mounted board. */

const t = (over: Record<string, unknown>) =>
  ({ unit_number: null, display_unit_number: null, make: 'Volvo',
     fleet_company_name: null, owner_company_name: null, ...over }) as Parameters<typeof fleetIdentity>[0]

describe('fleetIdentity', () => {
  it('splits the listing company from the unit number', () => {
    const id = fleetIdentity(t({
      unit_number: '01', display_unit_number: '77 CARGO LLC 01', owner_company_name: '77 CARGO LLC',
    }))
    expect(id.company).toBe('77 CARGO LLC')
    expect(id.unit).toBe('01')
  })

  it('prefers the owner company, which is the listing company', () => {
    const id = fleetIdentity(t({
      unit_number: '603', display_unit_number: 'Elis Logistics LLC (DBN) 603',
      owner_company_name: 'Elis Logistics LLC (DBN)', fleet_company_name: 'Someone Else',
    }))
    expect(id.company).toBe('Elis Logistics LLC (DBN)')
  })

  it('falls back to the operating authority when there is no owner', () => {
    const id = fleetIdentity(t({
      unit_number: '77', display_unit_number: 'DONTRANS LLC 77', fleet_company_name: 'DONTRANS LLC',
    }))
    expect(id.company).toBe('DONTRANS LLC')
    expect(id.unit).toBe('77')
  })

  it('shows the unit alone when no company is known', () => {
    const id = fleetIdentity(t({ unit_number: 'W900', display_unit_number: 'W900' }))
    expect(id.company).toBeNull()
    expect(id.unit).toBe('W900')
  })

  it('does not repeat a company already baked into the unit number', () => {
    // The backend leaves display_unit_number as the bare unit in this case, so
    // the card must not print the company twice.
    const id = fleetIdentity(t({
      unit_number: '77 CARGO LLC 7', display_unit_number: '77 CARGO LLC 7',
      owner_company_name: '77 CARGO LLC',
    }))
    expect(id.unit).toBe('77 CARGO LLC 7')
    expect(id.company).toBeNull()
  })

  it('falls back to the make when a truck has no unit at all', () => {
    const id = fleetIdentity(t({ make: 'Kenworth' }))
    expect(id.unit).toBe('Kenworth')
  })

  it('keeps the full label available for search and aria text', () => {
    const truck = t({ unit_number: '01', display_unit_number: '77 CARGO LLC 01', owner_company_name: '77 CARGO LLC' })
    expect(fleetUnitLabel(truck)).toBe('77 CARGO LLC 01')
  })
})
