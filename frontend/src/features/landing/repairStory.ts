export type ModuleId = 'repair-orders' | 'customers' | 'shop-work' | 'invoices' | 'vehicle-history'
export type InputMode = 'pointer' | 'keyboard' | 'programmatic'
export type RepairEvidenceId = 'invoice' | 'history' | 'work-def' | 'work-diagnostic'
export type CustomerDetailTab = 'overview' | 'history'
export type ShopWorkTab = 'queue' | 'activity'

export interface PreviewState {
  activeModule: ModuleId
  inputMode: InputMode
  transitionEpoch: number
}

export interface PreviewLocalState {
  repairOrders: {
    selectedEvidence: RepairEvidenceId
    invoiceExpanded: boolean
    historyExpanded: boolean
  }
  customers: {
    selectedCustomerId: string
    detailTab: CustomerDetailTab
  }
  shopWork: {
    activeTab: ShopWorkTab
    selectedOrderId: string
  }
  invoices: {
    selectedInvoiceId: string
    expandedInvoiceId: string | null
  }
  vehicleHistory: {
    selectedVehicleId: string
    expandedRepairId: string | null
  }
}

interface StoryMoment {
  iso: string
  display: string
  short: string
}

interface MoneyBreakdown {
  laborCents: number
  partsCents: number
  shopSuppliesCents: number
  taxableSubtotalCents: number
  taxRate: number
  taxCents: number
  totalCents: number
}

export interface RepairStory {
  repairOrder: {
    number: string
    state: 'Paid'
    lifecycle: 'Closed'
    concern: string
    received: StoryMoment
    estimatePrepared: StoryMoment
    approvalRecorded: StoryMoment
  }
  customer: {
    id: string
    company: string
    authorizationContact: string
    approvalChannel: string
    phone: string
    vehicleCount: number
  }
  vehicle: {
    id: string
    year: number
    make: string
    model: string
    unit: string
    maskedVin: string
    meterMiles: number
    owner: string
  }
  shopWork: {
    bay: string
    leadTechnician: string
    keyOperation: string
    completed: StoryMoment
  }
  money: MoneyBreakdown
  invoice: {
    id: string
    number: string
    created: StoryMoment
    totalCents: number
    state: 'Paid'
  }
  payment: {
    method: string
    recorded: StoryMoment
    paidCents: number
    balanceCents: number
  }
}

export interface CustomerFixture {
  id: string
  company: string
  contact: string
  email: string
  phone: string
  dotMc: string
  vehicleCount: number
  balanceCents: number
  history: ReadonlyArray<{ id: string; label: string; at: string; amountCents: number }>
}

export interface ShopOrderFixture {
  id: string
  orderNumber: string
  customer: string
  vehicle: string
  summary: string
  lane: 'Needs Action' | 'On the Floor' | 'Ready to Close'
  status: string
  technician: string
  totalCents: number
  activity: string
}

export interface InvoiceFixture {
  id: string
  number: string
  customer: string
  orderNumber: string
  state: 'Paid' | 'Pending Zelle confirmation' | 'Awaiting payment'
  created: string
  totalCents: number
  balanceCents: number
}

export interface VehicleFixture {
  id: string
  unit: string
  label: string
  owner: string
  maskedVin: string
  meterMiles: number
  repairs: ReadonlyArray<{
    id: string
    orderNumber: string
    title: string
    date: string
    status: string
    amountCents: number
  }>
}

export interface SheetModel {
  eyebrow: string
  title: string
  summary: string
  status: string
  tone: 'neutral' | 'success' | 'document' | 'warm'
  facts: ReadonlyArray<{ label: string; value: string }>
}

function deepFreeze<T>(value: T): T {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.values(value as Record<string, unknown>).forEach((nested) => deepFreeze(nested))
    Object.freeze(value)
  }
  return value
}

const moment = (iso: string, display: string, short: string): StoryMoment => ({ iso, display, short })

