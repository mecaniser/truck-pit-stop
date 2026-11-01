import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ShopWorkOverview, { type ShopWorkOverviewData, type ShopWorkItem, type OverviewSourceStatus } from '../ShopWorkOverview'
const item = (overrides: Partial<ShopWorkItem> = {}): ShopWorkItem => ({ id: 'inventory:part-a', source: 'inventory', destination: { kind: 'inventory', id: 'part-a', view: null }, title: 'Brake chamber T30', reason: 'stock_preparation', action_label: 'Review stock', status: 'needs_review', created_at: null, due_at: null, due_kind: null, evidence: 'verified', quantity: 2, related_repair_order_ids: [], ...overrides })
const source = (overrides: Partial<OverviewSourceStatus> = {}): OverviewSourceStatus => ({ id: 'inventory', state: 'ready', checked_at: '2026-11-01T15:00:00Z', reason: null, total: 1, shown: 1, has_more: false, ...overrides })
const data = (overrides: Partial<ShopWorkOverviewData> = {}): ShopWorkOverviewData => ({ as_of: '2026-11-01T15:00:00Z', timezone: 'America/New_York', scope: 'shop', active_jobs: 0, sources: [source()], actions: [item()], upcoming: [], actions_total: 1, upcoming_total: 0, has_more_actions: false, has_more_upcoming: false, ...overrides })
function setup(value?: ShopWorkOverviewData, overrides = {}) {
 const props = { data: value, loading: false, failed: false, refreshing: false, onRetry: vi.fn(), onOpen: vi.fn(), onWorkspace: vi.fn(), ...overrides }
 return { props, ...render(<ShopWorkOverview {...props} />) }
}
describe('Shop Work overview', () => {
 it('shows a stock task exactly once with zero active jobs and opens the exact record', () => {
  const { props } = setup(data()); expect(document.querySelectorAll('[data-work-id="inventory:part-a"]')).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', { name: 'Review stock: Brake chamber T30' }))
  expect(props.onOpen).toHaveBeenCalledWith({ kind: 'inventory', id: 'part-a', view: null }); expect(screen.queryByText(/caught up/i)).not.toBeInTheDocument()
 })
 it('opens cross-domain identities without duplicating their editors or financial amounts', () => {
  const rows = [item(), item({ id: 'return:r2', title: 'Return R2', source: 'returns', destination: { kind: 'vendor_return', id: 'r2', view: null }, action_label: 'Review return' }), item({ id: 'account:c3', title: 'Customer C3', source: 'receivables', destination: { kind: 'customer_account', id: 'c3', view: null }, action_label: 'Review account', quantity: null, reason: 'account_verification_required' })]
  const { props } = setup(data({ actions: rows })); rows.forEach(row => fireEvent.click(screen.getByRole('button', { name: `${row.action_label}: ${row.title}` })))
  expect(props.onOpen.mock.calls.map(args => args[0])).toEqual(rows.map(row => row.destination)); expect(screen.queryByRole('textbox')).not.toBeInTheDocument(); expect(screen.queryByText(/\$/)).not.toBeInTheDocument()
 })
 it('shows actual future dates as expected delivery and opens the PO receiving context', () => {
  const row = item({ id: 'po:p1', source: 'purchasing', title: 'PO-208', action_label: 'Review delivery', destination: { kind: 'purchase_order', id: 'p1', view: 'receiving' }, due_at: '2026-11-02T16:30:00Z', due_kind: 'expected_delivery' })
  const { props } = setup(data({ upcoming: [row] })); const upcoming = screen.getByRole('complementary'); expect(upcoming).toHaveTextContent('Nov 2, 11:30 AM'); expect(upcoming).not.toHaveTextContent('confirmed')
  fireEvent.click(within(upcoming).getByRole('button', { name: 'Review delivery: PO-208' })); expect(props.onOpen).toHaveBeenCalledWith(row.destination)
 })
 it('does not claim all clear for unavailable or partially verified sources', () => {
  setup(data({ actions: [], actions_total: null, sources: [source({ id: 'receivables', state: 'partial', reason: 'account_review_only', total: null, shown: 0 }), source({ state: 'unavailable', total: null, shown: 0 })] }))
  expect(screen.getByText('No confirmed actions in the checked work')).toBeInTheDocument(); expect(screen.getByText(/Collectible balances require verification/)).toBeInTheDocument(); expect(screen.queryByText(/caught up/)).not.toBeInTheDocument(); expect(screen.getByText('0 shown')).toBeInTheDocument()
 })
 it('does not turn an unknown account source into a claim that more records exist', () => {
  setup(data({ actions: [], actions_total: null, sources: [source({ id: 'receivables', state: 'partial', reason: 'classification_unavailable', total: null, shown: 0, has_more: true })] }))
  expect(screen.getByText('Account verification is unavailable. Review invoices in Customer accounts.')).toBeInTheDocument(); expect(screen.queryByText('More records are available in this workspace.')).not.toBeInTheDocument()
 })
 it('scopes an empty-state claim to accessible checked workspaces', () => {
  setup(data({ actions: [], actions_total: 0, sources: [source({ total: 0, shown: 0 }), source({ id: 'receivables', state: 'restricted', total: null, shown: 0 })] }))
  expect(screen.getByText('You’re caught up in your available workspaces')).toBeInTheDocument(); expect(screen.queryByRole('button', { name: /Customer accounts/ })).not.toBeInTheDocument()
 })
 it('retains stale rows after a failed refresh and offers retry', () => {
  const { props } = setup(data(), { failed: true }); expect(screen.getByRole('alert')).toHaveTextContent('Showing the last checked work'); expect(screen.getByText('Brake chamber T30')).toBeInTheDocument(); fireEvent.click(screen.getByRole('button', { name: 'Retry', exact: true })); expect(props.onRetry).toHaveBeenCalledOnce()
 })
 it('handles initial loading and failure without inventing zero', () => {
  const { props, rerender } = setup(undefined, { loading: true }); expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true'); rerender(<ShopWorkOverview {...props} loading={false} failed />); expect(screen.getByRole('alert')).toHaveTextContent('Shop overview is unavailable'); expect(screen.queryByText('0 tasks')).not.toBeInTheDocument()
 })
 it('reveals the remaining tasks and routes overflow to its owning workspace', () => {
  const actions = Array.from({ length: 8 }, (_, i) => item({ id: `inventory:${i}`, title: `Part ${i}` })); const { props } = setup(data({ actions, actions_total: null, has_more_actions: true, sources: [source({ has_more: true, state: 'partial', total: null, shown: 8 })] }))
  expect(document.querySelectorAll('[data-work-id]')).toHaveLength(6); fireEvent.click(screen.getByRole('button', { name: 'Show next 2 tasks' })); expect(document.querySelectorAll('[data-work-id]')).toHaveLength(8); fireEvent.click(screen.getByRole('button', { name: 'Inventory', exact: true })); expect(props.onWorkspace).toHaveBeenCalledWith('/dashboard/garage/inventory')
 })
 it('routes incomplete upcoming coverage without asserting more dated work exists', () => {
  const { props } = setup(data({ upcoming_total: null, has_more_upcoming: true, sources: [source({ id: 'purchasing', state: 'partial', reason: 'source_limit', total: null, has_more: true })] }))
  expect(screen.getByText('Review upcoming commitments in their workspace.')).toBeInTheDocument(); expect(screen.queryByText('More dated work is available in its workspace.')).not.toBeInTheDocument(); fireEvent.click(screen.getByRole('button', { name: 'Purchasing', exact: true })); expect(props.onWorkspace).toHaveBeenCalledWith('/dashboard/garage/purchasing?view=orders')
 })
 it('keeps unknown local times unknown', () => { setup(data({ timezone: null, upcoming: [item({ due_at: '2026-11-02T16:30:00Z', due_kind: 'repair_start' })] })); expect(screen.getByText('Time unavailable')).toBeInTheDocument() })
})
