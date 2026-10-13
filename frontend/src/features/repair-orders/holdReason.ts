const labels: Record<string, string> = {
  waiting_for_parts: 'Waiting for parts',
  waiting_for_customer_approval: 'Waiting for customer approval',
  need_more_info: 'More information needed',
  switched_to_other_ro: 'Technician switched to another order',
  other: 'Other',
}

export function holdReasonLabel(reason: string) {
  return labels[reason] || reason.replace(/_/g, ' ')
}
