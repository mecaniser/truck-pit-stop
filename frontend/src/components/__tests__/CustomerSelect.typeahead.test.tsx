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
})
