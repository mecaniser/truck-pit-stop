import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

import { getCustomerPortalTitle } from './portal-title'

export default function PortalDocumentTitle({ portalBrandName }: { portalBrandName: string }) {
  const location = useLocation()

  useEffect(() => {
    document.title = getCustomerPortalTitle(
      location.pathname,
      location.search,
      portalBrandName,
    )
  }, [location.pathname, location.search, portalBrandName])

  return null
}
