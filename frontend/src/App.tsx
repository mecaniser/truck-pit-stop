import { useCookieSessionBootstrap } from './lib/useCookieSessionBootstrap'
import SessionRecoveryNotice from './components/SessionRecoveryNotice'
import StaleDeployNotice from './components/StaleDeployNotice'
import RouteErrorBoundary from './components/RouteErrorBoundary'
import { lazyRouteLoader } from './lib/staleDeploy'
import { lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Toaster, ToastBar, toast, useToasterStore } from 'react-hot-toast'
import { useAuthStore } from './stores/authStore'
import { ThemeProvider, useTheme, type NotificationPosition } from './contexts/ThemeContext'
import { AppearanceNavigationGuardProvider } from './features/dashboard/AppearanceNavigationGuard'

const LandingPage = lazy(lazyRouteLoader(() => import('./features/landing/LandingPage')))
const PrivacyPolicyPage = lazy(lazyRouteLoader(() => import('./features/landing/PrivacyPolicyPage')))
const TermsOfServicePage = lazy(lazyRouteLoader(() => import('./features/landing/TermsOfServicePage')))
const LoginPage = lazy(lazyRouteLoader(() => import('./features/auth/LoginPage')))
const DriverLoginPage = lazy(lazyRouteLoader(() => import('./features/auth/DriverLoginPage')))
const ForgotPasswordPage = lazy(lazyRouteLoader(() => import('./features/auth/ForgotPasswordPage')))
const ResetPasswordPage = lazy(lazyRouteLoader(() => import('./features/auth/ResetPasswordPage')))
const VerifyEmailPage = lazy(lazyRouteLoader(() => import('./features/auth/VerifyEmailPage')))
const GarageEnrollmentPage = lazy(lazyRouteLoader(() => import('./features/auth/GarageEnrollmentPage')))
const GarageEnrollmentSuccessPage = lazy(lazyRouteLoader(() => import('./features/auth/GarageEnrollmentSuccessPage')))
const DashboardLayout = lazy(lazyRouteLoader(() => import('./components/layout/DashboardLayout')))
const CustomerPortalPage = lazy(lazyRouteLoader(() => import('./features/customer-portal/CustomerPortalPage')))
const QuoteApprovalPage = lazy(lazyRouteLoader(() => import('./features/quote-approval/QuoteApprovalPage')))
const MechanicPortalPage = lazy(lazyRouteLoader(() => import('./features/mechanic-portal/MechanicPortalPage')))
const FleetApp = lazy(lazyRouteLoader(() => import('./features/fleet/FleetApp')))
const DriverPortalPage = lazy(lazyRouteLoader(() => import('./features/driver-portal/DriverPortalPage')))
const InvoiceAccessPage = lazy(lazyRouteLoader(() => import('./features/invoice-access/InvoiceAccessPage')))

type FaviconAssetSet = {
  svg: string
  png?: string
}

const HOME_FAVICON: FaviconAssetSet = {
  svg: '/dieselbridge-mark.svg',
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
  '/driver/login',
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
  if (pathname === '/') return HOME_FAVICON
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
  bottom: { right: 16 },
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
    if (icon.png) {
      upsertFaviconLink('icon', 'image/png').setAttribute('href', icon.png)
      upsertFaviconLink('shortcut icon', 'image/png').setAttribute('href', icon.png)
    } else {
      document.querySelectorAll('link[type="image/png"][rel="icon"], link[type="image/png"][rel="shortcut icon"]').forEach((link) => link.remove())
    }
  }, [location.pathname])

  return null
}

function AppToaster() {
  const { notificationPosition, presentationVariant } = useTheme()

  return (
    <Toaster
      position={TOAST_POSITION_MAP[notificationPosition]}
      containerStyle={{
        ...TOAST_CONTAINER_STYLE_MAP[notificationPosition],
        ...(notificationPosition === 'bottom'
          ? { bottom: presentationVariant === 'new' ? 'calc(env(safe-area-inset-bottom, 0px) + 88px)' : 16 }
          : {}),
      }}
      containerClassName={`db-toaster db-toaster--${presentationVariant}`}
      toastOptions={{
        duration: 4000,
        style: {
          background: '#1f2937',
          color: '#fff',
          borderRadius: '0.75rem',
          maxWidth: 'min(480px, calc(100vw - 32px))',
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
              <span className="min-w-0 whitespace-normal break-words">{message}</span>
              {t.type !== 'loading' && (
                <button
                  type="button"
                  onClick={() => toast.dismiss(t.id)}
                  aria-label="Dismiss notification"
                  className="ml-2 -mr-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-white/60 hover:text-white hover:bg-white/10 transition-colors"
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

function SessionBootstrapStatus({ recovering }: { recovering: boolean }) {
  return <div role="status" className="min-h-screen bg-zinc-950 px-6 text-center text-white grid place-items-center">
    <div><p>{recovering ? 'Reconnecting your session' : 'Opening workspace…'}</p>
      {recovering && <p className="mt-2 max-w-md text-sm text-zinc-300">We’re having trouble checking your session. We’ll retry automatically. Please keep this page open.</p>}
    </div>
  </div>
}

function StaffRoute({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuthStore()
  const { checkingSession, recovering, endReason } = useCookieSessionBootstrap()

  if (checkingSession) {
    return <SessionBootstrapStatus recovering={recovering} />
  }
  
  if (!isAuthenticated) {
    return <Navigate to={endReason ? `/login?reason=${endReason}` : "/login"} replace />
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
  const { user } = useAuthStore()
  const { checkingSession, recovering, endReason } = useCookieSessionBootstrap()

  if (checkingSession) return <SessionBootstrapStatus recovering={recovering} />
  if (!useAuthStore.getState().isAuthenticated) return <Navigate to={endReason ? `/driver/login?reason=${endReason}` : "/driver/login"} replace />
  if ((user || useAuthStore.getState().user)?.role !== 'driver') return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

function FleetRoute({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuthStore()
  const { checkingSession, recovering, endReason } = useCookieSessionBootstrap()

  if (checkingSession) {
    return <SessionBootstrapStatus recovering={recovering} />
  }

  if (!isAuthenticated) {
    return <Navigate to={endReason ? `/login?reason=${endReason}` : "/login"} replace />
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

function RouteLoading() {
  const location = useLocation()
  const isDarkWorkspace = /^\/(driver|fleet|mechanic)(\/|$)/.test(location.pathname)
  return (
    <main
      className={`min-h-screen grid place-items-center ${isDarkWorkspace ? 'bg-[#081018] text-white' : 'bg-white text-slate-700'}`}
      role="status"
      aria-live="polite"
    >
      {isDarkWorkspace ? 'Opening workspace…' : 'Loading…'}
    </main>
  )
}

function App() {
  return (
    <ThemeProvider>
    <BrowserRouter>
      <AppearanceNavigationGuardProvider>
      <ProductAnalyticsTracker />
      <RouteFaviconManager />
      <ToastLimiter />
      <AppToaster />
      <SessionRecoveryNotice />
      <StaleDeployNotice />
      <RouteErrorBoundary>
      <Suspense fallback={<RouteLoading />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/driver/login" element={<DriverLoginPage />} />
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
      </Suspense>
      </RouteErrorBoundary>
      </AppearanceNavigationGuardProvider>
    </BrowserRouter>
    </ThemeProvider>
  )
}

export default App
