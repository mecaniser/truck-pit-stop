import { Spinner } from '@/components/ui'
import BaseSelect from './BaseSelect'
import { Customer } from '../types'
import { formatUSPhone } from '../utils/phone'
import { customerDisplayName, customerPersonalName } from '../lib/customerName'

interface CustomerSelectProps {
  customers: Customer[]
  value: string
  onChange: (id: string) => void
  placeholder?: string
  allowAddNew?: boolean
  onAddNew?: () => void
  variant?: 'light' | 'dark'
  /** Which field to show as the secondary line in the dropdown */
  subLabelField?: 'email' | 'phone'
  /** When true, shows an inline phone input if the selected customer has no phone */
  phoneRequired?: boolean
  phoneValue?: string
  onPhoneChange?: (phone: string) => void
  /** While true, the select is disabled and shows a "Loading customers…" state
   * instead of an empty/unresponsive-looking dropdown. */
  isLoading?: boolean
}

export default function CustomerSelect({
  customers,
  value,
  onChange,
  placeholder = 'Choose a customer',
  allowAddNew = true,
  onAddNew,
  variant = 'light',
  subLabelField = 'email',
  phoneRequired = false,
  phoneValue = '',
  onPhoneChange,
  isLoading = false,
}: CustomerSelectProps) {
  const selectedCustomer = customers.find((c) => c.id === value)
  const needsPhone = phoneRequired && !!selectedCustomer && !selectedCustomer.phone

  function subLabel(c: Customer): string | undefined {
    if (subLabelField === 'phone') {
      return c.phone ? formatUSPhone(c.phone) : 'no phone'
    }
    return c.email ?? undefined
  }

  return (
    <div className="flex flex-col gap-2">
      {isLoading ? (
        <div
          className={`flex h-[42px] w-full items-center gap-2 rounded-lg border px-4 text-sm ${
            variant === 'dark'
              ? 'border-white/20 bg-white/10 text-gray-400'
              : 'border-gray-300 bg-gray-50 text-gray-500'
          }`}
        >
          <Spinner size="xs" />
          Loading customers…
        </div>
      ) : (
        <BaseSelect
          options={customers.map((c) => ({
            value: c.id,
            label: customerDisplayName(c, `${c.first_name} ${c.last_name}`.trim()),
            subLabel: subLabel(c),
            // Company name is shown as the label, but the contact's personal
            // name should still be searchable even when it isn't displayed.
            searchText: customerPersonalName(c),
          }))}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          allowAddNew={allowAddNew}
          addNewLabel="+ Add new customer"
          onAddNew={onAddNew}
          variant={variant}
        />
      )}

      {needsPhone && (
        <div>
          <input
            className={`w-full rounded-lg border px-3 py-2 text-sm focus:outline-none transition-colors ${
              variant === 'dark'
                ? 'border-amber-400/40 bg-white/10 text-white placeholder:text-gray-500 focus:border-amber-400/70'
                : 'border-amber-400 bg-amber-50 text-gray-900 placeholder:text-gray-400 focus:border-amber-500'
            }`}
            placeholder="Phone number (will be saved to customer)…"
            value={phoneValue}
            onChange={(e) => onPhoneChange?.(e.target.value)}
          />
          <p className="mt-1 text-[11px] text-amber-400/80">
            This customer has no phone on file. Enter one to enable SMS.
          </p>
        </div>
      )}
    </div>
  )
}
