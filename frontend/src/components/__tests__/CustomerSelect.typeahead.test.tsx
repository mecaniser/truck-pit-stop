import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/contexts/ThemeContext', () => ({
  useTheme: () => ({ accentColors: { 400: '#60a5fa', 500: '#3b82f6', 600: '#2563eb' } }),
}))

import CustomerSelect from '../CustomerSelect'

describe('CustomerSelect server-side typeahead', () => {
  it('keeps the typed search text while a new result set is loading', () => {
    const onQueryChange = vi.fn()
    const props = {
      customers: [],
      value: '',
      onChange: vi.fn(),
      onQueryChange,
      searchLoading: false,
    }
    const { rerender } = render(<CustomerSelect {...props} />)

    fireEvent.click(screen.getByRole('button', { name: /choose a customer/i }))
    const input = screen.getByPlaceholderText('Choose a customer')
    fireEvent.change(input, { target: { value: 'Acme' } })

    expect(onQueryChange).toHaveBeenLastCalledWith('Acme')
    expect(input).toHaveValue('Acme')

    rerender(<CustomerSelect {...props} isLoading searchLoading />)

    expect(screen.getByPlaceholderText('Choose a customer')).toHaveValue('Acme')
  })

  it('supports keyboard navigation and selection', () => {
    const onChange = vi.fn()

    render(
      <CustomerSelect
        customers={[
          {
            id: 'customer-1',
            first_name: 'Alice',
            last_name: 'Owner',
            company_name: 'Alpha Logistics',
            email: 'alice@example.com',
          },
          {
            id: 'customer-2',
            first_name: 'Bob',
            last_name: 'Manager',
            company_name: 'Beta Freight',
            email: 'bob@example.com',
          },
        ]}
        value=""
        onChange={onChange}
      />,
    )

    const button = screen.getByRole('button', { name: /choose a customer/i })
    fireEvent.keyDown(button, { key: 'ArrowDown' })

    const input = screen.getByRole('combobox')
    expect(input).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('listbox')).toBeInTheDocument()

    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(onChange).toHaveBeenCalledWith('customer-2')
  })

  it('routes the add-new menu action through onChange when no custom add handler is provided', () => {
    const onChange = vi.fn()

    render(
      <CustomerSelect
        customers={[]}
        value=""
        onChange={onChange}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /choose a customer/i }))
    fireEvent.mouseDown(screen.getByRole('option', { name: /\+ add new customer/i }))

    expect(onChange).toHaveBeenCalledWith('add_new')
  })
})
