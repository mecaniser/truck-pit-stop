import { BUSINESS } from './business'


export default function BusinessContact() {
  return <address className="business-contact" style={{ fontStyle: 'normal' }}>
    {BUSINESS.legalName}, doing business as {BUSINESS.tradingName}<br />
    {BUSINESS.address}<br />
    <a href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a>
  </address>
}
