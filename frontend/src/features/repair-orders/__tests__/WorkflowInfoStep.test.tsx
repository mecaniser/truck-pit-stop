import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import WorkflowInfoStep, { type WorkflowInfo } from '../WorkflowInfoStep'
const info: WorkflowInfo = { created_at: '2026-09-12T09:00:00Z', work_started_at: '2026-09-12T10:00:00Z', work_completed_at: '2026-09-12T13:30:00Z', actual_tracked_minutes: 75, internal_notes: null }
describe('Workflow informational steps', () => {
  it('separates elapsed job duration from tracked labor and provides no mutation', async () => {
    const user = userEvent.setup()
    render(<WorkflowInfoStep stage="bay" label="In the bay" className="" status="pending_review" info={info} operationCount={3} />)
    await user.click(screen.getByRole('button', { name: 'In the bay' }))
    expect(screen.getByText('3h 30m')).toBeVisible()
    expect(screen.getByText('1h 15m')).toBeVisible()
    expect(screen.getByText('3 labor / operation lines')).toBeVisible()
    expect(screen.queryByRole('button', { name: /assign|start work|complete/i })).not.toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByLabelText('In-the-bay details')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'In the bay' })).toHaveFocus()
  })
  it('does not turn missing or reversed timestamps into durations', async () => {
    const user = userEvent.setup()
    render(<WorkflowInfoStep stage="bay" label="In the bay" className="" status="pending_review" info={{ ...info, work_started_at: '2026-09-13T10:00:00Z', actual_tracked_minutes: null }} />)
    await user.click(screen.getByRole('button', { name: 'In the bay' }))
    expect(screen.getAllByText('Not available').length).toBeGreaterThan(0)
    expect(screen.getByText('Not recorded')).toBeVisible()
  })
  it('separates saved reviews from unsaved drafts and unrelated internal notes', async () => {
    const user = userEvent.setup()
    render(<WorkflowInfoStep stage="review" label="Quality review" className="" status="pending_review" reviewDraft="Check coolant again" info={{ ...info, internal_notes: JSON.stringify({ raw_notes: 'not a review', reviews: [{ type: 'manager_review', notes: 'Road test passed', reviewed_by: 'Sam', reviewed_at: '2026-09-12T14:00:00Z' }] }) }} />)
    await user.click(screen.getByRole('button', { name: 'Quality review' }))
    expect(screen.getByText('Road test passed')).toBeVisible()
    expect(screen.getByText('Unsaved review notes')).toBeVisible()
    expect(screen.queryByText('not a review')).not.toBeInTheDocument()
  })
  it('updates shop-managed information when a technician is assigned without claiming a new start', async () => {
    const user = userEvent.setup()
    const props = { stage: 'technician' as const, label: 'Shop-managed', className: '', status: 'in_progress', info }
    const view = render(<WorkflowInfoStep {...props} />)
    await user.click(screen.getByRole('button', { name: 'Technician status' }))
    expect(screen.getByText('No technician assigned')).toBeVisible()
    expect(screen.getByText('Started 1h 0m after order opened')).toBeVisible()
    expect(screen.queryByText('Assigned')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Technician details' })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Close technician details' })).toHaveFocus()
    view.rerender(<WorkflowInfoStep {...props} technician="Mike Johnson" info={{ ...info, assigned_at: '2026-09-12T11:00:00Z' }} />)
    expect(screen.getByText('Mike Johnson')).toBeVisible()
    expect(screen.getByText('Assigned')).toBeVisible()
    expect(screen.getByText('Awaiting acknowledgment')).toBeVisible()
    expect(screen.getByText('Repair started')).toBeVisible()
    expect(screen.queryByText('No technician assigned')).not.toBeInTheDocument()
  })
  it('uses a filling circle to signal an open pipeline popover instead of a dropdown caret', async () => {
    const user = userEvent.setup()
    const { container } = render(<WorkflowInfoStep stage="technician" label="Shop-managed" className="" status="in_progress" info={info} />)
    const indicator = screen.getByTestId('workflow-popover-indicator')
    expect(indicator).toHaveAttribute('data-open', 'false')
    expect(container.querySelector('[data-lucide="chevron-down"]')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Technician status' }))
    expect(indicator).toHaveAttribute('data-open', 'true')
    expect(indicator.firstElementChild).toHaveClass('scale-100')
  })
  it('handles malformed legacy notes without inventing reviews', async () => {
    const user = userEvent.setup()
    render(<WorkflowInfoStep stage="review" label="Quality review" className="" status="draft" info={{ ...info, internal_notes: 'legacy plain text' }} />)
    await user.click(screen.getByRole('button', { name: 'Quality review' }))
    expect(screen.getByText('No saved quality-review notes.')).toBeVisible()
    expect(screen.getByText('Work has not reached quality review')).toBeVisible()
  })
})
