import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Toaster, ToastBar, toast, useToasterStore } from 'react-hot-toast'
import { useAuthStore } from './stores/authStore'
import api from './lib/api'
import { ThemeProvider, useTheme, type NotificationPosition } from './contexts/ThemeContext'
import LandingPage from './features/landing/LandingPage'
import PrivacyPolicyPage from './features/landing/PrivacyPolicyPage'
import TermsOfServicePage from './features/landing/TermsOfServicePage'
import LoginPage from './features/auth/LoginPage'
import ForgotPasswordPage from './features/auth/ForgotPasswordPage'
import ResetPasswordPage from './features/auth/ResetPasswordPage'
import VerifyEmailPage from './features/auth/VerifyEmailPage'
import GarageEnrollmentPage from './features/auth/GarageEnrollmentPage'
import GarageEnrollmentSuccessPage from './features/auth/GarageEnrollmentSuccessPage'
import DashboardLayout from './components/layout/DashboardLayout'
import CustomerPortalPage from './features/customer-portal/CustomerPortalPage'
import QuoteApprovalPage from './features/quote-approval/QuoteApprovalPage'
import MechanicPortalPage from './features/mechanic-portal/MechanicPortalPage'
import FleetApp from './features/fleet/FleetApp'
import DriverPortalPage from './features/driver-portal/DriverPortalPage'
import InvoiceAccessPage from './features/invoice-access/InvoiceAccessPage'

type FaviconAssetSet = {
  svg: string
  png: string
}

const PUBLIC_FAVICON: FaviconAssetSet = {
  svg: '/DB_bridge_logo_favi_figma_public.svg',
  png: '/DB_bridge_logo_favi_figma_public.png',
}

const ADMIN_FAVICON: FaviconAssetSet = {
  svg: '/DB_bridge_logo_favi_figma_admin.svg',
  png: '/DB_bridge_logo_favi_figma_admin.png',
}

const ADMIN_FAVICON_PATHS = [
  /^\/dashboard(\/|$)/,
  /^\/mechanic(\/|$)/,
  /^\/driver(\/|$)/,
  /^\/login$/,
  /^\/register$/,
  /^\/forgot-password$/,
  /^\/reset-password$/,
  /^\/verify-email$/,
]

const PUBLIC_ANALYTICS_PATHS = new Set([
  '/',
  '/enroll',
  '/enroll/success',
  '/privacy',
  '/terms',
  '/login',
  '/forgot-password',
  '/reset-password',
  '/verify-email',
])

function isTokenAccessRoute(pathname: string): boolean {
  return /^\/(quote|invoice)\/[^/]+$/.test(pathname)
}

function isProductAnalyticsRoute(pathname: string, role?: string): boolean {
  if (PUBLIC_ANALYTICS_PATHS.has(pathname) || isTokenAccessRoute(pathname)) return true
  if (role === 'super_admin') return false

  // Protected product surfaces are tracked only after the authenticated user's
  // role is known. This keeps platform-super-admin navigation out of GA.
  return Boolean(role) && /^(\/dashboard|\/portal|\/mechanic|\/fleet|\/driver)(\/|$)/.test(pathname)
}

function analyticsPagePath(pathname: string, search: string): string {
  if (isTokenAccessRoute(pathname)) return pathname.startsWith('/quote/') ? '/quote/:token' : '/invoice/:token'

  // Usage analytics needs page families, not tenant/customer record identifiers.
  const redactedPath = pathname
    .replace(/\/[0-9a-f]{8}-[0-9a-f-]{27,}/gi, '/:id')
    .replace(/\/\d+(?=\/|$)/g, '/:id')

  return `${redactedPath}${search}`
}

