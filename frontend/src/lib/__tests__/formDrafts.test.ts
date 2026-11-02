import { beforeEach, describe, expect, it, vi } from 'vitest'
import { captureFormDrafts, clearFormDrafts, draftIdentity, readFormDraft, registerDraftWriter, saveFormDraft } from '../formDrafts'
const user = { id: 'u1', tenant_id: 't1', role: 'garage_owner', customer_id: null, is_active: true }
beforeEach(() => { sessionStorage.clear(); vi.useRealTimers() })
describe('session draft isolation', () => {
  it('captures synchronously for the active identity, never inactive accounts', () => {
    const write = vi.fn()
    const unregister = registerDraftWriter(write)
    captureFormDrafts(user)
    expect(write).toHaveBeenCalledWith(draftIdentity(user))
    captureFormDrafts({ ...user, is_active: false })
    expect(write).toHaveBeenCalledTimes(1)
    unregister()
    captureFormDrafts(user)
    expect(write).toHaveBeenCalledTimes(1)
  })
  it.each([{ id: 'u2' }, { tenant_id: 't2' }, { role: 'mechanic' }, { customer_id: 'c2' }])('rejects changed identity %j', change => {
    saveFormDraft('customer', draftIdentity(user)!, { name: 'Draft' }, true)
    expect(readFormDraft('customer', draftIdentity({ ...user, ...change })!)).toBeNull()
    expect(readFormDraft('customer', draftIdentity(user)!)).toBeNull()
  })
  it('expires after two hours and clears only draft storage on logout', () => {
    vi.useFakeTimers()
    saveFormDraft('customer', draftIdentity(user)!, { name: 'Draft' }, false)
    expect(readFormDraft('customer', draftIdentity(user)!)?.data).toEqual({ name: 'Draft' })
    vi.advanceTimersByTime(2 * 60 * 60 * 1000 + 1)
    expect(readFormDraft('customer', draftIdentity(user)!)).toBeNull()
    sessionStorage.setItem('unrelated', 'keep')
    saveFormDraft('customer', draftIdentity(user)!, {}, false)
    clearFormDrafts()
    expect(sessionStorage.getItem('unrelated')).toBe('keep')
    expect(readFormDraft('customer', draftIdentity(user)!)).toBeNull()
  })
  it('handles corrupt, oversized, and unavailable storage without throwing', () => {
    sessionStorage.setItem('dieselbridge:form-draft:v1:customer', '{')
    expect(readFormDraft('customer', draftIdentity(user)!)).toBeNull()
    expect(saveFormDraft('customer', draftIdentity(user)!, 'x'.repeat(100001), false)).toBe(false)
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Quota') })
    expect(saveFormDraft('customer', draftIdentity(user)!, {}, false)).toBe(false)
    spy.mockRestore()
  })
})
