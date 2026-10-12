import { z } from 'zod'

const count = z.number().int().nonnegative()
const taskSchema = z.object({
  id: z.string().min(1), labor_id: z.string().min(1), service_name: z.string(), label: z.string().min(1),
  required: z.boolean(), position: count, is_completed: z.boolean(), version: z.number().int().positive(),
  completed_at: z.string().nullable(), completed_by: z.object({ id: z.string().min(1), name: z.string() }).nullable(),
})
export const checklistPageSchema = z.object({
  items: z.array(taskSchema), total: count, skip: count, limit: z.number().int().min(1).max(100),
  summary: z.object({ total: count, completed: count, required: count, required_remaining: count }),
  can_update: z.boolean(),
}).refine(page => page.summary.total === page.total && page.summary.completed <= page.total
  && page.summary.required <= page.total && page.summary.required_remaining <= page.summary.required,
'Invalid checklist summary')
export const checklistTemplateSchema = z.object({
  service_id: z.string().min(1), version: count,
  items: z.array(z.object({ id: z.string().min(1), label: z.string().min(1).max(300), required: z.boolean() })).max(50),
})