export const REPAIR_STORY = deepFreeze({
  repairOrder: {
    number: 'RO-2025-0417',
    state: 'Paid',
    lifecycle: 'Closed',
    concern: 'Loss of power under load',
    received: moment('2025-05-14T08:52:00', 'May 14, 2025 · 8:52 AM', '8:52 AM'),
    estimatePrepared: moment('2025-05-14T09:31:00', 'May 14, 2025 · 9:31 AM', '9:31 AM'),
    approvalRecorded: moment('2025-05-14T09:47:00', 'May 14, 2025 · 9:47 AM', '9:47 AM'),
  },
  customer: {
    id: 'customer-northstar',
    company: 'NorthStar Logistics',
    authorizationContact: 'Sarah Johnson',
    approvalChannel: 'dispatch@northstar.example',
    phone: '(704) 555-0147',
    vehicleCount: 12,
  },
  vehicle: {
    id: 'vehicle-nsl-1047',
    year: 2021,
    make: 'Freightliner',
    model: 'Cascadia 126',
    unit: 'NSL-1047',
    maskedVin: '…1234',
    meterMiles: 412_358,
    owner: 'NorthStar Logistics',
  },
  shopWork: {
    bay: 'Bay 3',
    leadTechnician: 'M. Reyes',
    keyOperation: 'Replace DEF dosing unit',
    completed: moment('2025-05-14T10:08:00', 'May 14, 2025 · 10:08 AM', '10:08 AM'),
  },
  money: {
    laborCents: 125_000,
    partsCents: 287_542,
    shopSuppliesCents: 8_500,
    taxableSubtotalCents: 421_042,
    taxRate: 0.0675,
    taxCents: 28_420,
    totalCents: 449_462,
  },
  invoice: {
    id: 'invoice-0417',
    number: 'INV-2025-0417',
    created: moment('2025-05-14T10:15:00', 'May 14, 2025 · 10:15 AM', '10:15 AM'),
    totalCents: 449_462,
    state: 'Paid',
  },
  payment: {
    method: 'ACH •••• 5521',
    recorded: moment('2025-05-14T10:32:00', 'May 14, 2025 · 10:32 AM', '10:32 AM'),
    paidCents: 449_462,
    balanceCents: 0,
  },
} as const satisfies RepairStory)

export const MODULES = deepFreeze([
  { id: 'repair-orders', label: 'Repair Orders' },
  { id: 'customers', label: 'Customers' },
  { id: 'shop-work', label: 'Shop Work' },
  { id: 'invoices', label: 'Invoices' },
  { id: 'vehicle-history', label: 'Vehicle History' },
] as const satisfies ReadonlyArray<{ id: ModuleId; label: string }>)

export const CUSTOMERS = deepFreeze([
  {
    id: REPAIR_STORY.customer.id,
    company: REPAIR_STORY.customer.company,
    contact: REPAIR_STORY.customer.authorizationContact,
    email: REPAIR_STORY.customer.approvalChannel,
    phone: REPAIR_STORY.customer.phone,
    dotMc: 'DOT 2846117 · MC 912408',
    vehicleCount: REPAIR_STORY.customer.vehicleCount,
    balanceCents: REPAIR_STORY.payment.balanceCents,
    history: [
      { id: 'customer-event-payment', label: `Payment recorded · ${REPAIR_STORY.invoice.number}`, at: REPAIR_STORY.payment.recorded.display, amountCents: REPAIR_STORY.payment.paidCents },
      { id: 'customer-event-approval', label: `Estimate approved · ${REPAIR_STORY.repairOrder.number}`, at: REPAIR_STORY.repairOrder.approvalRecorded.display, amountCents: REPAIR_STORY.money.totalCents },
    ],
  },
  {
    id: 'customer-riverbend',
    company: 'Riverbend Freight',
    contact: 'Jordan Lee',
    email: 'dispatch@riverbend.example',
    phone: '(980) 555-0188',
    dotMc: 'DOT 3521104',
    vehicleCount: 7,
    balanceCents: 187_500,
    history: [{ id: 'rb-event', label: 'Invoice awaiting payment · INV-2025-0412', at: 'May 13, 2025 · 4:22 PM', amountCents: 187_500 }],
  },
] as const satisfies ReadonlyArray<CustomerFixture>)

