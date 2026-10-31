import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import InvoiceReviewLink from '../InvoiceReviewLink'

describe('invoice review invitation', () => {
  it.each([null, undefined, '', 'javascript:alert(1)', 'http://example.com', 'https://user:pass@example.com'])('hides absent or unsafe links %s', url => {
    render(<InvoiceReviewLink url={url} />)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
  it('uses neutral copy and safe new-tab navigation', () => {
    render(<InvoiceReviewLink url="https://example.com/review?a=1&b=2" />)
    expect(screen.getByText(/Share your experience/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Leave a review' })).toHaveAttribute('href', 'https://example.com/review?a=1&b=2')
  })
})
