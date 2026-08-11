import { act, render } from '@testing-library/react'
import { MemoryRouter, useNavigate } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'

import PortalDocumentTitle from '../PortalDocumentTitle'
import { getCustomerPortalTitle } from '../portal-title'

function PortalTitleHarness({ brand }: { brand: string }) {
  const navigate = useNavigate()

  return (
    <>
      <PortalDocumentTitle portalBrandName={brand} />
      <button type="button" onClick={() => navigate('/portal/repairs?view=active')}>
        Open active repairs
      </button>
    </>
  )
}

describe('PortalDocumentTitle', () => {
  const originalTitle = document.title

  afterEach(() => {
    document.title = originalTitle
  })

  it('maps every customer portal surface to a customer-facing title', () => {
    const cases = [
      ['/portal', '', 'Dashboard'],
      ['/portal/services', '', 'Services'],
      ['/portal/book/service-1', '', 'Book Service'],
      ['/portal/appointments', '', 'Appointments'],
      ['/portal/vehicles', '', 'Vehicles'],
      ['/portal/repairs', '', 'Repair History'],
      ['/portal/repairs', '?view=active', 'Active Repairs'],
      ['/portal/invoices/invoice-1', '', 'Invoice'],
      ['/portal/settings', '', 'Account'],
    ]

    for (const [pathname, search, label] of cases) {
      expect(getCustomerPortalTitle(pathname, search, 'NorthStar Shop')).toBe(
        `${label} | NorthStar Shop Customer Portal`,
      )
    }
  })

  it('updates after client-side navigation and replaces a stale staff-login title', async () => {
    document.title = 'Staff Login | Diesel Bridge Network'
    const view = render(
      <MemoryRouter initialEntries={['/portal']}>
        <PortalTitleHarness brand="NorthStar Shop" />
      </MemoryRouter>,
    )

    expect(document.title).toBe('Dashboard | NorthStar Shop Customer Portal')

    await act(async () => {
      view.getByRole('button', { name: 'Open active repairs' }).click()
    })

    expect(document.title).toBe('Active Repairs | NorthStar Shop Customer Portal')
    expect(document.title).not.toContain('Staff Login')
  })
})
