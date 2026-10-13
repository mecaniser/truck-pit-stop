import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import CostContributionBreakdown, { type ComponentContribution, type ProfitabilityResp } from '../CostContributionBreakdown'

const complete: ComponentContribution = {
  revenue: '200.00', known_cost: '120.00', line_count: 1, missing_cost_line_count: 0,
  status: 'complete', contribution: '80.00', margin_pct: '40.00',
}
const noLines: ComponentContribution = {
  revenue: '0.00', known_cost: '0.00', line_count: 0, missing_cost_line_count: 0,
  status: 'not_applicable', contribution: null, margin_pct: null,
}
function report(parts = complete, sublet = noLines): ProfitabilityResp {
  return {
    cost_basis: 'current_lines_before_order_discounts', labor_cost_status: 'unavailable',
    ros: [{ repair_order_id: 'order-1', order_number: 'RO-101', type: 'Repair', subtotal: 300, hours: 1, marginPct: null,
      parts_contribution: parts, sublet_contribution: sublet }],
  }
}
function show(data?: ProfitabilityResp) {
  render(<MemoryRouter><CostContributionBreakdown data={data} /></MemoryRouter>)
}

describe('Recorded component contribution', () => {
  it('labels the current line basis, cost exclusions and the order link', () => {
    show(report())
    const parts = screen.getByRole('region', { name: 'Parts contribution' })
    expect(parts).toHaveTextContent('$80.00')
    expect(parts).toHaveTextContent('40.00% margin')
    expect(parts).toHaveTextContent('Revenue $200.00')
    expect(parts).toHaveTextContent('Cost $120.00')
    expect(screen.getByText(/Current recorded lines before order discounts/)).toHaveTextContent('sublet also before labor discounts')
    expect(screen.getByText(/Whole-job margin unavailable/)).toHaveTextContent('Labor costs not recorded')
    expect(screen.getByRole('link', { name: 'RO-101' })).toHaveAttribute('href', '/dashboard/repair-orders?selected=order-1')
    expect(screen.getByText('No sublet lines')).toBeInTheDocument()
  })

  it('shows partial coverage and known expenses without implying a profit or a zero margin', () => {
    show(report({ ...complete, line_count: 2, missing_cost_line_count: 1, status: 'partial', contribution: null, margin_pct: null }))
    const parts = screen.getByRole('region', { name: 'Parts contribution' })
    expect(parts).toHaveTextContent('Partial costs · 1 of 2 lines have costs')
    expect(parts).toHaveTextContent('Known cost $120.00')
    expect(parts).toHaveTextContent('Contribution unavailable')
    expect(within(parts).queryByText(/% margin/)).not.toBeInTheDocument()
  })

  it('distinguishes missing expenses from known zero expenses', () => {
    show(report(
      { ...complete, known_cost: '0.00', missing_cost_line_count: 1, status: 'unavailable', contribution: null, margin_pct: null },
      { ...complete, revenue: '300.00', known_cost: '0.00', contribution: '300.00', margin_pct: '100.00' },
    ))
    const parts = screen.getByRole('region', { name: 'Parts contribution' })
    const sublet = screen.getByRole('region', { name: 'Sublet contribution' })
    expect(parts).toHaveTextContent('Costs unavailable · 0 of 1 lines have costs')
    expect(parts).toHaveTextContent('Contribution unavailable')
    expect(sublet).toHaveTextContent('100.00% margin')
    expect(sublet).toHaveTextContent('Cost $0.00')
  })

  it('keeps negative contribution and margin visible', () => {
    show(report({ ...complete, revenue: '100.00', contribution: '-20.00', margin_pct: '-20.00' }))
    const parts = screen.getByRole('region', { name: 'Parts contribution' })
    expect(parts).toHaveTextContent('-$20.00')
    expect(parts).toHaveTextContent('-20.00% margin')
  })

  it('shows a zero contribution as zero, while zero revenue has no percentage', () => {
    show(report(
      { ...complete, revenue: '120.00', contribution: '0.00', margin_pct: '0.00' },
      { ...complete, revenue: '0.00', known_cost: '20.00', contribution: '-20.00', margin_pct: null },
    ))
    expect(screen.getByRole('region', { name: 'Parts contribution' })).toHaveTextContent('$0.00')
    expect(screen.getByRole('region', { name: 'Parts contribution' })).toHaveTextContent('0.00% margin')
    expect(screen.getByRole('region', { name: 'Sublet contribution' })).toHaveTextContent('-$20.00')
    expect(screen.getByText('Margin unavailable — no positive revenue')).toBeInTheDocument()
  })

  it('does not fall back to a legacy numeric margin from an older backend', () => {
    show({ ros: [{ type: 'Repair', subtotal: 300, hours: 1, marginPct: 87 }] })
    expect(screen.getByText('Cost breakdown unavailable')).toBeInTheDocument()
    expect(screen.queryByText(/87/)).not.toBeInTheDocument()
    expect(screen.queryByText(/No repair orders/)).not.toBeInTheDocument()
  })

  it('shows unavailable component fields without losing the repair order', () => {
    const data = report()
    delete data.ros[0].parts_contribution
    show(data)
    expect(screen.getByRole('link', { name: 'RO-101' })).toBeInTheDocument()
    expect(screen.getByText('Parts: Cost breakdown unavailable')).toBeInTheDocument()
  })

  it('distinguishes a legitimate empty report from an unavailable response', () => {
    show({ ...report(), ros: [] })
    expect(screen.getByText('No repair orders in this date range.')).toBeInTheDocument()
    expect(screen.queryByText('Cost breakdown unavailable')).not.toBeInTheDocument()
  })
})
