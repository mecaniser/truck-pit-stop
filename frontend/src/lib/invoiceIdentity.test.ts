import { describe,it,expect } from 'vitest'
import {customerInvoiceNumber,customerInvoiceLabel} from './invoiceIdentity'
import type {SourceCollectionSummary} from '@/features/source-collection/types'
describe('customer invoice identity',()=>{
 it('uses the returned tenant reference rather than the internal key',()=>{
  for(const prefix of ['TPS','DEL']){
   const invoice={invoice_number:'DBN-COL-internal',source:'ets_collection_handoff',source_collection:{display_invoice_number:`${prefix}-1687`} as SourceCollectionSummary}
   expect(customerInvoiceNumber(invoice)).toBe(`${prefix}-1687`)
   expect(customerInvoiceLabel(invoice)).toBe(`Invoice ${prefix}-1687`)
  }
 })
 it('fails closed while older collection responses have no display identity',()=>{
  expect(customerInvoiceLabel({invoice_number:'DBN-COL-uuid',source:'ets_collection_handoff'})).toBe('Invoice')
 })
 it('preserves an ordinary tenant invoice number',()=>{
  expect(customerInvoiceNumber({invoice_number:'TPS-828ACD84-000018',source:'native'})).toBe('TPS-828ACD84-000018')
 })
})
