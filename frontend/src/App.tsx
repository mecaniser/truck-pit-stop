import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { useAuthStore } from './stores/authStore'
import { ThemeProvider } from './contexts/ThemeContext'
import LandingPage from './features/landing/LandingPage'
import LoginPage from './features/auth/LoginPage'
import ForgotPasswordPage from './features/auth/ForgotPasswordPage'
import ResetPasswordPage from './features/auth/ResetPasswordPage'
import VerifyEmailPage from './features/auth/VerifyEmailPage'
import GarageEnrollmentPage from './features/auth/GarageEnrollmentPage'
import DashboardLayout from './components/layout/DashboardLayout'
import CustomerPortalPage from './features/customer-portal/CustomerPortalPage'
import QuoteApprovalPage from './features/quote-approval/QuoteApprovalPage'
import MechanicPortalPage from './features/mechanic-portal/MechanicPortalPage'
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
  /^\/login$/,
  /^\/register$/,
  /^\/forgot-password$/,
  /^\/reset-password$/,
  /^\/verify-email$/,
]

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

function StaffRoute({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuthStore()
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  
  // Redirect customers and mechanics to their portals
  if (user?.role === 'customer') {
    return <Navigate to="/portal" replace />
  }
  if (user?.role === 'mechanic') {
    return <Navigate to="/mechanic" replace />
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
      <RouteFaviconManager />
      <Toaster
        position="top-right"
        containerStyle={{
          top: 16,
          right: 16,
        }}
        toastOptions={{
          duration: 4000,
          style: {
            background: '#1f2937',
            color: '#fff',
            borderRadius: '0.75rem',
            maxWidth: '480px',
            width: '100%',
            padding: '12px 16px',
          },
          success: {
            iconTheme: { primary: '#10b981', secondary: '#fff' },
          },
          error: {
            iconTheme: { primary: '#ef4444', secondary: '#fff' },
          },
        }}
      />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<Navigate to="/login" replace />} />
        <Route path="/enroll" element={<GarageEnrollmentPage />} />
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
        
        <Route path="/" element={<LandingPage />} />
      </Routes>
    </BrowserRouter>
    </ThemeProvider>
  )
}

export default App
