import { beforeEach, describe, expect, it } from 'vitest'
import viewModule from '../../../backend/scripts/easytruck_sync/lib/contact_view.js'
import snapshotModule from '../../../backend/scripts/easytruck_sync/lib/contact_snapshot.js'

const { readContactView } = viewModule
const { contactSnapshot } = snapshotModule
const options = { shop: 'shop_test', customerId: '123', observedAt: '2026-10-16T00:00:00Z' }
// Sanitized structural fixture grounded in the authenticated source DOM:
// the visible text label is a sibling of inputContent, with an empty switch label.
const fixture = `<header><span>customer</span><h2>Test account</h2><span>Contact</span>
<a href="tel:7045551234">7045551234</a><nav><a href="/shop_test/customers/123">Vehicles</a>
<a href="/shop_test/customers/123/contacts">Contacts</a></nav></header>
<div id="filter-search-input"><div><input placeholder="Search"></div></div>
<div id="archive-control"><label> Show archived </label><div class="inputContent"><label class="switch"><input type="checkbox"><span></span></label></div><div class="support"></div></div>
<table><thead><tr>${['Role','First Name','Last Name','Phone','Email','notes'].map(x=>`<th>${x}</th>`).join('')}</tr></thead>
<tbody><tr>${['Owner','','','7045555678','',''].map(x=>`<td>${x}</td>`).join('')}</tr></tbody></table>
<div>Showing 1 to 1 of 1 results</div>`
const result = () => contactSnapshot(readContactView(), options)
beforeEach(() => {
  window.history.replaceState({}, '', '/shop_test/customers/123/contacts')
  document.body.innerHTML = fixture
  Object.defineProperty(HTMLElement.prototype, 'innerText', { configurable: true, get() { return this.textContent } })
})
describe('ETS contact DOM proof', () => {
  it('accepts observed unchecked sibling switch and CSS-uppercase labels', () => {
    expect(readContactView()).toMatchObject({ archived: false, searchValue: '', headerBound: true })
    expect(result()).toMatchObject({complete:true,phones:['7045551234','7045555678']})
  })
  it.each([
    ['checked', () => { document.querySelector('input[type=checkbox]').checked = true }],
    ['missing checkbox', () => document.querySelector('input[type=checkbox]').remove()],
    ['duplicate checkbox', () => document.querySelector('.switch').insertAdjacentHTML('beforeend','<input type="checkbox">')],
    ['duplicate archive label', () => document.body.insertAdjacentHTML('beforeend','<label>Show archived</label>')],
    ['unrelated sibling checkbox', () => document.querySelector('.switch').classList.remove('switch')],
    ['wrong wrapper', () => document.body.append(document.querySelector('.inputContent'))],
    ['second named control', () => document.querySelector('#archive-control').insertAdjacentHTML('beforeend','<label>Other setting</label>')],
    ['nonempty search', () => { document.querySelector('input[placeholder=Search]').value = 'driver' }],
    ['missing search', () => document.querySelector('#filter-search-input').remove()],
    ['duplicate search', () => document.querySelector('#filter-search-input').insertAdjacentHTML('beforeend','<input>')],
  ])('holds %s', (_, mutate) => {
    mutate(); expect(result()).toMatchObject({complete:false,reason:'filtered',phones:[]})
  })
  it.each([
    ['wrong account', () => window.history.replaceState({}, '', '/shop_test/customers/999/contacts')],
    ['unbound header', () => document.querySelector('nav').remove()],
    ['wrong schema', () => { document.querySelector('th').textContent = 'Different' }],
    ['missing column', () => document.querySelector('td').remove()],
    ['missing footer', () => document.body.lastElementChild.remove()],
    ['next page', () => document.body.insertAdjacentHTML('beforeend','<button>Next</button>')],
  ])('does not authorize %s', (_, mutate) => {
    mutate(); expect(result()).toMatchObject({complete:false,phones:[]})
  })
  it('ignores explicitly disabled next button', () => {
    document.body.insertAdjacentHTML('beforeend','<button disabled>Next</button>')
    expect(result().complete).toBe(true)
  })
})
