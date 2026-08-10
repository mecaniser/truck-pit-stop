import { describe, expect, it, vi } from 'vitest'

vi.mock('../lib/api', () => ({
  default: {
    defaults: { headers: { common: {} } },
    get: vi.fn(),
  },
}))

import { buildWorkOSLoginUrl } from '../lib/workosAuth'

describe('WorkOS manager login URL', () => {
  it('preserves a relative manager return path', () => {
    expect(buildWorkOSLoginUrl('/fleet/trucks/one', 'tenant-1')).toBe(
      '/api/v1/auth/workos/login?return_to=%2Ffleet%2Ftrucks%2Fone&tenant_id=tenant-1'
    )
  })

  it('rejects protocol-relative and external return targets', () => {
    expect(buildWorkOSLoginUrl('//evil.example', 'tenant-1')).toBe(
      '/api/v1/auth/workos/login?return_to=%2F&tenant_id=tenant-1'
    )
    expect(buildWorkOSLoginUrl('https://evil.example', 'tenant-1')).toBe(
      '/api/v1/auth/workos/login?return_to=%2F&tenant_id=tenant-1'
    )
  })
})
