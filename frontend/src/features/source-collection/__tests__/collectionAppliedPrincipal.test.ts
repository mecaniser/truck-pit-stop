import { describe, expect, it } from 'vitest'
import { collectionAppliedPrincipal } from '../collectionAppliedPrincipal'
import type { SourceCollectionSummary } from '../types'

describe('collection principal presentation', () => {
  it.each([
    ['0.00', '0.00', '0.00'], ['20.00', '0.00', '20.00'],
    ['0.00', '40.00', '40.00'], ['20.00', '40.00', '60.00'],
    ['0.10', '0.20', '0.30'], ['9999999999.99', '0.01', '10000000000.00'],
    ['20.00', null, null], ['invalid', '40.00', null], ['20.00', '-1.00', null], ['20.00', '1.234', null],
  ])('combines only known prior %s and native %s principal', (prior, native, expected) => {
    expect(collectionAppliedPrincipal({ source_prior_allocated: prior } as SourceCollectionSummary, native)).toBe(expected)
  })
})
