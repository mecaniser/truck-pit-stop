type Identity = { tenant_id?: string | null; id: string; role: string }
export const canReadOperationNotes = (role?: string) => ['garage_owner', 'garage_admin', 'receptionist', 'mechanic'].includes(role ?? '')

/** Keep the existing order prefix for invalidation, partition private history by session. */
export function scopedOrderDetailKey(prefix: 'repair-order-detail' | 'fleet-ro-detail', orderId: string | undefined, user: Identity | null | undefined, epoch: number) {
  return [prefix, orderId, user?.tenant_id, user?.id, user?.role, epoch] as const
}
