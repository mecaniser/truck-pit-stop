import { centsToMoney, moneyToCents } from '@/features/payments/money'
import type { SourceCollectionSummary } from './types'

export function collectionAppliedPrincipal(summary: SourceCollectionSummary, nativeApplied: string | null | undefined): string | null {
  const prior = moneyToCents(summary.source_prior_allocated)
  const native = moneyToCents(nativeApplied)
  return prior === null || native === null ? null : centsToMoney(prior + native)
}
