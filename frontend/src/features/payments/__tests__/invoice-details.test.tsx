import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import InvoiceDetailsDisclosure from '../InvoiceDetailsDisclosure'

const summary = { ...DB048_SETTLEMENT_FIXTURES.unpaid.summary,
  breakdown: { labor_total: '100.00', parts_total: '104.50', subtotal: '204.50', shop_supplies_amount: '3.00', sales_tax_amount: '0.00', discount_amount: '0.00', principal_total: '207.50' } }

describe('Invoice details', () => {
  it('opens saved labor/parts with an accessible disclosure and no invented rate', async () => {
    render(<InvoiceDetailsDisclosure summary={summary} />)
    const button = screen.getByRole('button', { name: 'View details' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('$100.00')).not.toBeInTheDocument()
    button.focus()
    await userEvent.keyboard('{Enter}')
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('$100.00')).toBeInTheDocument()
    expect(screen.getByText('$104.50')).toBeInTheDocument()
    expect(screen.getByText(/not parts/)).toBeInTheDocument()
    for (const label of ['Invoice total', 'Available to pay', 'Sales tax', 'Shop supplies', 'Confirmed payments']) {
      expect(screen.queryByText(label)).not.toBeInTheDocument()
    }
    await userEvent.click(button)
    expect(screen.queryByText('$100.00')).not.toBeInTheDocument()
  })
  it('does not invent missing historical data', async () => {
    render(<InvoiceDetailsDisclosure summary={{ ...summary, breakdown: undefined }} />)
    await userEvent.click(screen.getByRole('button', { name: 'View details' }))
    expect(screen.getByText('Labor/parts breakdown wasn’t saved.')).toBeInTheDocument()
    expect(screen.queryByText(/Labor ·/)).not.toBeInTheDocument()
  })
  it('preserves disclosure during fee updates and resets for another invoice', async () => {
    const { rerender } = render(<InvoiceDetailsDisclosure key="one" summary={summary} />)
    await userEvent.click(screen.getByRole('button', { name: 'View details' }))
    rerender(<InvoiceDetailsDisclosure key="one" summary={{ ...summary, version: 2 }} />)
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'true')
    rerender(<InvoiceDetailsDisclosure key="two" summary={{ ...summary, invoice_id: 'two' }} />)
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'false')
  })
})
