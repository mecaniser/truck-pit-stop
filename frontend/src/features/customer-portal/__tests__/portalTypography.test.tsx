import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { DEFAULT_PORTAL_TYPOGRAPHY, parsePortalTypography, usePortalTypography } from '../portalTypography'
const auth = vi.hoisted(() => ({ user: { id: 'customer-a', tenant_id: 'shop-a', role: 'customer' } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: () => auth }))
function Readout({ label }: { label: string }) {
  const { typography, update } = usePortalTypography()
  return <div><output aria-label={label}>{typography.font}:{typography.size}</output>
    <button onClick={() => update({font:'jakarta',size:'large'})}>Change {label}</button></div>
}
beforeEach(() => { localStorage.clear(); auth.user={id:'customer-a',tenant_id:'shop-a',role:'customer'} })
it.each([null,'bad','{}','{"font":"unsupported","size":"large"}','{"font":"jakarta","size":"huge"}'])('ignores unsupported browser preferences: %s',raw=>{
  expect(parsePortalTypography(raw)).toEqual(DEFAULT_PORTAL_TYPOGRAPHY)
})
it('updates every portal subscriber and persists without touching staff keys',()=>{
  localStorage.setItem('theme-font-family','inter')
  render(<><Readout label="shell"/><Readout label="settings"/></>)
  fireEvent.click(screen.getByText('Change settings'))
  expect(screen.getByLabelText('shell')).toHaveTextContent('jakarta:large')
  expect(screen.getByLabelText('settings')).toHaveTextContent('jakarta:large')
  expect(localStorage.getItem('dieselbridge:customer-typography:v1:shop-a:customer-a')).toBe('{"font":"jakarta","size":"large"}')
  expect(localStorage.getItem('theme-font-family')).toBe('inter')
})
it('restores preferences after remount and separates customers and shops',()=>{
  const view=render(<Readout label="shell"/>)
  fireEvent.click(screen.getByText('Change shell')); view.unmount()
  const next=render(<Readout label="shell"/>)
  expect(screen.getByLabelText('shell')).toHaveTextContent('jakarta:large')
  auth.user={...auth.user,id:'customer-b'};next.rerender(<Readout label="shell"/>)
  expect(screen.getByLabelText('shell')).toHaveTextContent('geist:default')
  auth.user={...auth.user,id:'customer-a',tenant_id:'shop-b'};next.rerender(<Readout label="shell"/>)
  expect(screen.getByLabelText('shell')).toHaveTextContent('geist:default')
})
it('handles cross-tab storage updates',()=>{
  render(<Readout label="shell"/>)
  act(()=>{localStorage.setItem('dieselbridge:customer-typography:v1:shop-a:customer-a','{"font":"mono","size":"small"}');window.dispatchEvent(new Event('storage'))})
  expect(screen.getByLabelText('shell')).toHaveTextContent('mono:small')
})
it('keeps the previous preference when storage rejects a write',()=>{
  render(<Readout label="shell"/>)
  const write=vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('blocked')})
  fireEvent.click(screen.getByText('Change shell'))
  expect(screen.getByLabelText('shell')).toHaveTextContent('geist:default')
  write.mockRestore()
})
it('does not write customer preferences for a staff principal',()=>{
  auth.user.role='owner'
  render(<Readout label="shell"/>);fireEvent.click(screen.getByText('Change shell'))
  expect(localStorage.length).toBe(0)
  expect(screen.getByLabelText('shell')).toHaveTextContent('geist:default')
})
