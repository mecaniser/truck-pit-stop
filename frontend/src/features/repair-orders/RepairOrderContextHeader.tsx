import { ArrowLeft, History } from 'lucide-react'
import { REPAIR_ORDERS_QUEUE_LABEL, type RepairOrdersQueueOrigin } from './repairOrdersPresentation'

export default function RepairOrderContextHeader({
  orderNumber,
  status,
  customer,
  vehicle,
  description,
  laborTotal,
  partsTotal,
  quoteState,
  invoiceState,
  queueOrigin,
  onReturnToShopWork,
  onRequestHistory,
}: {
  orderNumber: string
  status: string
  customer: string
  vehicle: string
  description: string
  laborTotal: string
  partsTotal: string
  quoteState: string
  invoiceState: string
  queueOrigin: RepairOrdersQueueOrigin | null
  onReturnToShopWork: () => void
  onRequestHistory: () => void
}) {
  return (
    <section className="db-repair-order-context" aria-labelledby="repair-order-context-title">
      <header>
        <div>
          <span>Selected repair order</span>
          <h2 id="repair-order-context-title">{orderNumber}</h2>
        </div>
        <strong>{status}</strong>
      </header>
      <div className="db-repair-order-context__strip">
        <div>
          <span>Customer / vehicle</span>
          <strong>{customer}</strong>
          <small>{vehicle}</small>
        </div>
        <div>
          <span>Work · labor / parts</span>
          <strong>{description}</strong>
          <small>Labor {laborTotal} · Parts {partsTotal}</small>
        </div>
        <div>
          <span>Authorization / history</span>
          <strong>{quoteState}</strong>
          <button type="button" onClick={onRequestHistory}><History aria-hidden="true" /> Load order history</button>
        </div>
        <div>
          <span>Invoice / payment</span>
          <strong>{invoiceState}</strong>
          <small>Financial controls remain in this repair order.</small>
        </div>
      </div>
      {queueOrigin && (
        <button type="button" className="db-repair-order-context__return" onClick={onReturnToShopWork}>
          <ArrowLeft aria-hidden="true" /> Return to {REPAIR_ORDERS_QUEUE_LABEL[queueOrigin]}
        </button>
      )}
    </section>
  )
}
