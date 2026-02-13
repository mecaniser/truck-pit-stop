export const MISC_WORK_OPTIONS = [
  { value: 'shop_cleanup', label: 'Shop Cleanup' },
  { value: 'parts_runner', label: 'Parts Runner' },
  { value: 'admin_paperwork', label: 'Admin Paperwork' },
  { value: 'training', label: 'Training' },
] as const

const MISC_WORK_LABEL_MAP: Record<string, string> = Object.fromEntries(
  MISC_WORK_OPTIONS.map((option) => [option.value, option.label]),
)

const SESSION_TYPE_LABEL_MAP: Record<string, string> = {
  repair_order: 'Repair Order',
  misc: 'Misc',
}

function humanizeEnum(value: string): string {
  return value
    .split('_')
    .map((chunk) => (chunk ? `${chunk[0].toUpperCase()}${chunk.slice(1)}` : chunk))
    .join(' ')
}

export function formatMiscCategory(value?: string | null): string {
  if (!value) return 'Other'
  return MISC_WORK_LABEL_MAP[value] || humanizeEnum(value)
}

export function formatSessionType(value?: string | null): string {
  if (!value) return 'Unknown'
  return SESSION_TYPE_LABEL_MAP[value] || humanizeEnum(value)
}
