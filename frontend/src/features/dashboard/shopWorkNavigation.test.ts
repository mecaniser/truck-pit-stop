import { describe, expect, it } from 'vitest'
import { SHOP_WORK_RETURN_URL, shopWorkDestinationUrl, shopWorkReturnUrl, type ShopWorkDestination } from './shopWorkNavigation'

describe('Shop Work destination contract', () => {
  it.each([
    ['repair_order', 'needs_action', '/dashboard/repair-orders', 'selected', 'queue', 'needs_action'],
    ['inventory', null, '/dashboard/garage/inventory', 'selected', null, null],
    ['purchase_order', 'orders', '/dashboard/garage/purchasing', 'purchase_order', 'view', 'orders'],
    ['purchase_order', 'receiving', '/dashboard/garage/purchasing', 'purchase_order', 'view', 'receiving'],
    ['vendor_return', null, '/dashboard/garage/purchasing', 'return', 'view', 'returns'],
    ['core', null, '/dashboard/garage/purchasing', 'core', 'view', 'returns'],
    ['customer_account', null, '/dashboard/customers', 'selected', 'tab', 'account'],
  ])('opens exact %s record with safe origin', (kind, view, path, idParam, viewParam, expectedView) => {
    const url = new URL(shopWorkDestinationUrl({ kind, view, id: 'record/&?=1' } as ShopWorkDestination), 'https://shop.test')
    expect(url.pathname).toBe(path)
    expect(url.searchParams.get(idParam!)).toBe('record/&?=1')
    if (viewParam) expect(url.searchParams.get(viewParam)).toBe(expectedView)
    expect(shopWorkReturnUrl(url.searchParams)).toBe(SHOP_WORK_RETURN_URL)
  })

  it('accepts only the fixed origin marker and validates queue lanes', () => {
    expect(shopWorkReturnUrl(new URLSearchParams('shop_work=https://evil.test'))).toBeNull()
    expect(shopWorkReturnUrl(new URLSearchParams('return=https://evil.test'))).toBeNull()
    const url = new URL(shopWorkDestinationUrl({ kind: 'repair_order', id: 'one', view: '//evil.test' }), 'https://shop.test')
    expect(url.searchParams.has('queue')).toBe(false)
  })
})
