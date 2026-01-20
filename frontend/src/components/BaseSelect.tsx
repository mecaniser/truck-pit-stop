import { Fragment, useMemo, useState } from 'react'
import { Listbox, Transition } from '@headlessui/react'

export interface BaseSelectOption {
  value: string
  label: string
  subLabel?: string
}

interface BaseSelectProps {
  options: BaseSelectOption[]
  value: string
  onChange: (val: string) => void
  placeholder?: string
  searchable?: boolean
  allowAddNew?: boolean
  addNewLabel?: string
  onAddNew?: () => void
}

export default function BaseSelect({
  options,
  value,
  onChange,
  placeholder = 'Select an option',
  searchable = true,
  allowAddNew = false,
  addNewLabel = '+ Add new',
  onAddNew,
}: BaseSelectProps) {
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    if (!searchable || !query.trim()) return options
    const q = query.toLowerCase()
    return options.filter((opt) => opt.label.toLowerCase().includes(q) || opt.subLabel?.toLowerCase().includes(q))
  }, [options, query, searchable])

  const selected = options.find((opt) => opt.value === value)

  const handleChange = (val: string) => {
    if (allowAddNew && val === 'add_new') {
      if (onAddNew) onAddNew()
      return
    }
    onChange(val)
  }

  return (
    <Listbox value={value} onChange={handleChange}>
      <div className="relative">
        <Listbox.Button className="w-full px-4 py-2.5 border border-gray-300 rounded-lg bg-white text-left text-gray-900 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors">
          <span className="block truncate">{selected ? selected.label : placeholder}</span>
        </Listbox.Button>
        <Transition
          as={Fragment}
          leave="transition ease-in duration-100"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <Listbox.Options className="absolute z-50 mt-2 max-h-72 w-full overflow-auto rounded-lg bg-white py-2 shadow-xl ring-1 ring-black/10 focus:outline-none">
            {searchable && (
              <div className="px-3 pb-2">
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                  placeholder="Search..."
                />
              </div>
            )}

            {filtered.map((opt) => (
              <Listbox.Option
                key={opt.value}
                className={({ active }) =>
                  `cursor-pointer select-none px-4 py-2 text-sm ${
                    active ? 'bg-amber-50 text-amber-700' : 'text-gray-900'
                  }`
                }
                value={opt.value}
              >
                <div className="flex flex-col">
                  <span className="font-medium">{opt.label}</span>
                  {opt.subLabel && <span className="text-xs text-gray-500">{opt.subLabel}</span>}
                </div>
              </Listbox.Option>
            ))}

            {allowAddNew && (
              <Listbox.Option
                key="add_new"
                value="add_new"
                className={({ active }) =>
                  `cursor-pointer select-none px-4 py-2 text-sm font-medium ${
                    active ? 'bg-amber-100 text-amber-800' : 'text-amber-700'
                  }`
                }
              >
                {addNewLabel}
              </Listbox.Option>
            )}

            {filtered.length === 0 && (
              <div className="px-4 py-2 text-sm text-gray-500">No results</div>
            )}
          </Listbox.Options>
        </Transition>
      </div>
    </Listbox>
  )
}
