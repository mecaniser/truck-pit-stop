import type { ChangeEventHandler } from 'react'
import { Search } from 'lucide-react'

type StaffSearchFieldProps = {
  accessibleLabel: string
  className?: string
  disabled?: boolean
  onChange?: ChangeEventHandler<HTMLInputElement>
  placeholder: string
  value?: string
}

export default function StaffSearchField({
  accessibleLabel,
  className = '',
  disabled = false,
  onChange,
  placeholder,
  value,
}: StaffSearchFieldProps) {
  return (
    <div className={`db-staff-search-field-inset${className ? ` ${className}` : ''}`}>
      <label className="db-staff-search-field">
        <span className="sr-only">{accessibleLabel}</span>
        <Search aria-hidden="true" />
        <input
          type="search"
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          disabled={disabled}
        />
      </label>
    </div>
  )
}
