import BaseSelect from './BaseSelect'
import { Customer } from '../types'

interface CustomerSelectProps {
  customers: Customer[]
  value: string
  onChange: (id: string) => void
  placeholder?: string
  allowAddNew?: boolean
}

export default function CustomerSelect({
  customers,
  value,
  onChange,
  placeholder = 'Choose a customer',
  allowAddNew = true,
}: CustomerSelectProps) {
  return (
    <BaseSelect
      options={customers.map((c) => ({
        value: c.id,
        label: `${c.first_name} ${c.last_name}`,
        subLabel: c.email,
      }))}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      allowAddNew={allowAddNew}
      addNewLabel="+ Add new customer"
    />
  )
}
