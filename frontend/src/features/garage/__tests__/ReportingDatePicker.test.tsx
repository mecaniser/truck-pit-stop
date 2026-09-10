import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import ReportingDatePicker from '../ReportingDatePicker'
import { readReportRange, rangeError } from '../reportRange'

beforeAll(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
const resolved = { range_start: '2026-09-01', range_end: '2026-09-10' }
async function setup() {
  const onChange = vi.fn()
  const user = userEvent.setup()
  render(<ReportingDatePicker value={{ range: 'this_month' }} resolved={resolved} onChange={onChange} />)
  const trigger = screen.getByRole('button', { name: /This month/ })
  await user.click(trigger)
  return { user, onChange, trigger, panel: within(screen.getByRole('dialog')) }
}
describe('reporting date picker', () => {
  it('keeps preset changes as drafts until applied and sends no custom dates', async () => {
    const { user, panel, onChange, trigger } = await setup()
    await user.click(panel.getByRole('button', { name: 'Last quarter' }))
    expect(onChange).not.toHaveBeenCalled()
    await user.click(panel.getByRole('button', { name: 'Apply period' }))
    expect(onChange).toHaveBeenCalledWith({ range: 'last_quarter' })
    expect(trigger).toHaveFocus()
  })
  it('supports a custom leap-day range without shifting date-only values', async () => {
    const { user, panel, onChange } = await setup()
    fireEvent.change(panel.getByLabelText('Start date'), { target: { value: '2024-02-29' } })
    fireEvent.change(panel.getByLabelText('End date'), { target: { value: '2024-03-10' } })
    await user.click(panel.getByRole('button', { name: 'Apply period' }))
    expect(onChange).toHaveBeenCalledWith({ range: 'custom', from_date: '2024-02-29', to_date: '2024-03-10' })
  })
  it('blocks reversed and incomplete dates', async () => {
    const { panel } = await setup()
    fireEvent.change(panel.getByLabelText('Start date'), { target: { value: '2026-09-20' } })
    expect(panel.getByRole('button', { name: 'Apply period' })).toBeDisabled()
    expect(panel.getByRole('status')).toHaveTextContent('End date must be on or after')
    fireEvent.change(panel.getByLabelText('End date'), { target: { value: '' } })
    expect(panel.getByRole('button', { name: 'Apply period' })).toBeDisabled()
  })
  it('selects calendar endpoints in either order and permits a single day', async () => {
    const { user, panel, onChange } = await setup()
    await user.click(panel.getByRole('button', { name: 'Sep 20, 2026' }))
    expect(panel.getByRole('button', { name: 'Apply period' })).toBeDisabled()
    await user.click(panel.getByRole('button', { name: 'Sep 5, 2026' }))
    expect(panel.getByLabelText('Start date')).toHaveValue('2026-09-05')
    expect(panel.getByLabelText('End date')).toHaveValue('2026-09-20')
    await user.click(panel.getByRole('button', { name: 'Sep 8, 2026' }))
    await user.click(panel.getByRole('button', { name: 'Sep 8, 2026' }))
    await user.click(panel.getByRole('button', { name: 'Apply period' }))
    expect(onChange).toHaveBeenCalledWith({ range: 'custom', from_date: '2026-09-08', to_date: '2026-09-08' })
  })
  it('cancels without applying and resets drafts when reopened', async () => {
    const { user, panel, onChange, trigger } = await setup()
    await user.click(panel.getByRole('button', { name: 'Last year' }))
    await user.click(panel.getByRole('button', { name: 'Cancel' }))
    expect(onChange).not.toHaveBeenCalled()
    expect(trigger).toHaveFocus()
    await user.click(trigger)
    expect(panel.getByRole('button', { name: 'This month', exact: true })).toHaveAttribute('aria-pressed', 'true')
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { cancelable: true }))
    expect(trigger).toHaveFocus()
  })
  it('has one roving calendar stop and keyboard navigation across months', async () => {
    const { panel } = await setup()
    const day = panel.getByRole('button', { name: 'Sep 1, 2026' })
    act(() => day.focus())
    fireEvent.keyDown(day, { key: 'ArrowLeft' })
    const previous = await screen.findByRole('button', { name: 'Aug 31, 2026' })
    expect(previous).toHaveAttribute('tabindex', '0')
    expect(document.querySelectorAll('[data-day][tabindex="0"]')).toHaveLength(1)
  })
  it('keeps the focused second month visible when compact mode begins', async () => {
    let onResize = () => {}
    const media = { matches: false, addEventListener: (_: string, callback: () => void) => { onResize = callback }, removeEventListener: () => {} }
    const original = window.matchMedia
    window.matchMedia = vi.fn().mockReturnValue(media)
    try {
      const { user, panel } = await setup()
      await user.click(panel.getByRole('button', { name: 'Oct 5, 2026', exact: true }))
      act(() => { media.matches = true; onResize() })
      const focused = panel.getByRole('button', { name: 'Oct 5, 2026', exact: true })
      expect(focused).toHaveAttribute('tabindex', '0')
      expect(focused.closest('section')).not.toHaveClass('db-report-calendar--second')
      expect(document.querySelectorAll('[data-day][tabindex="0"]')).toHaveLength(1)
    } finally { window.matchMedia = original }
  })
})
describe('report period URL validation', () => {
  it.each(['2023-02-29', '2024-02-30', 'not-a-date', '0000-01-01'])('rejects invalid date %s', date => {
    expect(rangeError(date, '2026-09-10')).not.toBeNull()
  })
  it('defaults malformed URLs and retains valid custom periods', () => {
    expect(readReportRange(new URLSearchParams('range=custom&from_date=2026-09-10&to_date=2026-09-01'))).toEqual({ range: 'this_month' })
    expect(readReportRange(new URLSearchParams('range=custom&from_date=2024-02-29&to_date=2024-02-29'))).toEqual({ range: 'custom', from_date: '2024-02-29', to_date: '2024-02-29' })
    expect(readReportRange(new URLSearchParams('range=toString'))).toEqual({ range: 'this_month' })
  })
})
