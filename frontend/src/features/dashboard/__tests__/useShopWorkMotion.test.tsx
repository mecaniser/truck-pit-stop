import { render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useShopWorkMotion } from '../useShopWorkMotion'
function Board({ view }: { view: string }) {
  const ref = useShopWorkMotion(view)
  return <section ref={ref}><div className="db-overview"><div className="db-overview__row">{view}</div></div></section>
}
beforeEach(() => {
  Object.defineProperty(Element.prototype, 'animate', { configurable: true, writable: true, value: vi.fn() })
})
afterEach(() => vi.restoreAllMocks())
describe('Shop Work motion lifecycle', () => {
  it('cancels outgoing motion on view change and unmount without retaining old work', () => {
    const cancel = vi.fn()
    const animate = vi.spyOn(Element.prototype, 'animate').mockReturnValue({ cancel } as unknown as Animation)
    const { rerender, unmount, queryByText } = render(<Board view="overview" />)
    rerender(<Board view="closeout" />)
    expect(cancel).toHaveBeenCalled()
    expect(queryByText('overview')).toBeNull()
    expect(animate).toHaveBeenCalledTimes(2)
    unmount()
    expect(cancel).toHaveBeenCalledTimes(2)
  })
  it('skips animation for reduced motion', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true } as MediaQueryList)
    const animate = vi.spyOn(Element.prototype, 'animate')
    render(<Board view="active" />)
    expect(animate).not.toHaveBeenCalled()
  })
})
