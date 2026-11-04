import { describe, it, expect } from 'vitest'
import type { Invoice } from '@/types'
import { canPayPortalInvoice, portalInvoiceBalance } from '../portal-invoices'
const item=(pending: string|null, balance='268.44')=>({source:'native',payment_summary:{state:'unpaid',balance_due:balance,pending_amount:pending}} as Invoice)
describe('invoice payment availability',()=>{
  it('uses the API null-pending contract as no reservation',()=>expect(canPayPortalInvoice(item(null))).toBe(true))
  it('blocks fully reserved and malformed amounts',()=>{
    for(const pending of ['268.44','300.00','NaN','-1.00']) expect(canPayPortalInvoice(item(pending))).toBe(false)
    expect(portalInvoiceBalance(item(null,'NaN'))).toBeNull()
  })
  it('blocks inactive source collections even when balance is known',()=>expect(canPayPortalInvoice({...item(null),source:'ets_collection_handoff',source_collection:{state:'paused',collection_enabled:false} as never})).toBe(false))
})
