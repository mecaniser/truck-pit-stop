import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import MyGaragePage from '../MyGaragePage'

vi.mock('@/features/dashboard/ServicesManagementPage', () => ({ default: () => <h1>Services surface</h1> }))
vi.mock('@/features/inventory/InventoryPage', () => ({ default: () => <h1>Inventory surface</h1> }))
vi.mock('@/features/inventory/PurchasingWorkspace', () => ({ default: () => <h1>Purchasing surface</h1> }))
vi.mock('@/features/mechanics/MechanicsPage', () => ({ default: () => <h1>Team surface</h1> }))
vi.mock('../GarageAnalyticsPage', () => ({ default: () => <h1>Analytics surface</h1> }))
vi.mock('../LaborBookTimePage', () => ({ default: () => <h1>Labor Book Time surface</h1> }))
vi.mock('@/features/reviews/GoogleReviewsPage', () => ({ default: () => null }))
vi.mock('@/features/reviews/GoogleReviewsSettingsPage', () => ({ default: () => null }))

const operationalHrefs = [
  '/dashboard/garage/services',
  '/dashboard/garage/labor-book-time',
  '/dashboard/garage/inventory',
  '/dashboard/garage/purchasing',
]
const secondaryHrefs = ['/dashboard/garage/mechanics', '/dashboard/garage/analytics']

function renderGarage(path = '/dashboard/garage/inventory') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/dashboard/garage/*" element={<MyGaragePage />} />
      </Routes>
    </MemoryRouter>,
  )
}

function hrefs(group: HTMLElement) {
  return within(group).getAllByRole('link').map(link => link.getAttribute('href'))
}

describe('DB-043 container-adaptive Shop navigation', () => {
  it('uses one semantic navigation while preserving the operational and secondary groups', () => {
    renderGarage()

    const navigation = screen.getByRole('navigation', { name: 'Shop sections' })
    expect(navigation).toHaveAttribute('data-shop-menu-layout', 'container-adaptive')

    const operations = within(navigation).getByRole('group', { name: 'Shop operations' })
    const secondary = within(navigation).getByRole('group', { name: 'Shop administration and insights' })

    expect(hrefs(operations)).toEqual(operationalHrefs)
    expect(hrefs(secondary)).toEqual(secondaryHrefs)
    expect(operations.compareDocumentPosition(secondary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(secondary).toHaveClass('db-my-shop-nav-cluster-secondary')
    expect(within(operations).getAllByRole('link')).toHaveLength(4)
    expect(within(secondary).getAllByRole('link')).toHaveLength(2)
    expect(within(navigation).getByRole('link', { name: 'Labor Book Time' })).toHaveAttribute(
      'href',
      '/dashboard/garage/labor-book-time',
    )
  })

  it('preserves routes, icons, selected state, target sizing, and one keyboard order without reveal animation', async () => {
    const user = userEvent.setup()
    renderGarage()

    const navigation = screen.getByRole('navigation', { name: 'Shop sections' })
    const links = within(navigation).getAllByRole('link')
    expect(links.map(link => link.getAttribute('aria-label'))).toEqual([
      'Services',
      'Labor Book Time',
      'Inventory',
      'Purchasing',
      'Team',
      'Analytics',
    ])
    for (const link of links) {
      expect(link).toHaveClass('min-h-11')
      expect(link.querySelector('svg')).toBeInTheDocument()
      expect(link).not.toHaveClass('transition-all', 'opacity-0')
      expect(link.getAttribute('class')).not.toContain('animate-[')
      expect(link).not.toHaveAttribute('style')
    }
    expect(within(navigation).getByRole('link', { name: 'Inventory' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('heading', { name: 'Inventory surface' })).toBeInTheDocument()

    const services = within(navigation).getByRole('link', { name: 'Services' })
    services.focus()
    for (const expectedName of ['Labor Book Time', 'Inventory', 'Purchasing', 'Team', 'Analytics']) {
      await user.tab()
      expect(within(navigation).getByRole('link', { name: expectedName })).toHaveFocus()
    }

    services.focus()
    await user.keyboard('{Enter}')
    expect(await screen.findByRole('heading', { name: 'Services surface' })).toBeInTheDocument()
    expect(within(navigation).getByRole('link', { name: 'Services' })).toHaveAttribute('aria-current', 'page')
  })
})
