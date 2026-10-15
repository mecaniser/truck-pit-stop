import { z } from 'zod'

export const MAX_RECEIPT_BYTES = 5 * 1024 * 1024
export const RECEIPT_ACCEPT = '.pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png'
const timestamp = z.string().datetime({ offset: true })
const uuid = z.string().uuid()
export const receiptSchema = z.object({
  id: uuid, record_id: uuid, vehicle_id: uuid, uploaded_vehicle_id: uuid,
  filename: z.string().min(1).max(180), media_type: z.enum(['application/pdf', 'image/jpeg', 'image/png']),
  size_bytes: z.number().int().min(1).max(MAX_RECEIPT_BYTES), version: z.number().int().positive(),
  removed_at: timestamp.nullable(), created_at: timestamp, updated_at: timestamp,
  created_by_user_id: uuid.nullable(), created_by_name: z.string().nullable(),
  updated_by_user_id: uuid.nullable(), updated_by_name: z.string().nullable(),
})
export type Receipt = z.infer<typeof receiptSchema>
export const receiptListSchema = z.object({
  items: z.array(receiptSchema).max(10), total: z.number().int().min(0).max(10),
  retained_count: z.number().int().min(0).max(10), retained_bytes: z.number().int().min(0).max(MAX_RECEIPT_BYTES * 10),
  max_files: z.literal(10), max_file_bytes: z.literal(MAX_RECEIPT_BYTES), max_total_bytes: z.literal(MAX_RECEIPT_BYTES * 10),
  record_version: z.number().int().positive(), record_voided_at: timestamp.nullable(),
}).refine(value => value.total === value.items.length && value.retained_count >= value.total
  && new Set(value.items.map(item => item.id)).size === value.items.length
  && value.retained_bytes >= value.items.reduce((total, item) => total + item.size_bytes, 0), 'Invalid receipt totals')
export type ReceiptList = z.infer<typeof receiptListSchema>
export const receiptResultSchema = z.object({ receipt: receiptSchema, replayed: z.boolean(), record_version: z.number().int().positive(), record_voided_at: timestamp.nullable() })
export const receiptHistorySchema = z.object({
  items: z.array(z.object({
    id: uuid, receipt_id: uuid, record_id: uuid, version: z.number().int().positive(), action: z.enum(['upload', 'remove', 'restore']),
    actor_user_id: uuid.nullable(), actor_name: z.string().nullable(), created_at: timestamp, reason: z.string().nullable(), snapshot: receiptSchema,
  })), total: z.number().int().nonnegative(), has_more: z.boolean(),
})

export function validateReceiptTarget(receipt: Receipt, vehicleId: string, recordId: string, receiptId?: string) {
  if (receipt.vehicle_id !== vehicleId || receipt.record_id !== recordId || (receiptId && receipt.id !== receiptId)) throw new Error('Invalid receipt response')
}

export function receiptFileError(file: File): string | null {
  if (!file.size) return 'Choose a receipt file that is not empty.'
  if (file.size > MAX_RECEIPT_BYTES) return 'Use a file up to 5 MiB.'
  if (file.type ? !['application/pdf', 'image/jpeg', 'image/png'].includes(file.type) : !/\.(pdf|jpe?g|png)$/i.test(file.name)) return 'Use a PDF, JPEG or PNG receipt.'
  try {
    if (encodeURIComponent(file.name).length > 2048) return 'Shorten the receipt filename before uploading.'
  } catch { return 'Rename this receipt file before uploading.' }
  return null
}

export function receiptError(error: unknown, fallback: string): { message: string; code: string } {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return { message: detail, code: '' }
  const parsed = z.object({ code: z.string(), message: z.string() }).safeParse(detail)
  return parsed.success ? parsed.data : { message: fallback, code: '' }
}

export async function downloadError(error: unknown): Promise<string> {
  const data = (error as { response?: { data?: unknown } })?.response?.data
  if (data instanceof Blob && data.size <= 64 * 1024) {
    try { return receiptError({ response: { data: JSON.parse(await data.text()) } }, 'Could not download this receipt. Try again.').message } catch { /* Never download an error body. */ }
  }
  return receiptError(error, 'Could not download this receipt. Try again.').message
}

export const receiptSize = (bytes: number) => bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KiB` : `${(bytes / (1024 * 1024)).toFixed(1)} MiB`
