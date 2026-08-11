const portalRouteLabel = (pathname: string, search: string): string => {
  if (pathname === '/portal') return 'Dashboard'
  if (pathname === '/portal/services') return 'Services'
  if (pathname.startsWith('/portal/book/')) return 'Book Service'
  if (pathname === '/portal/appointments') return 'Appointments'
  if (pathname === '/portal/vehicles') return 'Vehicles'
  if (pathname === '/portal/repairs') {
    return new URLSearchParams(search).get('view') === 'active'
      ? 'Active Repairs'
      : 'Repair History'
  }
  if (pathname.startsWith('/portal/invoices/')) return 'Invoice'
  if (pathname === '/portal/settings') return 'Account'
  return 'Customer Portal'
}

export const getCustomerPortalTitle = (
  pathname: string,
  search: string,
  portalBrandName: string,
): string => {
  const routeLabel = portalRouteLabel(pathname, search)
  return routeLabel === 'Customer Portal'
    ? `${portalBrandName} Customer Portal`
    : `${routeLabel} | ${portalBrandName} Customer Portal`
}
