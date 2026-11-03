import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import PublicPolicyPage from '../features/landing/PublicPolicyPage'
import PrivacyPolicyPage from '../features/landing/PrivacyPolicyPage'
import TermsOfServicePage from '../features/landing/TermsOfServicePage'

afterEach(cleanup)
const mount = (content: React.ReactNode) => render(<MemoryRouter>{content}</MemoryRouter>)
describe('public policies and operator identity', () => {
  it.each(['cookies','refunds','deletion'] as const)('provides operator identity and all policy destinations on %s', kind => {
    mount(<PublicPolicyPage kind={kind} />)
    expect(screen.getByText(/Elis Tech LLC, doing business/)).toBeVisible()
    expect(screen.getByText(/1002 Yearden Ln, Monroe, NC 28110/)).toBeVisible()
    for (const href of ['/privacy','/terms','/refunds','/cookies','/data-deletion']) {
      expect(document.querySelector(`nav a[href="${href}"]`)).toBeInTheDocument()
    }
  })
  it('states the approved monthly refund and cancellation terms without removing statutory rights', () => {
    mount(<PublicPolicyPage kind="refunds" />)
    expect(screen.getByText(/billed month-to-month/)).toHaveTextContent('except where applicable law requires a refund')
    expect(screen.getByText(/billed month-to-month/)).toHaveTextContent('Cancellation stops future monthly renewals')
  })
  it('prepares a deletion email without claiming it was submitted or requesting sensitive IDs', () => {
    mount(<PublicPolicyPage kind="deletion" />)
    expect(screen.getByRole('link', {name:'Email a data deletion request'})).toHaveAttribute('href',expect.stringContaining('mailto:support@dieselbridge.com?subject='))
    expect(screen.getByText(/does not submit a request until you send it/)).toBeVisible()
    expect(screen.getByText(/Do not include passwords/)).toBeVisible()
  })
  it('does not imply that a phone number or accepting terms gives SMS consent', () => {
    mount(<TermsOfServicePage />)
    expect(screen.getByText(/does not by itself give consent to SMS/)).toBeVisible()
  })
  it('describes disabled analytics and manual data rights requests', () => {
    mount(<PrivacyPolicyPage />)
    expect(screen.getByText(/Google Analytics and advertising trackers are disabled/)).toBeVisible()
    expect(screen.getByRole('link', {name:'data deletion request option'})).toHaveAttribute('href','/data-deletion')
  })
})