export const SHOP_ORDERS = deepFreeze([
  {
    id: 'shop-order-needs-action', orderNumber: 'RO-2025-0421', customer: 'Riverbend Freight', vehicle: 'Unit RBF-22',
    summary: 'Estimate awaiting customer authorization', lane: 'Needs Action', status: 'Waiting approval', technician: 'Unassigned', totalCents: 187_500,
    activity: 'Estimate sent at 10:21 AM',
  },
  {
    id: 'shop-order-on-floor', orderNumber: REPAIR_STORY.repairOrder.number, customer: REPAIR_STORY.customer.company, vehicle: `Unit ${REPAIR_STORY.vehicle.unit}`,
    summary: REPAIR_STORY.shopWork.keyOperation, lane: 'On the Floor', status: 'In progress', technician: REPAIR_STORY.shopWork.leadTechnician, totalCents: REPAIR_STORY.money.totalCents,
    activity: `${REPAIR_STORY.shopWork.bay} · work completed ${REPAIR_STORY.shopWork.completed.short}`,
  },
  {
    id: 'shop-order-ready', orderNumber: 'RO-2025-0419', customer: 'Atlas Produce', vehicle: 'Unit ATL-08',
    summary: 'Annual inspection and brake adjustment', lane: 'Ready to Close', status: 'Invoice customer', technician: 'D. Patel', totalCents: 92_800,
    activity: 'Quality check completed at 10:04 AM',
  },
] as const satisfies ReadonlyArray<ShopOrderFixture>)

export const INVOICES = deepFreeze([
  {
    id: REPAIR_STORY.invoice.id, number: REPAIR_STORY.invoice.number, customer: REPAIR_STORY.customer.company,
    orderNumber: REPAIR_STORY.repairOrder.number, state: 'Paid', created: REPAIR_STORY.invoice.created.display,
    totalCents: REPAIR_STORY.invoice.totalCents, balanceCents: REPAIR_STORY.payment.balanceCents,
  },
  {
    id: 'invoice-zelle', number: 'INV-2025-0419', customer: 'Atlas Produce', orderNumber: 'RO-2025-0419',
    state: 'Pending Zelle confirmation', created: 'May 14, 2025 · 10:04 AM', totalCents: 92_800, balanceCents: 92_800,
  },
  {
    id: 'invoice-awaiting', number: 'INV-2025-0412', customer: 'Riverbend Freight', orderNumber: 'RO-2025-0412',
    state: 'Awaiting payment', created: 'May 13, 2025 · 4:22 PM', totalCents: 187_500, balanceCents: 187_500,
  },
] as const satisfies ReadonlyArray<InvoiceFixture>)

export const VEHICLES = deepFreeze([
  {
    id: REPAIR_STORY.vehicle.id,
    unit: REPAIR_STORY.vehicle.unit,
    label: `${REPAIR_STORY.vehicle.year} ${REPAIR_STORY.vehicle.make} ${REPAIR_STORY.vehicle.model}`,
    owner: REPAIR_STORY.vehicle.owner,
    maskedVin: REPAIR_STORY.vehicle.maskedVin,
    meterMiles: REPAIR_STORY.vehicle.meterMiles,
    repairs: [
      { id: 'repair-0417', orderNumber: REPAIR_STORY.repairOrder.number, title: REPAIR_STORY.shopWork.keyOperation, date: 'May 14, 2025', status: 'Paid', amountCents: REPAIR_STORY.money.totalCents },
      { id: 'repair-0388', orderNumber: 'RO-2025-0388', title: 'PM Service · Level B', date: 'Apr 18, 2025', status: 'Completed', amountCents: 86_400 },
    ],
  },
] as const satisfies ReadonlyArray<VehicleFixture>)

