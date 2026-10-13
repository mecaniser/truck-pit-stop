export interface TemplateTaskDraft { id?: string; label: string; required: boolean }
export interface ServiceChecklistTemplate { service_id: string; version: number; items: (TemplateTaskDraft & { id: string })[] }
export interface ChecklistSummary { total: number; completed: number; required: number; required_remaining: number }
export interface OrderChecklistItem {
  can_update?: boolean; id: string; labor_id: string; service_name: string; label: string; required: boolean; position: number
  is_completed: boolean; completed_at: string | null; completed_by: { id: string; name: string } | null; version: number
}
export interface OrderChecklistPage { items: OrderChecklistItem[]; total: number; skip: number; limit: number; summary: ChecklistSummary; can_update: boolean }
export interface ChecklistUpdate extends OrderChecklistItem { summary: ChecklistSummary; can_update: boolean }
