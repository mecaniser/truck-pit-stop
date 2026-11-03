import { describe, expect, it } from 'vitest'
import { readWorkspaceVisit } from './workspaceVisit'

describe('workspace visit', () => {
  const visit = { pathname: '/dashboard/customers', search: '?selected=c1&tab=history', record: 'order-1', scope: 'shop-and-user' }
  it('restores only an internal record destination in the originating staff scope', () => {
    expect(readWorkspaceVisit({ workspaceVisit: visit }, visit.scope)).toEqual(visit)
    expect(readWorkspaceVisit({ workspaceVisit: visit }, 'different-user')).toBeNull()
    for (const invalid of [{ pathname: '//other.test' }, { search: '?tab=history' }, { search: '//other.test' }]) {
      expect(readWorkspaceVisit({ workspaceVisit: { ...visit, ...invalid } }, visit.scope)).toBeNull()
    }
  })
})
