import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import CashReceiptsByCustomer, { type CashReceipt } from '../CashReceiptsByCustomer'
const receipt = (payment: string, customer: string, amount: string, invoice = payment, name = 'Elis Logistics LLC'): CashReceipt => ({
  payment_id: payment, payment_number: `PAY-${payment}`, customer_id: customer, invoice_id: invoice,
  invoice_number: `INV-${invoice}`, customer_name: name, amount, received_at: '2026-09-12T12:00:00Z',
})
describe('Cash receipts by company', () => {
  it('shows the server-provided shop date across UTC midnight', async () => {
    render(<CashReceiptsByCustomer receipts={[{ ...receipt('1', 'elis', '10'), received_at: '2026-09-13T00:14:00Z', received_on: '2026-09-12' }]} />)
    await userEvent.click(screen.getByText('Elis Logistics LLC'))
    expect(screen.getByText('Sep 12, 2026 shop time')).toBeVisible()
    expect(screen.queryByText('Sep 13, 2026 UTC')).not.toBeInTheDocument()
  })
  it('shows exact totals and unique invoice counts with independently expandable receipts', async () => {
    render(<CashReceiptsByCustomer receipts={[receipt('1', 'elis', '0.10', 'one'), receipt('2', 'elis', '0.20', 'one'), receipt('3', 'elis', '10.00', 'two'), receipt('4', 'avanti', '7.00', 'three', 'Avanti LLC')]} />)
    const company = screen.getByText('Elis Logistics LLC').closest('details')!
    const other = screen.getByText('Avanti LLC').closest('details')!
    expect(company.open).toBe(false)
    expect(company.querySelector('summary')).toHaveTextContent('$10.30')
    expect(company.querySelector('summary')).toHaveTextContent('2 invoices · 3 cash receipts')
    expect(other.querySelector('summary')).toHaveTextContent('$7.00')
    await userEvent.click(screen.getByText('Elis Logistics LLC'))
    expect(company.open).toBe(true)
    expect(other.open).toBe(false)
    expect(within(company).getByText('PAY-1 · INV-one')).toBeVisible()
    expect(within(company).queryByText('PAY-4 · INV-three')).not.toBeInTheDocument()
    await userEvent.click(screen.getByText('Elis Logistics LLC'))
    expect(company.open).toBe(false)
  })
  it('keeps identical company names from separate accounts distinct', () => {
    render(<CashReceiptsByCustomer receipts={[receipt('1', 'a', '10'), receipt('2', 'b', '20')]} />)
    expect(screen.getAllByText('Elis Logistics LLC')).toHaveLength(2)
    expect(screen.queryByText('$30.00')).not.toBeInTheDocument()
  })
  it('does not guess identity from names when an older API omits IDs', () => {
    render(<CashReceiptsByCustomer receipts={[{ ...receipt('1', 'a', '10'), customer_id: undefined }, { ...receipt('2', 'b', '20'), customer_id: undefined }]} />)
    expect(screen.getAllByText('Elis Logistics LLC')).toHaveLength(2)
  })
  it('refreshes totals and customers when the reporting period changes', () => {
    const { rerender } = render(<CashReceiptsByCustomer receipts={[receipt('1', 'a', '10')]} />)
    rerender(<CashReceiptsByCustomer receipts={[receipt('2', 'b', '20', 'two', 'Jane Doe')]} />)
    expect(screen.queryByText('Elis Logistics LLC')).not.toBeInTheDocument()
    expect(screen.getByText('Jane Doe').closest('summary')).toHaveTextContent('$20.00')
  })
})
