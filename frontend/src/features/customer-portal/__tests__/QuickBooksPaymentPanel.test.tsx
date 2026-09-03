import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import QuickBooksPaymentPanel from '../QuickBooksPaymentPanel'

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

describe('QuickBooksPaymentPanel theme', () => {
  it('uses light invoice fields when rendered inside the guest invoice', () => {
    render(
      <QuickBooksPaymentPanel
        tokenUrl="https://sandbox.api.intuit.com/quickbooks/v4/payments/tokens"
        tone="light"
        onToken={vi.fn()}
        onSuccess={vi.fn()}
      />,
    )

    const nameInput = screen.getByLabelText('Name on card')
    expect(nameInput).toHaveClass('bg-white', 'text-slate-950', 'border-slate-300')
    expect(screen.getByRole('button', { name: /submit secure payment/i })).toHaveClass('text-white')
  })

  it('preserves the dark customer-portal treatment by default', () => {
    render(
      <QuickBooksPaymentPanel
        tokenUrl="https://sandbox.api.intuit.com/quickbooks/v4/payments/tokens"
        onToken={vi.fn()}
        onSuccess={vi.fn()}
      />,
    )

    expect(screen.getByLabelText('Name on card')).toHaveClass('bg-[#161a26]', 'text-white')
  })

  it('formats and caps every sensitive payment field', () => {
    render(
      <QuickBooksPaymentPanel
        tokenUrl="https://sandbox.api.intuit.com/quickbooks/v4/payments/tokens"
        tone="light"
        onToken={vi.fn()}
        onSuccess={vi.fn()}
      />,
    )

    fireEvent.change(screen.getByLabelText('Card number'), { target: { value: '4242x4242-4242 4242 999999' } })
    fireEvent.change(screen.getByLabelText('Expiry'), { target: { value: '122030999' } })
    fireEvent.change(screen.getByLabelText('Security code'), { target: { value: '12a3456' } })
    fireEvent.change(screen.getByLabelText('Billing ZIP code'), { target: { value: '53703abc123499' } })

    expect(screen.getByLabelText('Card number')).toHaveValue('4242 4242 4242 4242 999')
    expect(screen.getByLabelText('Expiry')).toHaveValue('12 / 2030')
    expect(screen.getByLabelText('Security code')).toHaveValue('1234')
    expect(screen.getByLabelText('Billing ZIP code')).toHaveValue('53703-1234')
  })

  it('blocks tokenization and identifies invalid payment fields', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    render(
      <QuickBooksPaymentPanel
        tokenUrl="https://sandbox.api.intuit.com/quickbooks/v4/payments/tokens"
        onToken={vi.fn()}
        onSuccess={vi.fn()}
      />,
    )

    fireEvent.change(screen.getByLabelText('Name on card'), { target: { value: 'Truck Pit Stop' } })
    fireEvent.change(screen.getByLabelText('Card number'), { target: { value: '123' } })
    fireEvent.change(screen.getByLabelText('Expiry'), { target: { value: '132030' } })
    fireEvent.change(screen.getByLabelText('Security code'), { target: { value: '12' } })
    fireEvent.change(screen.getByLabelText('Billing ZIP code'), { target: { value: '123' } })
    fireEvent.click(screen.getByRole('button', { name: /submit secure payment/i }))

    expect(fetchSpy).not.toHaveBeenCalled()
    expect(screen.getByText('Enter a valid 13–19 digit card number.')).toBeInTheDocument()
    expect(screen.getByText('Enter a valid future expiry date.')).toBeInTheDocument()
    expect(screen.getByText('Enter a 3 or 4 digit security code.')).toBeInTheDocument()
    expect(screen.getByText('Enter a 5 digit ZIP or ZIP+4.')).toBeInTheDocument()
    fetchSpy.mockRestore()
  })

  it('sends only normalized values to Intuit tokenization', async () => {
    const onToken = vi.fn().mockResolvedValue(undefined)
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ value: 'opaque-intuit-token' }),
    } as unknown as Response)

    render(
      <QuickBooksPaymentPanel
        tokenUrl="https://sandbox.api.intuit.com/quickbooks/v4/payments/tokens"
        onToken={onToken}
        onSuccess={vi.fn()}
      />,
    )

    fireEvent.change(screen.getByLabelText('Name on card'), { target: { value: ' Truck Pit Stop ' } })
    fireEvent.change(screen.getByLabelText('Card number'), { target: { value: '4242424242424242' } })
    fireEvent.change(screen.getByLabelText('Expiry'), { target: { value: '122030' } })
    fireEvent.change(screen.getByLabelText('Security code'), { target: { value: '123' } })
    fireEvent.change(screen.getByLabelText('Billing ZIP code'), { target: { value: '537031234' } })
    fireEvent.click(screen.getByRole('button', { name: /submit secure payment/i }))

    await waitFor(() => expect(onToken).toHaveBeenCalledWith('opaque-intuit-token'))
    const request = fetchSpy.mock.calls[0]?.[1]
    expect(JSON.parse(String(request?.body))).toEqual({
      card: {
        number: '4242424242424242',
        cvc: '123',
        expMonth: '12',
        expYear: '2030',
        name: 'Truck Pit Stop',
        address: { country: 'US', postalCode: '53703-1234' },
      },
    })
    fetchSpy.mockRestore()
  })
})
