import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { requestTokenRefresh, requestWorkOSSessionRefresh } from '../authRefresh'
import { useAuthStore } from '../../stores/authStore'

describe('session refresh coordination', () => {
  afterEach(() => vi.restoreAllMocks())
  it('shares simultaneous WorkOS renewals and bounds request duration', async () => {
    let resolve!: (value: unknown) => void
    const post = vi.spyOn(axios, 'post').mockImplementation(() => new Promise(r => { resolve = r }))
    const timer = requestWorkOSSessionRefresh()
    const reactive = requestWorkOSSessionRefresh()
    expect(timer).toBe(reactive)
    expect(post).toHaveBeenCalledTimes(1)
    expect(post.mock.calls[0][2]).toMatchObject({ withCredentials: true, timeout: 15_000 })
    resolve({ data: {} })
    await timer
  })
  it('shares legacy token rotation but never shares across session epochs', async () => {
    const post = vi.spyOn(axios, 'post').mockResolvedValue({ data: { access_token: 'a', refresh_token: 'r' } })
    const first = requestTokenRefresh('r0')
    expect(requestTokenRefresh('r0')).toBe(first)
    useAuthStore.setState(s => ({ authSessionEpoch: s.authSessionEpoch + 1 }))
    const next = requestTokenRefresh('new-user-r')
    expect(next).not.toBe(first)
    await Promise.all([first, next])
    expect(post).toHaveBeenCalledTimes(2)
  })
})
