import api from '@/lib/api'
import type { EtsReceiptTask, SourceCollectionPreview, SourceCollectionSummary } from './types'

const base = '/source-debt-handoffs'
export async function fetchSourceCollection(id: string) {
  return (await api.get<SourceCollectionSummary>(`${base}/${id}`)).data
}
export async function previewSourceCollection(sourceInvoiceId: string, customerId: string) {
  return (await api.post<SourceCollectionPreview>(`${base}/preview`, { source_invoice_id: sourceInvoiceId, target_customer_id: customerId })).data
}
export async function prepareSourceCollection(preview: SourceCollectionPreview, key: string) {
  const proposal = preview.proposal
  if (preview.eligibility !== 'ready' || !proposal) throw new Error('Refresh the source invoice before preparing collection.')
  return (await api.post<SourceCollectionSummary>(base, {
    source_invoice_id: proposal.source_invoice_id,
    target_customer_id: proposal.target_customer_id,
    expected_source_capture_sha256: proposal.source_capture_sha256,
    expected_source_revision: proposal.source_revision,
    acknowledge_dbn_primary: true,
  }, { headers: { 'Idempotency-Key': key } })).data
}
export async function activateSourceCollection(handoff: SourceCollectionSummary, preview: SourceCollectionPreview, key: string) {
  if (!preview.proposal) throw new Error('Refresh the source invoice before activating collection.')
  return (await api.post<{ handoff: SourceCollectionSummary; native_invoice_id: string; already_active: boolean }>(`${base}/${handoff.id}/activate`, {
    expected_version: handoff.version,
    expected_source_capture_sha256: preview.proposal.source_capture_sha256,
    expected_source_revision: preview.proposal.source_revision,
  }, { headers: { 'Idempotency-Key': key } })).data
}

export async function fetchEtsReceiptTasks(handoffId: string, skip = 0) {
  return (await api.get<{ items: EtsReceiptTask[]; total: number; skip: number; limit: number }>(`${base}/ets-update-tasks`, { params: { handoff_id: handoffId, skip, limit: 20 } })).data
}
export async function claimEtsReceiptTask(task: EtsReceiptTask, key: string) {
  return (await api.post<EtsReceiptTask>(`${base}/ets-update-tasks/${task.id}/claim`, { expected_version: task.version }, { headers: { 'Idempotency-Key': key } })).data
}
export async function acknowledgeEtsReceiptTask(task: EtsReceiptTask, handoff: SourceCollectionSummary, allocationIds: string[], key: string) {
  return (await api.post<EtsReceiptTask>(`${base}/ets-update-tasks/${task.id}/acknowledge`, {
    expected_version: task.version,
    expected_source_revision: handoff.source_revision,
    source_capture_sha256: handoff.source_capture_sha256,
    source_allocation_ids: allocationIds,
  }, { headers: { 'Idempotency-Key': key } })).data
}
export async function reconcileSourceCollection(handoff: SourceCollectionSummary, key: string) {
  return (await api.post<{ handoff: SourceCollectionSummary; conflict: boolean }>(`${base}/${handoff.id}/reconcile`, {
    expected_version: handoff.version,
    expected_source_revision: handoff.source_revision,
    source_capture_sha256: handoff.source_capture_sha256,
  }, { headers: { 'Idempotency-Key': key } })).data
}
