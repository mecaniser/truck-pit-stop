import {afterEach, describe, expect, it, vi} from 'vitest'
import {render, cleanup} from '@testing-library/react'
import PortalMotion from '../PortalMotion'
import {transitionPortal} from '../portal-transition'
import type {MouseEvent} from 'react'

const originalTransition=Object.getOwnPropertyDescriptor(document,'startViewTransition')
const originalAnimate=Object.getOwnPropertyDescriptor(Element.prototype,'animate')
afterEach(()=>{cleanup();transitionPortal({detail:0} as MouseEvent<HTMLAnchorElement>,()=>{});if(originalTransition)Object.defineProperty(document,'startViewTransition',originalTransition);else Reflect.deleteProperty(document,'startViewTransition');if(originalAnimate)Object.defineProperty(Element.prototype,'animate',originalAnimate);else Reflect.deleteProperty(Element.prototype,'animate');document.documentElement.removeAttribute('data-portal-keyboard-navigation');vi.unstubAllGlobals();vi.restoreAllMocks()})

describe('portal motion accessibility and lifecycle',()=>{
 it('keeps keyboard state changes immediate',()=>{
  const update=vi.fn()
  transitionPortal({detail:0} as MouseEvent<HTMLAnchorElement>,update)
  expect(update).toHaveBeenCalledOnce()
 })
 it('keeps reduced-motion state changes immediate',()=>{
  vi.stubGlobal('matchMedia',()=>({matches:true}))
  const update=vi.fn()
  transitionPortal({detail:1} as MouseEvent<HTMLAnchorElement>,update)
  expect(update).toHaveBeenCalledOnce()
 })
 it('renders immediately when view transitions are unsupported',()=>{
  vi.stubGlobal('matchMedia',()=>({matches:false}))
  const update=vi.fn()
  transitionPortal({detail:1} as MouseEvent<HTMLAnchorElement>,update)
  expect(update).toHaveBeenCalledOnce()
 })
 it('staggers actual rows by 30ms and cancels detached animations',()=>{
  vi.stubGlobal('matchMedia',()=>({matches:false,addEventListener:vi.fn(),removeEventListener:vi.fn()}))
  const cancel=vi.fn()
  const animate=vi.fn(()=>({finished:new Promise(()=>{}),cancel}))
  vi.stubGlobal('Animation',class {})
  Object.defineProperty(Element.prototype,'animate',{value:animate,configurable:true})
  const view=render(<PortalMotion><section><div className="space-y-2"><a>One</a><a>Two</a></div></section></PortalMotion>)
  expect(animate.mock.calls.map(call=>(call as unknown as [unknown,{delay:number}])[1].delay)).toEqual([0,30])
  view.unmount()
  expect(cancel).toHaveBeenCalledTimes(2)
  Reflect.deleteProperty(Element.prototype,'animate')
 })
})

function queuedTransitions() {
 vi.stubGlobal('matchMedia',()=>({matches:false}))
 const callbacks:Array<()=>void>=[]
 const skips:Array<ReturnType<typeof vi.fn>>=[]
 Object.defineProperty(document,'startViewTransition',{configurable:true,value:(callback:()=>void)=>{
  callbacks.push(callback)
  const skip=vi.fn();skips.push(skip)
  return {skipTransition:skip,finished:new Promise(()=>{})}
 }})
 const event={detail:1,currentTarget:document.createElement('a')} as MouseEvent<HTMLAnchorElement>
 return {callbacks,skips,event}
}
describe('interrupted portal navigation',()=>{
 it('commits only the latest pointer destination even when old callbacks run later',()=>{
  const {callbacks,skips,event}=queuedTransitions();const old=vi.fn();const latest=vi.fn()
  transitionPortal(event,old);transitionPortal(event,latest)
  callbacks[1]();callbacks[0]()
  expect(old).not.toHaveBeenCalled();expect(latest).toHaveBeenCalledOnce();expect(skips[0]).toHaveBeenCalledOnce()
 })
 it('never lets a pending pointer transition override an immediate keyboard destination',()=>{
  const {callbacks,event}=queuedTransitions();const old=vi.fn();const keyboard=vi.fn()
  transitionPortal(event,old);transitionPortal({detail:0} as MouseEvent<HTMLAnchorElement>,keyboard);callbacks[0]()
  expect(old).not.toHaveBeenCalled();expect(keyboard).toHaveBeenCalledOnce()
 })
})
