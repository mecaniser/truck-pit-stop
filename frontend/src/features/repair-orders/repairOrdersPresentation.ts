export type RepairOrdersQueueOrigin = 'needs_action' | 'on_floor' | 'ready_to_close'

export const REPAIR_ORDERS_QUEUE_LABEL: Record<RepairOrdersQueueOrigin, string> = {
  needs_action: 'Needs Action',
  on_floor: 'On the Floor',
  ready_to_close: 'Ready to Close',
}
