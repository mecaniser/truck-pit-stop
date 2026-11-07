import { render } from '@testing-library/react'
import { expect, it } from 'vitest'
import { OrderSurfaceHandoff } from '../OrderSurfaceHandoff'

function panel(id: string, ready: boolean, scope = 'shop-a') {
  return <OrderSurfaceHandoff key={scope} orderId={id} ready={ready}>
    <section><h3>{id}</h3><button id="action" name="action">Edit {id}</button></section>
  </OrderSurfaceHandoff>
}

it('holds one inert presentation through interrupted selection and removes it when the latest record is ready', () => {
  const view = render(panel('A', true))
  view.rerender(panel('B', false))
  const cover = view.container.querySelector<HTMLElement>('.db-order-cover')!
  expect(cover.inert).toBe(true)
  expect(cover.querySelector('h3')).toHaveTextContent('A')
  expect(cover.querySelector('[id],[name]')).toBeNull()
  view.rerender(panel('C', false))
  expect(cover.querySelector('h3')).toHaveTextContent('A')
  view.rerender(panel('C', true))
  expect(cover).toBeEmptyDOMElement()
  expect(view.container.querySelector('h3')).toHaveTextContent('C')
  expect(view.container.querySelector<HTMLElement>('.db-order-live')!.hidden).toBe(false)
})

it('discards the outgoing presentation immediately on a session or shop change', () => {
  const view = render(panel('private A', true))
  view.rerender(panel('private B', false))
  view.rerender(panel('other shop', false, 'shop-b'))
  expect(view.container).not.toHaveTextContent('private')
  expect(view.container.querySelector('.db-order-cover')).toBeEmptyDOMElement()
})
