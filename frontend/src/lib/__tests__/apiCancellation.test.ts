import axios from 'axios'
import { describe, expect, it, vi } from 'vitest'

const refreshMocks = vi.hoisted(() => ({
  requestTokenRefresh: vi.fn(),
}))

vi.mock('../authRefresh', () => ({
  requestTokenRefresh: refreshMocks.requestTokenRefresh,
}))

import api from '../api'

describe('API cancellation', () => {
  it('does not attempt token refresh for an aborted request', async () => {
    const controller = new AbortController()
    const request = api.get('/repair-orders', {
      signal: controller.signal,
      adapter: async () => {
        throw new axios.CanceledError('Request canceled')
      },
    })

    controller.abort()

    await expect(request).rejects.toMatchObject({ code: 'ERR_CANCELED' })
    expect(refreshMocks.requestTokenRefresh).not.toHaveBeenCalled()
  })
})
