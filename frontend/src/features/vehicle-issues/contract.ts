import { z } from 'zod'

function validIssueDay(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const parsed = new Date(`${value}T12:00:00Z`)
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}

const id = z.string().uuid()
const instant = z.string().datetime({ offset: true })
export const prioritySchema = z.enum(['urgent', 'soon', 'monitor'])
export const stateSchema = z.enum(['open', 'resolved', 'dismissed'])
export const issueSchema = z.object({
  id, vehicle_id: id, description: z.string().min(1).max(2000), priority: prioritySchema,
  state: stateSchema, version: z.number().int().positive(),
  responsible_user: z.object({ id, display_name: z.string(), active: z.boolean() }).nullable(),
  follow_up_on: z.string().refine(validIssueDay).nullable(),
  follow_up_state: z.enum(['unscheduled', 'upcoming', 'today', 'overdue', 'closed', 'unknown']),
  created_at: instant, updated_at: instant, state_changed_at: instant.nullable(), state_reason: z.string().nullable(),
  current_link: z.object({ id, target_order_id: id.nullable(), order_number: z.string().nullable(), availability: z.enum(['available', 'unavailable']), created_at: instant }).nullable(),
  capabilities: z.object({ can_edit: z.boolean(), can_change_state: z.boolean(), can_link_context: z.boolean(), can_end_link: z.boolean() }),
}).superRefine((issue, context) => {
  if (issue.current_link?.availability === 'available' && (!issue.current_link.target_order_id || !issue.current_link.order_number)) {
    context.addIssue({ code: 'custom', message: 'Available visit identity is missing' })
  }
})
export const pageSchema = z.object({
  items: z.array(issueSchema).max(25), total: z.number().int().nonnegative(), skip: z.number().int().nonnegative(),
  limit: z.literal(25), has_more: z.boolean(), as_of: instant, timezone: z.string().nullable(),
})
export const ownersSchema = z.object({ items: z.array(z.object({ id, display_name: z.string() })) })
export const mutationSchema = z.object({ issue: issueSchema, replayed: z.boolean() })
export type VehicleIssue = z.infer<typeof issueSchema>
export type IssueState = z.infer<typeof stateSchema>
export type IssueDraft = { description: string; priority: VehicleIssue['priority']; owner: string; date: string }
export const emptyDraft = (): IssueDraft => ({ description: '', priority: 'soon', owner: '', date: '' })
export function draftFor(issue: VehicleIssue): IssueDraft {
  return { description: issue.description, priority: issue.priority, owner: issue.responsible_user?.id ?? '', date: issue.follow_up_on ?? '' }
}
export function scopedIssue(value: unknown, vehicleId: string, issueId?: string) {
  const issue = issueSchema.parse(value)
  if (issue.vehicle_id !== vehicleId || (issueId && issue.id !== issueId)) throw new Error('Truck issue context unavailable')
  return issue
}
export function scopedPage(value: unknown, vehicleId: string, skip: number, state: IssueState | 'all') {
  const page = pageSchema.parse(value)
  if (page.skip !== skip || page.items.length > page.total || new Set(page.items.map(item => item.id)).size !== page.items.length
    || page.items.some(item => item.vehicle_id !== vehicleId || (state !== 'all' && item.state !== state))
    || page.has_more !== (skip + page.items.length < page.total)) throw new Error('Truck issues response unavailable')
  return page
}
export function issueFields(draft: IssueDraft, original?: VehicleIssue) {
  const description = draft.description.trim()
  if (!description || description.length > 2000) throw new Error('Enter an issue description (1–2,000 characters).')
  if (draft.date && !validIssueDay(draft.date)) throw new Error('Enter a valid follow-up date (YYYY-MM-DD).')
  return {
    description, priority: draft.priority, follow_up_on: draft.date || null,
    // An inactive former owner remains visible, but is not submitted as a new assignment.
    ...(original?.responsible_user?.id === draft.owner ? {} : { responsible_user_id: draft.owner || null }),
  }
}
export function issueError(error: unknown, fallback: string) {
  const detail = (error as { response?: { data?: { detail?: { message?: unknown } } } })?.response?.data?.detail
  return typeof detail?.message === 'string' ? detail.message : fallback
}
