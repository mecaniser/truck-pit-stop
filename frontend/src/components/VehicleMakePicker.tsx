import { useEffect, useMemo, useState } from 'react'
import BaseSelect, { BaseSelectOption } from './BaseSelect'

const TRUCK_MAKES = [
  'Peterbilt',
  'Kenworth',
  'Freightliner',
  'Volvo',
  'Mack',
  'International',
  'Western Star',
  'Hino',
  'Isuzu',
  'Ford',
  'Ram',
  'Chevrolet',
  'GMC',
  'Mercedes-Benz',
  'MAN',
  'Scania',
]

const normalizeMakeKey = (make: string) => make.toLowerCase().replace(/[^a-z0-9]/g, '')

const MAKE_ALIASES: Record<string, string> = {
  peterbilt: 'Peterbilt',
  paccarpeterbilt: 'Peterbilt',
  kenworth: 'Kenworth',
  paccarkenworth: 'Kenworth',
  freightliner: 'Freightliner',
  freightlinertruck: 'Freightliner',
  freightlinertrucks: 'Freightliner',
  daimlerfreightliner: 'Freightliner',
  volvo: 'Volvo',
  volvotruck: 'Volvo',
  volvotrucks: 'Volvo',
  volvotrucknorthamerica: 'Volvo',
  mack: 'Mack',
  macktruck: 'Mack',
  macktrucks: 'Mack',
  international: 'International',
  internationaltruck: 'International',
  internationaltrucks: 'International',
  navistar: 'International',
  navistarinternational: 'International',
  westernstar: 'Western Star',
  westernstartruck: 'Western Star',
  westernstartrucks: 'Western Star',
  hino: 'Hino',
  hinotruck: 'Hino',
  hinotrucks: 'Hino',
  isuzu: 'Isuzu',
  isuzutruck: 'Isuzu',
  isuzutrucks: 'Isuzu',
  ford: 'Ford',
  ram: 'Ram',
  dodge: 'Ram',
  chevrolet: 'Chevrolet',
  chevy: 'Chevrolet',
  gmc: 'GMC',
  mercedesbenz: 'Mercedes-Benz',
  mercedes: 'Mercedes-Benz',
  man: 'MAN',
  scania: 'Scania',
}

const canonicalMake = (make: string) => {
  const trimmed = make.trim()
  if (!trimmed) return ''
  return MAKE_ALIASES[normalizeMakeKey(trimmed)] || ''
}

interface VehicleMakePickerProps {
  value: string
  onChange: (make: string) => void
  label?: string
  error?: string
}

export default function VehicleMakePicker({ value, onChange, label = 'Make', error }: VehicleMakePickerProps) {
  const [selection, setSelection] = useState<string>(canonicalMake(value) || (value ? 'custom' : ''))

  useEffect(() => {
    const make = canonicalMake(value)
    if (make) {
      setSelection(make)
      if (value !== make) {
        onChange(make)
      }
    } else if (value) {
      setSelection('custom')
    } else {
      setSelection('')
    }
  }, [value, onChange])

  const options: BaseSelectOption[] = useMemo(
    () => [
      ...TRUCK_MAKES.map((make) => ({ value: make, label: make })),
      { value: 'custom', label: 'Custom make' },
    ],
    []
  )

  const handleChange = (makeValue: string) => {
    setSelection(makeValue)
    if (makeValue === 'custom') {
      onChange('')
    } else {
      onChange(makeValue)
    }
  }

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label} <span className="text-red-500">*</span></label>
      <BaseSelect
        options={options}
        value={selection}
        onChange={handleChange}
        placeholder="Select make"
      />
      {selection === 'custom' ? (
        <div className="mt-2">
          <input
            name="make"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className={`w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors ${error ? 'border-red-400' : 'border-gray-300'}`}
            placeholder="e.g., Peterbilt or custom make"
            required
          />
        </div>
      ) : null}
      {error ? <p className="mt-1 text-xs font-medium text-red-600">{error}</p> : null}
    </div>
  )
}