export const INITIAL_LOCAL_STATE = deepFreeze({
  repairOrders: { selectedEvidence: 'invoice', invoiceExpanded: true, historyExpanded: false },
  customers: { selectedCustomerId: REPAIR_STORY.customer.id, detailTab: 'overview' },
  shopWork: { activeTab: 'queue', selectedOrderId: 'shop-order-on-floor' },
  invoices: { selectedInvoiceId: REPAIR_STORY.invoice.id, expandedInvoiceId: REPAIR_STORY.invoice.id },
  vehicleHistory: { selectedVehicleId: REPAIR_STORY.vehicle.id, expandedRepairId: 'repair-0417' },
} as const satisfies PreviewLocalState)

export const formatStoryCurrency = (cents: number) => new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', minimumFractionDigits: 2,
}).format(cents / 100)

export const formatStoryMiles = (value: number) => `${new Intl.NumberFormat('en-US').format(value)} mi`

export function getContextSheet(moduleId: ModuleId): SheetModel {
  const models: Record<ModuleId, SheetModel> = {
    'repair-orders': {
      eyebrow: 'Repair Orders', title: REPAIR_STORY.repairOrder.number, summary: REPAIR_STORY.repairOrder.concern,
      status: `${REPAIR_STORY.repairOrder.state} · ${REPAIR_STORY.repairOrder.lifecycle}`, tone: 'success',
      facts: [{ label: 'Customer', value: REPAIR_STORY.customer.company }, { label: 'Vehicle', value: `Unit ${REPAIR_STORY.vehicle.unit}` }],
    },
    customers: {
      eyebrow: 'Customers', title: REPAIR_STORY.customer.company, summary: REPAIR_STORY.customer.authorizationContact,
      status: 'Balance $0.00', tone: 'neutral',
      facts: [{ label: 'Contact', value: REPAIR_STORY.customer.approvalChannel }, { label: 'Vehicles', value: String(REPAIR_STORY.customer.vehicleCount) }],
    },
    'shop-work': {
      eyebrow: 'Shop Cockpit', title: 'Work Queue', summary: 'Actionable repair orders organized by shop state.',
      status: '3 active lanes', tone: 'warm',
      facts: [{ label: 'On the floor', value: REPAIR_STORY.repairOrder.number }, { label: 'Bay', value: REPAIR_STORY.shopWork.bay }],
    },
    invoices: {
      eyebrow: 'Invoices', title: REPAIR_STORY.invoice.number, summary: `${REPAIR_STORY.customer.company} · ${formatStoryCurrency(REPAIR_STORY.invoice.totalCents)}`,
      status: REPAIR_STORY.invoice.state, tone: 'document',
      facts: [{ label: 'Repair order', value: REPAIR_STORY.repairOrder.number }, { label: 'Balance', value: formatStoryCurrency(REPAIR_STORY.payment.balanceCents) }],
    },
    'vehicle-history': {
      eyebrow: 'Vehicle History', title: `Unit ${REPAIR_STORY.vehicle.unit}`, summary: `${REPAIR_STORY.vehicle.year} ${REPAIR_STORY.vehicle.make} ${REPAIR_STORY.vehicle.model}`,
      status: 'History current', tone: 'success',
      facts: [{ label: 'Owner', value: REPAIR_STORY.vehicle.owner }, { label: 'VIN', value: REPAIR_STORY.vehicle.maskedVin }],
    },
  }
  return models[moduleId]
}

