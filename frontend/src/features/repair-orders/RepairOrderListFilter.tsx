import { Menu, MenuButton, MenuHeading, MenuItem, MenuItems, MenuSection } from '@headlessui/react'
import { Check, ChevronDown } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useTheme } from '@/contexts/ThemeContext'
import { appearanceTokenRecord } from '@/contexts/appearanceTokens'
import { DEFAULT_APPEARANCE } from '@/types/presentation'
import '../dashboard/shopWorkSelect.css'
import { REPAIR_ORDERS_QUEUE_LABEL, type RepairOrdersQueueOrigin } from './repairOrdersPresentation'

export type OrderListView = 'all' | 'overdue' | RepairOrdersQueueOrigin
const labels: Record<OrderListView, string> = { all: 'All repair orders', overdue: 'Overdue', ...REPAIR_ORDERS_QUEUE_LABEL }
const views: OrderListView[] = ['all', 'needs_action', 'on_floor', 'ready_to_close', 'overdue']

export function RepairOrderListFilter({ view, status, options, allowQueueViews, onViewChange, onStatusChange }: {
  view: OrderListView
  allowQueueViews: boolean
  status: string
  options: Array<{ value: string; label: string; count?: number }>
  onViewChange: (view: OrderListView) => void
  onStatusChange: (status: string) => void
}) {
  const appearance = useTheme(true)?.appearance ?? DEFAULT_APPEARANCE
  const statusLabel = options.find(option => option.value === status)?.label ?? status
  const label = status === 'all' ? labels[view] : view === 'all' ? statusLabel : `${labels[view]} · ${statusLabel}`
  const availableViews = allowQueueViews ? views : views.filter(v => v === 'all' || v === 'overdue' || v === view)
  function choice(key: string, text: string, selected: boolean, choose: () => void, count?: number) {
    return <MenuItem key={key} as="button" type="button" data-db-control="content" className="db-work-select-option" onClick={choose} aria-label={selected ? `${text}, selected` : text}>
      <span>{text}</span>
      {count !== undefined && <small>{count}</small>}
      {selected && <Check size={14} aria-hidden="true" />}
    </MenuItem>
  }
  return <Menu>
    <MenuButton className="db-work-select db-order-list-filter" data-db-control="select" aria-label={`Filter repair orders: ${label}`}>
      <span>{label}</span><ChevronDown size={14} aria-hidden="true" />
    </MenuButton>
    <MenuItems anchor="bottom start" className="db-work-select-menu db-order-list-menu" data-appearance-mode={appearance.mode} style={appearanceTokenRecord(appearance) as CSSProperties}>
      <MenuSection>
        <MenuHeading className="db-order-list-menu__heading">View</MenuHeading>
        {(view === 'closed_today' ? [...availableViews, view] : availableViews).map(v => choice(v, labels[v], v === view, () => onViewChange(v)))}
      </MenuSection>
      <MenuSection>
        <MenuHeading className="db-order-list-menu__heading">Order status</MenuHeading>
        {options.map(o => choice(o.value, o.value === 'all' ? 'Any status' : o.label, o.value === status, () => onStatusChange(o.value),
          view === 'all' || view === 'overdue' ? o.count : undefined))}
      </MenuSection>
    </MenuItems>
  </Menu>
}
