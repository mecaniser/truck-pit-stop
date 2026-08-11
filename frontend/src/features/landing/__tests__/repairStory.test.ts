import { describe, expect, it } from 'vitest'

import {
  CUSTOMERS,
  INITIAL_LOCAL_STATE,
  INVOICES,
  MODULES,
  REPAIR_STORY,
  SHOP_ORDERS,
  VEHICLES,
  getContextSheet,
  getEventSheet,
} from '../repairStory'

describe('source-grounded landing preview fixtures', () => {
  it('keeps the canonical repair story arithmetic, references, and chronology consistent', () => {
    const story = REPAIR_STORY
    const subtotal = story.money.laborCents + story.money.partsCents + story.money.shopSuppliesCents

    expect(subtotal).toBe(story.money.taxableSubtotalCents)
    expect(Math.round(story.money.taxableSubtotalCents * story.money.taxRate)).toBe(story.money.taxCents)
    expect(story.money.taxableSubtotalCents + story.money.taxCents).toBe(story.money.totalCents)
    expect(story.invoice.totalCents).toBe(story.money.totalCents)
    expect(story.payment.paidCents).toBe(story.money.totalCents)
    expect(story.payment.balanceCents).toBe(0)
    expect(story.invoice.number.replace('INV', 'RO')).toBe(story.repairOrder.number)
    expect(story.vehicle.maskedVin).toMatch(/^…\d{4}$/)

    const chronology = [
      story.repairOrder.received.iso,
      story.repairOrder.estimatePrepared.iso,
      story.repairOrder.approvalRecorded.iso,
      story.shopWork.completed.iso,
      story.invoice.created.iso,
      story.payment.recorded.iso,
    ].map(Date.parse)
    expect(chronology).toEqual([...chronology].sort((left, right) => left - right))
    expect(new Set(chronology).size).toBe(chronology.length)
  })

  it('uses the exact product rail and authentic invoice states', () => {
    expect(MODULES.map(({ id, label }) => ({ id, label }))).toEqual([
      { id: 'repair-orders', label: 'Repair Orders' },
      { id: 'customers', label: 'Customers' },
      { id: 'shop-work', label: 'Shop Work' },
      { id: 'invoices', label: 'Invoices' },
      { id: 'vehicle-history', label: 'Vehicle History' },
    ])
    expect(INVOICES.map((invoice) => invoice.state)).toEqual([
      'Paid',
      'Pending Zelle confirmation',
      'Awaiting payment',
    ])
  })

  it('deep-freezes every normalized preview fixture', () => {
    const roots = [REPAIR_STORY, MODULES, CUSTOMERS, SHOP_ORDERS, INVOICES, VEHICLES, INITIAL_LOCAL_STATE]
    roots.forEach((root) => expect(Object.isFrozen(root)).toBe(true))
    expect(Object.isFrozen(REPAIR_STORY.money)).toBe(true)
    expect(Object.isFrozen(CUSTOMERS[0].history)).toBe(true)
    expect(Object.isFrozen(CUSTOMERS[0].history[0])).toBe(true)
    expect(Object.isFrozen(VEHICLES[0].repairs)).toBe(true)
    expect(Object.isFrozen(INITIAL_LOCAL_STATE.repairOrders)).toBe(true)
  })

  it('derives non-empty context and authentic-selection evidence for every module', () => {
    MODULES.forEach((module) => {
      const context = getContextSheet(module.id)
      const evidence = getEventSheet(module.id, INITIAL_LOCAL_STATE)
      expect(context.title).not.toHaveLength(0)
      expect(context.summary).not.toHaveLength(0)
      expect(context.facts.length).toBeGreaterThan(0)
      expect(evidence?.title).not.toHaveLength(0)
      expect(evidence?.facts.length).toBeGreaterThan(0)
    })
  })
})
