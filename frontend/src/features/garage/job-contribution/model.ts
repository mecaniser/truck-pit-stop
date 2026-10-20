import type { CostSegment } from './types'
export const costMoney = (value: string | null | undefined) => value == null ? 'Unavailable' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(value))
export const hours = (seconds: number) => `${(seconds / 3600).toFixed(2)} h`
export const reasonLabel = (code: string) => code.replace(/_/g, ' ')
export function validateSchedule(segments: CostSegment[], reason: string, activation: string): string | null {
  if (!reason.trim() || reason.trim().length > 500) return 'Enter a reason (1–500 characters).'
  if (!segments.length || segments.length > 100) return 'Add between 1 and 100 rate segments.'
  for (let i = 0; i < segments.length; i++) {
    const segment = segments[i]
    if (!/^\d{1,5}(\.\d{1,4})?$/.test(segment.hourly_cost) || Number(segment.hourly_cost) < 0.0001 || Number(segment.hourly_cost) > 10000) return 'Hourly cost must be $0.0001–$10,000, with up to four decimals.'
    if (!segment.inclusions.trim() || segment.inclusions.trim().length > 500) return 'Describe included direct employment costs (1–500 characters).'
    const utc = (v: string) => /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/.test(v) && Number.isFinite(Date.parse(v))
    if (!utc(segment.effective_from) || Date.parse(segment.effective_from) < Date.parse(activation)) return 'Start must be on or after shop activation.'
    if (segment.effective_to !== null && (!utc(segment.effective_to) || Date.parse(segment.effective_to) <= Date.parse(segment.effective_from))) return 'End must be after start, or blank for open-ended.'
    if (i > 0 && (segments[i - 1].effective_to === null || Date.parse(segments[i - 1].effective_to!) > Date.parse(segment.effective_from))) return 'Rate segments must be sorted and must not overlap.'
  }
  return null
}
