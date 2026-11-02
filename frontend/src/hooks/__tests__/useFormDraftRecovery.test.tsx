import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { z } from 'zod'
const mocks = vi.hoisted(() => ({ get: vi.fn(), state: { user: { id: 'u1', tenant_id: 't1', role: 'garage_owner', customer_id: null as string | null, is_active: true } } }))
vi.mock('../../lib/api', () => ({ default: { get: mocks.get } }))
vi.mock('../../stores/authStore', () => ({ useAuthStore: Object.assign((selector: (s: typeof mocks.state) => unknown) => selector(mocks.state), { getState: () => mocks.state }) }))
import { useFormDraftRecovery } from '../useFormDraftRecovery'
import { captureFormDrafts, draftIdentity, readFormDraft, saveFormDraft } from '../../lib/formDrafts'
const schema = z.object({ note: z.string() })
const initialUser = { ...mocks.state.user }
beforeEach(() => { sessionStorage.clear(); mocks.state.user = { ...initialUser }; mocks.get.mockResolvedValue({ data: initialUser }) })
afterEach(() => { cleanup(); vi.useRealTimers(); vi.clearAllMocks() })
it('saves latest fields on expiry, preserves uncertainty, and suppresses a confirmed successful draft', () => {
  const { result, rerender } = renderHook(({ active, note }) => useFormDraftRecovery('test', active, { note }, schema), { initialProps: { active: true, note: 'first' } })
  rerender({ active: true, note: 'latest' })
  act(() => result.current.markSubmitting())
  captureFormDrafts(initialUser)
  expect(readFormDraft('test', draftIdentity(initialUser)!)).toMatchObject({ data: { note: 'latest' }, uncertain: true })
  act(() => result.current.clear())
  captureFormDrafts(initialUser)
  expect(readFormDraft('test', draftIdentity(initialUser)!)).toBeNull()
  rerender({ active: false, note: '' })
  rerender({ active: true, note: 'new form' })
  captureFormDrafts(initialUser)
  expect(readFormDraft('test', draftIdentity(initialUser)!)?.data).toEqual({ note: 'new form' })
})
it('never relabels an open form when the signed-in tenant changes', () => {
  const { rerender } = renderHook(() => useFormDraftRecovery('test', true, { note: 'tenant one' }, schema))
  mocks.state.user = { ...initialUser, tenant_id: 't2' }
  rerender()
  captureFormDrafts(mocks.state.user)
  expect(readFormDraft('test', draftIdentity(mocks.state.user)!)).toBeNull()
})
it('requires server identity before offering recovery and checks identity again at restore', async () => {
  saveFormDraft('test', draftIdentity(initialUser)!, { note: 'private' }, false)
  const { result, rerender } = renderHook(() => useFormDraftRecovery('test', false, { note: '' }, schema))
  expect(result.current.candidate).toBeNull()
  await waitFor(() => expect(result.current.candidate?.data.note).toBe('private'))
  expect(result.current.restoreData()).toEqual({ note: 'private' })
  mocks.state.user = { ...initialUser, id: 'u2' }
  expect(() => result.current.restoreData()).toThrow('Session changed')
  rerender()
  expect(result.current.candidate).toBeNull()
})
it('rejects a candidate that expires while the page is open', async () => {
  saveFormDraft('test', draftIdentity(initialUser)!, { note: 'old' }, false)
  const { result } = renderHook(() => useFormDraftRecovery('test', false, { note: '' }, schema))
  await waitFor(() => expect(result.current.candidate).not.toBeNull())
  vi.useFakeTimers(); vi.setSystemTime(Date.now() + 2 * 60 * 60 * 1000 + 1)
  expect(() => result.current.restoreData()).toThrow('Draft expired')
})
it('does not offer drafts when server identity differs or schema is invalid', async () => {
  saveFormDraft('test', draftIdentity(initialUser)!, { note: 'private' }, false)
  mocks.get.mockResolvedValue({ data: { ...initialUser, tenant_id: 'other' } })
  const { result } = renderHook(() => useFormDraftRecovery('test', false, { note: '' }, schema))
  await act(async () => { await Promise.resolve() })
  expect(result.current.candidate).toBeNull()
})
it('does not resurrect a discarded draft after delayed identity verification', async () => {
  saveFormDraft('test', draftIdentity(initialUser)!, { note: 'discard me' }, false)
  let resolve!: (value: unknown) => void
  mocks.get.mockReturnValue(new Promise(r => { resolve = r }))
  const { result } = renderHook(() => useFormDraftRecovery('test', false, { note: '' }, schema))
  act(() => result.current.clear())
  await act(async () => resolve({ data: initialUser }))
  expect(result.current.candidate).toBeNull()
})
it('does not replace a newer open form with a recovered draft', async () => {
  saveFormDraft('test', draftIdentity(initialUser)!, { note: 'old' }, false)
  const { result, rerender } = renderHook(({ active }) => useFormDraftRecovery('test', active, { note: 'new' }, schema), { initialProps: { active: false } })
  await waitFor(() => expect(result.current.candidate).not.toBeNull())
  rerender({ active: true })
  expect(() => result.current.restoreData()).toThrow('A newer form is open')
})