function loadGoogleAnalytics(measurementId: string) {
  if (document.getElementById('google-analytics-tag')) return

  const tag = document.createElement('script')
  tag.id = 'google-analytics-tag'
  tag.async = true
  tag.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`
  document.head.appendChild(tag)

  window.dataLayer = window.dataLayer || []
  window.gtag = window.gtag || function gtag(...args: unknown[]) { window.dataLayer?.push(args) }
  window.gtag('js', new Date())
  window.gtag('config', measurementId, { send_page_view: false })
}

function ProductAnalyticsTracker() {
  const location = useLocation()
  const { user } = useAuthStore()

  useEffect(() => {
    const measurementId = import.meta.env.VITE_GA_MEASUREMENT_ID?.trim()
    const isProductionSite = ['dieselbridge.com', 'www.dieselbridge.com'].includes(window.location.hostname)
    const pagePath = analyticsPagePath(location.pathname, location.search)

    if (!measurementId || !isProductionSite || !isProductAnalyticsRoute(location.pathname, user?.role)) return

    loadGoogleAnalytics(measurementId)
    window.gtag?.('event', 'page_view', {
      page_title: document.title,
      page_location: `${window.location.origin}${pagePath}`,
      page_path: pagePath,
    })
  }, [location.pathname, location.search, user?.role])

  return null
}

function resolveFavicon(pathname: string): FaviconAssetSet {
  return ADMIN_FAVICON_PATHS.some((pattern) => pattern.test(pathname)) ? ADMIN_FAVICON : PUBLIC_FAVICON
}

function upsertFaviconLink(rel: 'icon' | 'shortcut icon', type: 'image/svg+xml' | 'image/png'): HTMLLinkElement {
  let link = document.querySelector(`link[rel="${rel}"][type="${type}"]`) as HTMLLinkElement | null
  if (!link) {
    link = document.createElement('link')
    link.setAttribute('rel', rel)
    document.head.appendChild(link)
  }
  link.setAttribute('type', type)
  return link
}

const MAX_VISIBLE_TOASTS = 3

const TOAST_POSITION_MAP: Record<NotificationPosition, 'top-right' | 'bottom-right' | 'top-center'> = {
  top: 'top-right',
  bottom: 'bottom-right',
  'center-top': 'top-center',
}

const TOAST_CONTAINER_STYLE_MAP: Record<NotificationPosition, React.CSSProperties> = {
  top: { top: 16, right: 16 },
  bottom: { bottom: 16, right: 16 },
  'center-top': { top: 16, left: '50%', transform: 'translateX(-50%)' },
}

function ToastLimiter() {
  const { toasts } = useToasterStore()

  useEffect(() => {
    toasts
      .filter((t) => t.visible)
      .slice(MAX_VISIBLE_TOASTS)
      .forEach((t) => toast.dismiss(t.id))
  }, [toasts])

  return null
}

function RouteFaviconManager() {
  const location = useLocation()

  useEffect(() => {
    const icon = resolveFavicon(location.pathname)
    upsertFaviconLink('icon', 'image/svg+xml').setAttribute('href', icon.svg)
    upsertFaviconLink('icon', 'image/png').setAttribute('href', icon.png)
    upsertFaviconLink('shortcut icon', 'image/png').setAttribute('href', icon.png)
  }, [location.pathname])

  return null
}

function AppToaster() {
  const { notificationPosition } = useTheme()

  return (
    <Toaster
      position={TOAST_POSITION_MAP[notificationPosition]}
      containerStyle={TOAST_CONTAINER_STYLE_MAP[notificationPosition]}
      toastOptions={{
        duration: 4000,
        style: {
          background: '#1f2937',
          color: '#fff',
          borderRadius: '0.75rem',
          maxWidth: '480px',
          width: 'auto',
          padding: '12px 16px',
        },
        success: {
          iconTheme: { primary: '#10b981', secondary: '#fff' },
        },
        error: {
          iconTheme: { primary: '#ef4444', secondary: '#fff' },
        },
      }}
    >
      {(t) => (
        <ToastBar toast={t}>
          {({ icon, message }) => (
            <>
              {icon}
              <span className="whitespace-nowrap">{message}</span>
              {t.type !== 'loading' && (
                <button
                  type="button"
                  onClick={() => toast.dismiss(t.id)}
                  aria-label="Dismiss notification"
                  className="ml-2 -mr-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-white/60 hover:text-white hover:bg-white/10 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </>
          )}
        </ToastBar>
      )}
    </Toaster>
  )
}

function StaffRoute({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuthStore()
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  
  // Redirect roles with their own standalone app away from the garage dashboard.
  if (user?.role === 'customer') {
    return <Navigate to="/portal" replace />
  }
  if (user?.role === 'mechanic') {
    return <Navigate to="/mechanic" replace />
  }
  // The fleet manager's whole app is the fleet board; they have no garage dashboard.
  if (user?.role === 'fleet_manager') {
    return <Navigate to="/fleet" replace />
  }
  if (user?.role === 'driver') {
    return <Navigate to="/driver" replace />
  }

  return <>{children}</>
}

function DriverRoute({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated, establishCookieSession } = useAuthStore()
  const [checkingSession, setCheckingSession] = useState(!isAuthenticated)

  useEffect(() => {
    if (isAuthenticated) {
      setCheckingSession(false)
      return
    }
    let active = true
    api.get('/auth/me')
      .then(({ data }) => {
        if (active && data.role === 'driver') establishCookieSession(data)
      })
      .catch(() => undefined)
      .finally(() => { if (active) setCheckingSession(false) })
    return () => { active = false }
  }, [establishCookieSession, isAuthenticated])

  if (checkingSession) return <div className="min-h-screen bg-[#081018] text-white grid place-items-center">Opening driver workspace…</div>
  if (!useAuthStore.getState().isAuthenticated) return <Navigate to="/login" replace />
  if ((user || useAuthStore.getState().user)?.role !== 'driver') return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

function FleetRoute({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuthStore()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  // Fleet board is for the fleet manager + the garage owner/admin who own the fleet.
  if (!['fleet_manager', 'garage_owner', 'garage_admin'].includes(user?.role || '')) {
    return <Navigate to="/dashboard" replace />
  }
  return <>{children}</>
}

function CustomerRoute({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuthStore()
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  
  if (user?.role !== 'customer') {
    return <Navigate to="/dashboard" replace />
  }
  
  return <>{children}</>
}

function MechanicRoute({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuthStore()
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  
  if (user?.role !== 'mechanic') {
    return <Navigate to="/dashboard" replace />
  }
  
  return <>{children}</>
}

function App() {
  return (
    <ThemeProvider>
    <BrowserRouter>
      <ProductAnalyticsTracker />
      <RouteFaviconManager />
      <ToastLimiter />
      <AppToaster />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<Navigate to="/login" replace />} />
        <Route path="/enroll" element={<GarageEnrollmentPage />} />
        <Route path="/enroll/success" element={<GarageEnrollmentSuccessPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/quote/:token" element={<QuoteApprovalPage />} />
        <Route path="/invoice/:token" element={<InvoiceAccessPage />} />
        
        <Route
          path="/dashboard/*"
          element={
            <StaffRoute>
              <DashboardLayout />
            </StaffRoute>
          }
        />
        
        <Route
          path="/portal/*"
          element={
            <CustomerRoute>
              <CustomerPortalPage />
            </CustomerRoute>
          }
        />
        
        <Route
          path="/mechanic/*"
          element={
            <MechanicRoute>
              <MechanicPortalPage />
            </MechanicRoute>
          }
        />

        <Route
          path="/fleet/*"
          element={
            <FleetRoute>
              <FleetApp />
            </FleetRoute>
          }
        />

        <Route
          path="/driver/*"
          element={
            <DriverRoute>
              <DriverPortalPage />
            </DriverRoute>
          }
        />
        
        <Route path="/" element={<LandingPage />} />
        <Route path="/privacy" element={<PrivacyPolicyPage />} />
        <Route path="/terms" element={<TermsOfServicePage />} />
      </Routes>
    </BrowserRouter>
    </ThemeProvider>
  )
}

export default App
