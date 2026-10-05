import { expect, it } from 'vitest'
import { mapCity, mapUnitLabel } from '../mapLabels'

it.each(['01', '022', 'W900', 'HINO', '609'])('preserves raw unit %s', unit => {
  expect(mapUnitLabel({ unit_number: unit })).toBe(unit)
})
it('does not substitute a company name for a missing unit', () => expect(mapUnitLabel({ unit_number: null })).toBe('—'))
it.each([
  ['I 85, Belle Meade, SC 29605', 'Belle Meade'],
  ['282 Seaboard Dr, Stallings, NC 28104', 'Stallings'],
  ['Interstate Blvd, Horn Lake, MS 38637-1453', 'Horn Lake'],
  ['I 40, Nashville-Davidson, TN 37214', 'Nashville-Davidson'],
  ['Charlotte, NC', 'Charlotte'],
  ['12 Main Rd, Charlotte, NC 28278, USA', 'Charlotte'],
  ['123 Main Rd', 'City unavailable'],
  [null, 'Location unavailable'],
])('shows city from %s', (label, expected) => expect(mapCity(label)).toBe(expected))
