export type ShopWorkDestination = {
  kind: 'repair_order' | 'inventory' | 'purchase_order' | 'vendor_return' | 'core' | 'customer_account'
  id: string
  view: string | null
}

export const SHOP_WORK_RETURN_URL = '/dashboard?work_view=overview'

/** Read-cache identity for canonical Shop Work destinations. Prefixes stay intact
 * so their incumbent mutation invalidations still refresh the scoped reads. */
export function shopWorkQueryScope(user: { id?: string; tenant_id?: string | null; role?: string; is_active?: boolean; permissions?: { payments?: boolean } | null } | null | undefined, epoch: number | undefined): string {
  return JSON.stringify(['shop-work', user?.tenant_id, user?.id, user?.role, user?.permissions?.payments === true, user?.is_active, epoch])
}

/** A fixed marker, never a caller-supplied URL, carries the Overview origin. */
export function shopWorkBoardUrl(task: string | null): string {
  if (!task || !/^(attention|upcoming):[a-z_]+:[a-zA-Z0-9_-]{1,128}$/.test(task)) return SHOP_WORK_RETURN_URL
  return `${SHOP_WORK_RETURN_URL}&task=${encodeURIComponent(task)}`
}

export function shopWorkReturnUrl(params: URLSearchParams): string | null {
  return params.get('shop_work') === 'overview' ? shopWorkBoardUrl(params.get('task')) : null
}

export function shopWorkDestinationUrl(destination: ShopWorkDestination, task?: string): string {
  const params = new URLSearchParams({ shop_work: 'overview' })
  if (task) params.set('task', task)
  let path: string
  switch (destination.kind) {
    case 'repair_order':
      path = '/dashboard/repair-orders'
      params.set('selected', destination.id)
      if (['needs_action', 'on_floor', 'ready_to_close'].includes(destination.view || '')) params.set('queue', destination.view!)
      break
    case 'inventory':
      path = '/dashboard/garage/inventory'
      params.set('selected', destination.id)
      break
    case 'purchase_order':
      path = '/dashboard/garage/purchasing'
      params.set('view', destination.view === 'receiving' ? 'receiving' : 'orders')
      params.set('purchase_order', destination.id)
      break
    case 'vendor_return':
    case 'core':
      path = '/dashboard/garage/purchasing'
      params.set('view', 'returns')
      params.set(destination.kind === 'core' ? 'core' : 'return', destination.id)
      break
    case 'customer_account':
      path = '/dashboard/customers'
      params.set('selected', destination.id)
      params.set('tab', 'account')
      break
  }
  return `${path}?${params}`
}
