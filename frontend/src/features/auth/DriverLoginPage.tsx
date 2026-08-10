import { ClipboardCheck, ShieldCheck, TriangleAlert, Truck } from 'lucide-react'
import { useEffect } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import BrandLogo from '../../components/brand/BrandLogo'
import { applySeo } from '../../lib/seo'
import { useAuthStore } from '../../stores/authStore'

const workOSLoginUrl = `${String(import.meta.env.VITE_API_URL || '/api/v1').replace(/\/$/, '')}/auth/workos/login?return_to=%2Fdriver`

export default function DriverLoginPage() {
  const { isAuthenticated, user } = useAuthStore()
  const [searchParams] = useSearchParams()
  const accessNeedsReview = searchParams.get('reason') === 'identity_review_required'

  useEffect(() => {
    const siteOrigin = (import.meta.env.VITE_SITE_URL || window.location.origin).replace(/\/+$/, '')
    applySeo({
      title: 'Driver Login | Diesel Bridge Network',
      description: 'Secure access to assigned equipment, inspections, and incident reporting.',
      canonicalUrl: `${siteOrigin}/driver/login`,
      robots: 'noindex, nofollow',
      ogUrl: `${siteOrigin}/driver/login`,
      ogType: 'website',
      ogSiteName: 'Diesel Bridge Network',
      twitterCard: 'summary',
    })
  }, [])

  if (isAuthenticated) {
    if (user?.role === 'driver') return <Navigate to="/driver" replace />
    if (user?.role === 'customer') return <Navigate to="/portal" replace />
    if (user?.role === 'mechanic') return <Navigate to="/mechanic" replace />
    if (user?.role === 'fleet_manager') return <Navigate to="/fleet" replace />
    return <Navigate to="/dashboard" replace />
  }

  return (
    <main className="min-h-screen bg-[#081018] px-5 py-8 text-white sm:px-8 sm:py-12">
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-md flex-col sm:min-h-[calc(100vh-6rem)]">
        <div className="flex items-center gap-3 self-start text-sm font-bold tracking-[-0.01em] text-slate-200">
          <BrandLogo alt="" variant="admin" className="h-8 w-8 object-contain" />
          <span>Diesel Bridge Network</span>
        </div>

        <section className="my-auto py-12" aria-labelledby="driver-login-title">
          <div className="mb-8 flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-400 text-[#081018] shadow-[0_12px_32px_rgba(251,191,36,0.18)]">
            <Truck className="h-7 w-7" aria-hidden="true" />
          </div>
          <h1 id="driver-login-title" className="max-w-sm text-4xl font-black leading-[1.05] tracking-[-0.03em] text-zinc-50 sm:text-5xl">
            Your equipment.<br />Your record.
          </h1>
          <p className="mt-5 max-w-[42ch] text-base leading-7 text-slate-300">
            Open your assigned truck and trailer, complete inspections, and report conditions as they happen.
          </p>

          {accessNeedsReview && (
            <div
              role="alert"
              className="mt-7 flex gap-3 border-y border-amber-400/35 bg-amber-400/[0.07] py-4 text-amber-50"
            >
              <TriangleAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" aria-hidden="true" />
              <div>
                <h2 className="text-sm font-bold">Driver Portal access needs review</h2>
                <p className="mt-1 text-sm leading-6 text-amber-100/75">
                  This invitation cannot be connected to the account you used. Do not retry it. Ask your fleet manager to review the invitation and send access to a driver-controlled email.
                </p>
              </div>
            </div>
          )}

          <ul className="mt-9 divide-y divide-slate-700/70 border-y border-slate-700/70" aria-label="Driver portal capabilities">
            <li className="flex min-h-14 items-center gap-3 py-3 text-sm font-medium text-slate-200">
              <ShieldCheck className="h-5 w-5 shrink-0 text-emerald-400" aria-hidden="true" />
              Confirm the equipment assigned to you
            </li>
            <li className="flex min-h-14 items-center gap-3 py-3 text-sm font-medium text-slate-200">
              <ClipboardCheck className="h-5 w-5 shrink-0 text-emerald-400" aria-hidden="true" />
              Complete your pre-trip inspection
            </li>
            <li className="flex min-h-14 items-center gap-3 py-3 text-sm font-medium text-slate-200">
              <TriangleAlert className="h-5 w-5 shrink-0 text-amber-400" aria-hidden="true" />
              Report an incident without assigning fault
            </li>
          </ul>

          {!accessNeedsReview && (
            <>
              <a
                href={workOSLoginUrl}
                className="mt-8 flex min-h-14 w-full items-center justify-center rounded-xl bg-amber-400 px-5 text-base font-bold text-[#081018] shadow-[0_12px_32px_rgba(251,191,36,0.16)] transition-[background-color,transform,box-shadow] duration-150 hover:bg-amber-300 hover:shadow-[0_16px_38px_rgba(251,191,36,0.22)] active:translate-y-px focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300 focus-visible:ring-offset-4 focus-visible:ring-offset-[#081018]"
              >
                Continue to Driver Portal
              </a>
              <p className="mt-4 text-center text-sm leading-6 text-slate-400">
                Access is provided by your fleet manager. Sign in with the email address that received your invitation.
              </p>
            </>
          )}
        </section>

        <p className="text-center text-xs leading-5 text-slate-500">
          Need access or have the wrong equipment? Contact your fleet manager.
        </p>
      </div>
    </main>
  )
}