export function getEventSheet(moduleId: ModuleId, local: PreviewLocalState): SheetModel | null {
  if (moduleId === 'repair-orders') {
    const evidence = local.repairOrders.selectedEvidence
    if (evidence === 'invoice') return {
      eyebrow: 'Invoice evidence', title: REPAIR_STORY.invoice.number, summary: `Finalized ${REPAIR_STORY.invoice.created.display}`,
      status: REPAIR_STORY.invoice.state, tone: 'document', facts: [{ label: 'Total', value: formatStoryCurrency(REPAIR_STORY.invoice.totalCents) }, { label: 'Payment', value: REPAIR_STORY.payment.method }],
    }
    if (evidence === 'history') return {
      eyebrow: 'Repair order history', title: 'Payment recorded', summary: REPAIR_STORY.payment.recorded.display,
      status: 'History updated', tone: 'success', facts: [{ label: 'Approved', value: REPAIR_STORY.repairOrder.approvalRecorded.display }, { label: 'Closed balance', value: formatStoryCurrency(REPAIR_STORY.payment.balanceCents) }],
    }
    return {
      eyebrow: 'Work & Labor', title: evidence === 'work-def' ? REPAIR_STORY.shopWork.keyOperation : 'Aftertreatment system diagnostic',
      summary: evidence === 'work-def' ? '2.5 hr labor · 2 parts' : '2 hr labor · diagnostic line', status: 'Completed', tone: 'warm',
      facts: evidence === 'work-def'
        ? [{ label: 'Labor', value: formatStoryCurrency(75_000) }, { label: 'Parts', value: formatStoryCurrency(REPAIR_STORY.money.partsCents) }]
        : [{ label: 'Labor', value: formatStoryCurrency(50_000) }, { label: 'Technician', value: REPAIR_STORY.shopWork.leadTechnician }],
    }
  }

  if (moduleId === 'customers') {
    const customer = CUSTOMERS.find((item) => item.id === local.customers.selectedCustomerId)
    if (!customer) return null
    const history = customer.history[0]
    return {
      eyebrow: local.customers.detailTab === 'history' ? 'Customer history' : 'Customer selected', title: customer.company,
      summary: local.customers.detailTab === 'history' && history ? history.label : `${customer.contact} · ${customer.email}`,
      status: customer.balanceCents === 0 ? 'Balance $0.00' : `Balance ${formatStoryCurrency(customer.balanceCents)}`, tone: customer.balanceCents === 0 ? 'success' : 'neutral',
      facts: local.customers.detailTab === 'history' && history
        ? [{ label: 'Recorded', value: history.at }, { label: 'Amount', value: formatStoryCurrency(history.amountCents) }]
        : [{ label: 'Phone', value: customer.phone }, { label: 'Vehicles', value: String(customer.vehicleCount) }],
    }
  }

  if (moduleId === 'shop-work') {
    const order = SHOP_ORDERS.find((item) => item.id === local.shopWork.selectedOrderId)
    if (!order) return null
    return {
      eyebrow: local.shopWork.activeTab === 'activity' ? 'Shop activity' : order.lane, title: order.orderNumber,
      summary: local.shopWork.activeTab === 'activity' ? order.activity : order.summary, status: order.status, tone: order.lane === 'Needs Action' ? 'warm' : 'neutral',
      facts: [{ label: 'Vehicle', value: order.vehicle }, { label: 'Technician', value: order.technician }],
    }
  }

  if (moduleId === 'invoices') {
    const invoice = INVOICES.find((item) => item.id === local.invoices.selectedInvoiceId)
    if (!invoice) return null
    return {
      eyebrow: 'Invoice selected', title: invoice.number, summary: `${invoice.customer} · ${invoice.orderNumber}`, status: invoice.state,
      tone: invoice.state === 'Paid' ? 'success' : invoice.state === 'Pending Zelle confirmation' ? 'warm' : 'document',
      facts: [{ label: 'Total', value: formatStoryCurrency(invoice.totalCents) }, { label: 'Balance', value: formatStoryCurrency(invoice.balanceCents) }],
    }
  }

  const vehicle = VEHICLES.find((item) => item.id === local.vehicleHistory.selectedVehicleId)
  const repair = vehicle?.repairs.find((item) => item.id === local.vehicleHistory.expandedRepairId)
  if (!vehicle || !repair) return null
  return {
    eyebrow: 'Repair history', title: repair.orderNumber, summary: repair.title, status: repair.status, tone: 'success',
    facts: [{ label: 'Date', value: repair.date }, { label: 'Total', value: formatStoryCurrency(repair.amountCents) }],
  }
}

export function getStatusAnnouncement(moduleId: ModuleId, local: PreviewLocalState) {
  const module = MODULES.find((item) => item.id === moduleId)
  const event = getEventSheet(moduleId, local)
  return event ? `${module?.label ?? moduleId} selected. ${event.title}. ${event.status}.` : `${module?.label ?? moduleId} selected.`
}
