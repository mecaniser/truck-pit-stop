import { Listbox, ListboxButton, ListboxOption, ListboxOptions } from '@headlessui/react'
import { Check, ChevronDown } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useTheme, appearanceTokenRecord } from '@/contexts/ThemeContext'
import './shopWorkSelect.css'

/** Existing Headless UI selection behavior with Shop Work's compact theme. */
export default function ShopWorkSelect<T extends string>({ label, value, options, onChange }: {
  label: string
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
}) {
  const { appearance } = useTheme()
  // Anchored menus portal outside the staff shell, so carry its theme tokens.
  const menuStyle = appearanceTokenRecord(appearance) as CSSProperties
  return <Listbox value={value} onChange={onChange}>
    <ListboxButton aria-label={label} className="db-work-select">
      <span>{options.find(option => option.value === value)?.label ?? 'Choose…'}</span>
      <ChevronDown size={16} aria-hidden="true" />
    </ListboxButton>
    <ListboxOptions style={menuStyle} data-appearance-mode={appearance.mode} anchor="bottom start" className="db-work-select-menu">
      {options.map(option => <ListboxOption key={option.value} value={option.value} className="db-work-select-option">
        {({ selected }) => <><span>{option.label}</span>{selected && <Check size={16} aria-hidden="true" />}</>}
      </ListboxOption>)}
    </ListboxOptions>
  </Listbox>
}
