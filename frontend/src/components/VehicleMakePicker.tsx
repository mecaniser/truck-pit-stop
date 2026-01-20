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

interface VehicleMakePickerProps {
  value: string
  onChange: (make: string) => void
  label?: string
}

export default function VehicleMakePicker({ value, onChange, label = 'Make' }: VehicleMakePickerProps) {
  const [selection, setSelection] = useState<string>(TRUCK_MAKES.includes(value) ? value : value ? 'custom' : '')

  useEffect(() => {
    if (TRUCK_MAKES.includes(value)) {
      setSelection(value)
    } else if (value) {
      setSelection('custom')
    } else {
      setSelection('')
    }
  }, [value])

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
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="e.g., Peterbilt or custom make"
            required
          />
        </div>
      ) : null}
    </div>
  )
}
