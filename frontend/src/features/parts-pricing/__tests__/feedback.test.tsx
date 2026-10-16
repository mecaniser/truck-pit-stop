import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PricingFeedback from '../PricingFeedback'

afterEach(() => vi.restoreAllMocks())

function rectangle(top: number, bottom: number): DOMRect {
  return { top, bottom, height: bottom - top, left: 0, right: 300, width: 300, x: 0, y: top, toJSON: () => ({}) }
}

describe('pricing feedback visibility', () => {
  it.each([
    { description: 'success below the fold', top: 480, bottom: 550, expected: 158 },
    { description: 'error above the fold', top: 50, bottom: 90, expected: 42 },
    { description: 'already visible outcome', top: 150, bottom: 200, expected: 100 },
    { description: 'outcome taller than the work area', top: 150, bottom: 650, expected: 142 },
  ])('reveals $description only inside the panel scroller', ({ top, bottom, expected }) => {
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      return this.classList.contains('db-slide-panel-form__content') ? rectangle(100, 500) : rectangle(top, bottom)
    })
    const focus = vi.spyOn(HTMLElement.prototype, 'focus')
    const outer = document.createElement('div'); outer.scrollTop = 200
    const scroller = document.createElement('div'); scroller.className = 'db-slide-panel-form__content'; scroller.scrollTop = 100
    outer.append(scroller); document.body.append(outer)
    const view = render(<PricingFeedback role="status" revision={{}}>Proposed $130 · Profit $30</PricingFeedback>, { container: scroller })
    expect(scroller.scrollTop).toBe(expected)
    expect(outer.scrollTop).toBe(200)
    expect(document.scrollingElement?.scrollTop ?? 0).toBe(0)
    expect(screen.getByRole('status')).toHaveFocus()
    expect(focus).toHaveBeenLastCalledWith({ preventScroll: true })
    view.unmount(); outer.remove()
  })

  it('does not refocus on draft edits, but reveals a repeated action outcome', () => {
    const revision = { message: 'Bands must be contiguous.' }
    const content = (response: object) => <div className="db-slide-panel-form__content"><input aria-label="Cost from" /><PricingFeedback revision={response}>Bands must be contiguous.</PricingFeedback></div>
    const view = render(content(revision))
    expect(screen.getByRole('alert')).toHaveFocus()
    screen.getByLabelText('Cost from').focus()
    view.rerender(content(revision))
    expect(screen.getByLabelText('Cost from')).toHaveFocus()
    view.rerender(content({ message: revision.message }))
    expect(screen.getByRole('alert')).toHaveFocus()
  })
})
