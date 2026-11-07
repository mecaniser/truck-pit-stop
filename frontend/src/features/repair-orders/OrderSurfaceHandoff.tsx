import { Component, createRef, type ReactNode } from 'react'

type Props = { orderId: string; ready: boolean; children: ReactNode }
type Snapshot = { panel: HTMLElement; offsets: number[]; navigationFocus: string | null } | null

// React's before-mutation lifecycle captures the still-painted order. The copy
// is presentation only. The incoming panel mounts normally and owns all reads.
export class OrderSurfaceHandoff extends Component<Props> {
  private live = createRef<HTMLDivElement>()
  private cover = createRef<HTMLDivElement>()

  private navigationFocus: string | null = null

  getSnapshotBeforeUpdate(previous: Props): Snapshot {
    if (previous.orderId === this.props.orderId || !previous.ready || this.props.ready) return null
    const source = this.live.current?.firstElementChild
    if (!(source instanceof HTMLElement)) return null
    const panel = source.cloneNode(true) as HTMLElement
    for (const element of [panel, ...panel.querySelectorAll('*')]) {
      element.removeAttribute('id')
      element.removeAttribute('name')
      element.removeAttribute('autofocus')
      element.removeAttribute('data-testid')
    }
    const focused = document.activeElement
    const label = source.contains(focused) ? focused?.getAttribute('aria-label') : null
    const navigationFocus = label === 'Next repair order' || label === 'Previous repair order' ? label : null
    return { panel, navigationFocus, offsets: Array.from(source.querySelectorAll('.db-workspace-scroll,.db-workspace-body'), el => el.scrollTop) }
  }

  componentDidUpdate(_previous: Props, _state: unknown, snapshot: Snapshot) {
    const cover = this.cover.current
    const live = this.live.current
    if (!cover || !live) return
    if (this.props.ready && cover.firstChild) {
      cover.replaceChildren()
      live.hidden = false
      if (this.navigationFocus && document.activeElement === document.body) {
        const next = live.querySelector<HTMLButtonElement>(`button[aria-label="${this.navigationFocus}"]:not(:disabled)`)
          ?? live.querySelector<HTMLButtonElement>('button[aria-label="Close repair order"]')
        next?.focus({ preventScroll: true })
      }
      this.navigationFocus = null
    } else if (snapshot) {
      this.navigationFocus = snapshot.navigationFocus
      cover.inert = true
      cover.replaceChildren(snapshot.panel)
      snapshot.panel.querySelectorAll('.db-workspace-scroll,.db-workspace-body').forEach((el, index) => {
        el.scrollTop = snapshot.offsets[index]
      })
      live.hidden = true
    }
  }

  render() {
    return <div className="db-order-handoff relative h-full min-h-0">
      <div ref={this.live} className="db-order-live h-full">{this.props.children}</div>
      <div ref={this.cover} aria-hidden="true" className="db-order-cover absolute inset-0 overflow-hidden" />
      <span className="sr-only" role="status">{this.props.ready ? '' : 'Opening repair order…'}</span>
    </div>
  }
}
