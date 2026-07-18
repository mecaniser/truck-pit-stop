import { useEffect, useState } from 'react'
import { Spinner } from '@/components/ui'
import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  CheckCircle,
  FileText,
  ShieldCheck,
  User,
} from 'lucide-react'
import api from '../../lib/api'
import { formatUSPhone, isValidUSPhone } from '@/utils/phone'
import { getPasswordValidationError } from '../../lib/passwordPolicy'
import BrandLogo from '../../components/brand/BrandLogo'
import { applySeo, removeStructuredData } from '../../lib/seo'

// Step 1: Garage Info
const garageInfoSchema = z.object({
  garage_name: z.string().min(2, 'Shop name must be at least 2 characters').max(255),
  slug: z.string()
    .min(2, 'URL slug must be at least 2 characters')
    .max(100)
    .regex(/^[a-z0-9-]+$/, 'URL slug can only contain lowercase letters, numbers, and hyphens'),
  address: z.string().min(5, 'Address must be at least 5 characters').max(500),
  phone: z.string().refine((val) => isValidUSPhone(val), {
    message: 'Please enter a valid phone number',
  }),
  email: z.string().email('Please enter a valid email'),
  website: z.string().url('Please enter a valid URL').optional().or(z.literal('')),
})

// Step 2: Business Details
const businessDetailsSchema = z.object({
  business_license: z.string().max(100).optional().or(z.literal('')),
  ein: z.string()
    .regex(/^(\d{2}-\d{7})?$/, 'EIN must be in format XX-XXXXXXX')
    .optional()
    .or(z.literal('')),
})

// Step 3: Owner Account (base schema without refinement for merging)
const ownerAccountBaseSchema = z.object({
  owner_first_name: z.string().min(1, 'First name is required').max(100),
  owner_last_name: z.string().min(1, 'Last name is required').max(100),
  owner_email: z.string().email('Please enter a valid email'),
  owner_phone: z.string().refine((val) => isValidUSPhone(val), {
    message: 'Please enter a valid phone number',
  }),
  owner_password: z.string().superRefine((value, ctx) => {
    const validationError = getPasswordValidationError(value)
    if (validationError) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: validationError,
      })
    }
  }),
  confirm_password: z.string(),
})

// With password confirmation validation
const ownerAccountSchema = ownerAccountBaseSchema.refine(
  (data) => data.owner_password === data.confirm_password,
  {
    message: "Passwords don't match",
    path: ['confirm_password'],
  }
)

// Combined schema for final submission (without confirm_password)
const enrollmentSchema = garageInfoSchema
  .merge(businessDetailsSchema)
  .merge(ownerAccountBaseSchema.omit({ confirm_password: true }))

type GarageInfoData = z.infer<typeof garageInfoSchema>
type BusinessDetailsData = z.infer<typeof businessDetailsSchema>
type OwnerAccountData = z.infer<typeof ownerAccountSchema>
type EnrollmentData = z.infer<typeof enrollmentSchema>
type ApiErrorShape = {
  response?: {
    data?: {
      detail?: string
    }
  }
}

const steps = [
  { id: 1, name: 'Shop Info', icon: Building2 },
  { id: 2, name: 'Business Details', icon: FileText },
  { id: 3, name: 'Owner Account', icon: User },
  { id: 4, name: 'Review', icon: CheckCircle },
]

export default function GarageEnrollmentPage() {
  const [currentStep, setCurrentStep] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)
  const [showOwnerPassword, setShowOwnerPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [resumeStepAfterGarageEdit, setResumeStepAfterGarageEdit] = useState<number | null>(null)

  // Form data storage
  const [formData, setFormData] = useState<Partial<EnrollmentData & { confirm_password: string }>>({})

  // Step 1 form
  const step1Form = useForm<GarageInfoData>({
    resolver: zodResolver(garageInfoSchema),
    defaultValues: formData,
    mode: 'onBlur',
  })

  // Step 2 form
  const step2Form = useForm<BusinessDetailsData>({
    resolver: zodResolver(businessDetailsSchema),
    defaultValues: formData,
    mode: 'onBlur',
  })

  // Step 3 form
  const step3Form = useForm<OwnerAccountData>({
    resolver: zodResolver(ownerAccountSchema),
    defaultValues: formData,
    mode: 'onBlur',
  })

  const ownerPassword = step3Form.watch('owner_password', '')
  const confirmPassword = step3Form.watch('confirm_password', '')

  const generateSlug = (name: string) => {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, '')
      .replace(/\s+/g, '-')
      .replace(/-+/g, '-')
      .trim()
  }

  const handleStep1Submit = (data: GarageInfoData) => {
    step1Form.clearErrors(['email', 'slug'])
    setError(null)
    const currentOwnerPhone = step3Form.getValues('owner_phone')
    const shouldSyncOwnerPhone = !currentOwnerPhone || currentOwnerPhone === formData.phone

    step3Form.setValue('owner_email', data.email, { shouldValidate: false, shouldDirty: false })
    if (shouldSyncOwnerPhone) {
      step3Form.setValue('owner_phone', data.phone, { shouldValidate: false, shouldDirty: false })
    }

    setFormData((prev) => ({
      ...prev,
      ...data,
      owner_email: data.email,
      owner_phone: shouldSyncOwnerPhone ? data.phone : prev.owner_phone,
    }))

    if (resumeStepAfterGarageEdit === 4) {
      setResumeStepAfterGarageEdit(null)
      setCurrentStep(4)
      return
    }

    setCurrentStep(2)
  }

  const handleStep2Submit = (data: BusinessDetailsData) => {
    setFormData((prev) => ({ ...prev, ...data }))
    setCurrentStep(3)
  }

  const handleStep3Submit = (data: OwnerAccountData) => {
    setFormData((prev) => ({ ...prev, ...data }))
    setCurrentStep(4)
  }

  const handleFinalSubmit = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const finalData = formData as EnrollmentData & { confirm_password: string }
      const submitData: EnrollmentData = {
        garage_name: finalData.garage_name,
        slug: finalData.slug,
        address: finalData.address,
        phone: finalData.phone,
        email: finalData.email,
        website: finalData.website,
        business_license: finalData.business_license,
        ein: finalData.ein,
        owner_first_name: finalData.owner_first_name,
        owner_last_name: finalData.owner_last_name,
        owner_email: finalData.owner_email,
        owner_phone: finalData.owner_phone,
        owner_password: finalData.owner_password,
      }
      await api.post('/auth/enroll-garage', submitData)
      setIsSuccess(true)
    } catch (err: unknown) {
      const detail =
        typeof err === 'object' &&
        err !== null &&
        'response' in err &&
        typeof (err as ApiErrorShape).response?.data?.detail === 'string'
          ? (err as ApiErrorShape).response?.data?.detail ?? 'Enrollment failed. Please try again.'
          : 'Enrollment failed. Please try again.'

      if (detail.includes('This email is already registered')) {
        setResumeStepAfterGarageEdit(4)
        setCurrentStep(1)
        step1Form.setError('email', {
          type: 'server',
          message: 'This email is already registered. Use a different business email.',
        })
        setError('Business and owner login email must match. Please update email in Shop Info.')
      } else if (detail.includes('shop URL slug is already taken')) {
        setResumeStepAfterGarageEdit(4)
        setCurrentStep(1)
        step1Form.setError('slug', {
          type: 'server',
          message: 'This URL slug is already taken. Please choose another.',
        })
        setError('Shop URL slug is already taken. Please update it in Shop Info.')
      } else {
        setError(detail)
      }
    } finally {
      setIsLoading(false)
    }
  }

  const goBack = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1)
    }
  }

  const getInputClasses = (hasError: boolean, readOnly = false) => {
    const baseClasses = 'block w-full rounded-xl border bg-zinc-950/70 px-4 py-3 text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:ring-2 transition-colors sm:text-sm'
    const readOnlyClasses = readOnly ? 'cursor-not-allowed bg-zinc-900/60 text-zinc-400' : ''
    if (hasError) {
      return `${baseClasses} ${readOnlyClasses} border-red-500 focus:ring-red-500 focus:border-red-500`
    }
    return `${baseClasses} ${readOnlyClasses} border-zinc-700 hover:border-zinc-500 focus:border-[var(--accent-500)] focus:ring-[var(--accent-500)]`
  }

  const getPasswordStrength = (pwd: string) => {
    let strength = 0
    if (pwd.length >= 8) strength++
    if (/[A-Z]/.test(pwd)) strength++
    if (/[a-z]/.test(pwd)) strength++
    if (/[0-9]/.test(pwd)) strength++
    if (/[^A-Za-z0-9]/.test(pwd)) strength++
    return strength
  }

  const passwordStrength = getPasswordStrength(ownerPassword)
  const passwordsMatch = confirmPassword.length > 0 && ownerPassword === confirmPassword
  const progressPercent = ((currentStep - 1) / (steps.length - 1)) * 100

  useEffect(() => {
    const pageTitle = 'Apply for Founding Shop Access | DieselBridge Network'
    const pageDescription = 'Apply to join DieselBridge Network as a founding shop and launch your shop workspace after approval.'
    const siteOrigin = (import.meta.env.VITE_SITE_URL || window.location.origin).replace(/\/+$/, '')
    const canonicalUrl = `${siteOrigin}/enroll`
    const ogImage = `${siteOrigin}/DB_bridge_logo_favi_figma_public_B.png`
    const structuredDataId = 'seo-jsonld-enroll'

    applySeo({
      title: pageTitle,
      description: pageDescription,
      canonicalUrl,
      robots: 'index, follow',
      ogUrl: canonicalUrl,
      ogImage,
      ogSiteName: 'Diesel Bridge Network',
      twitterImage: ogImage,
      structuredData: {
        id: structuredDataId,
        data: {
          '@context': 'https://schema.org',
          '@type': 'WebPage',
          url: canonicalUrl,
          name: pageTitle,
          description: pageDescription,
        },
      },
    })

    return () => {
      removeStructuredData(structuredDataId)
    }
  }, [])

  const primaryButtonClasses =
    'inline-flex items-center justify-center gap-2 rounded-xl border border-transparent px-5 py-2.5 text-sm font-semibold text-white transition-all disabled:cursor-not-allowed disabled:opacity-50 hover:shadow-[0_0_24px_var(--accent-500)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-500)] focus:ring-offset-2 focus:ring-offset-zinc-950'
  const backButtonClasses =
    'inline-flex items-center gap-2 text-sm font-medium text-zinc-300 transition-colors hover:text-[var(--accent-400)]'

  // Success screen
  if (isSuccess) {
    return (
      <div className="relative min-h-screen overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(6,182,212,0.22),transparent_36%),radial-gradient(circle_at_85%_15%,rgba(79,70,229,0.2),transparent_34%),radial-gradient(circle_at_70%_80%,rgba(14,116,144,0.16),transparent_44%)]" />

        <div className="relative mx-auto flex min-h-screen w-full max-w-6xl flex-col justify-center px-4 py-8 sm:py-10">
          <Link
            to="/"
            className="mb-5 inline-flex items-center gap-2 self-start rounded-full border border-zinc-700/80 bg-zinc-900/70 px-4 py-2 text-sm font-medium text-zinc-200 backdrop-blur transition-colors hover:border-zinc-500 hover:text-[var(--accent-400)] lg:absolute lg:left-4 lg:top-6 lg:mb-0"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Landing Page
          </Link>

          <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
            <section className="hidden overflow-hidden rounded-3xl border border-zinc-800/80 bg-zinc-950/65 p-8 shadow-2xl lg:block">
              <div className="flex h-full flex-col justify-between">
                <div>
                  <div className="mb-4">
                    <BrandLogo alt="Diesel Bridge Network" variant="public" className="h-8 w-auto" />
                  </div>
                  <p className="mb-4 inline-flex items-center rounded-full border border-zinc-700 bg-zinc-900/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300">
                    Founding Shop Access
                  </p>
                  <h2 className="text-4xl font-black tracking-tight text-zinc-100">
                    Application received.
                    <span className="mt-1 block text-[var(--accent-400)]">You are in review.</span>
                  </h2>
                  <p className="mt-4 max-w-md text-zinc-400">
                    We review each shop application for readiness and fit, then send owner onboarding instructions by email.
                  </p>
                </div>

                <ul className="mt-10 space-y-3 text-sm text-zinc-300">
                  <li className="flex items-start gap-3 rounded-xl border border-zinc-800/70 bg-zinc-900/60 p-3">
                    <CheckCircle className="mt-0.5 h-4 w-4 text-[var(--accent-400)]" />
                    <span>Business details are validated for account integrity and setup quality.</span>
                  </li>
                  <li className="flex items-start gap-3 rounded-xl border border-zinc-800/70 bg-zinc-900/60 p-3">
                    <ShieldCheck className="mt-0.5 h-4 w-4 text-[var(--accent-400)]" />
                    <span>Owner credentials stay private. Staff will never request your password.</span>
                  </li>
                </ul>
              </div>
            </section>

            <section className="rounded-3xl border border-zinc-800/80 bg-zinc-950/75 p-6 shadow-2xl backdrop-blur sm:p-8">
              <div className="mb-6">
                <div className="mb-3 lg:hidden">
                  <BrandLogo alt="Diesel Bridge Network" variant="public" className="h-8 w-auto" />
                </div>
                <p className="mb-2 inline-flex items-center gap-2 rounded-full border border-emerald-700/70 bg-emerald-900/20 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-emerald-300">
                  <CheckCircle className="h-3.5 w-3.5" />
                  Submitted
                </p>
                <h1 className="text-3xl font-black tracking-tight text-zinc-100">Application Submitted</h1>
                <p className="mt-2 text-sm text-zinc-400">
                  Thank you for applying to DieselBridge Network. We typically respond within 1-2 business days.
                </p>
              </div>

              <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-4">
                <h2 className="text-sm font-semibold uppercase tracking-[0.1em] text-zinc-300">What Happens Next</h2>
                <ol className="mt-3 space-y-2 text-sm text-zinc-300">
                  <li className="flex items-start gap-2">
                    <span className="mt-0.5 h-5 w-5 rounded-full bg-zinc-800 text-center text-xs leading-5 text-zinc-200">1</span>
                    We verify your shop and owner details.
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-0.5 h-5 w-5 rounded-full bg-zinc-800 text-center text-xs leading-5 text-zinc-200">2</span>
                    You receive an approval status email.
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-0.5 h-5 w-5 rounded-full bg-zinc-800 text-center text-xs leading-5 text-zinc-200">3</span>
                    You sign in and launch your shop workspace.
                  </li>
                </ol>
              </div>

              <div className="mt-6">
                <Link
                  to="/login"
                  className={`${primaryButtonClasses} w-full`}
                  style={{ background: 'linear-gradient(135deg, var(--accent-500) 0%, var(--accent-600) 100%)' }}
                >
                  Back to Login
                </Link>
              </div>
            </section>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(6,182,212,0.22),transparent_36%),radial-gradient(circle_at_85%_15%,rgba(79,70,229,0.2),transparent_34%),radial-gradient(circle_at_70%_80%,rgba(14,116,144,0.16),transparent_44%)]" />

      <a
        href="#enroll-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-white focus:px-4 focus:py-2 focus:text-slate-950"
      >
        Skip to enrollment form
      </a>

      <div className="relative mx-auto flex min-h-screen w-full max-w-6xl flex-col justify-center px-4 py-8 sm:py-10">
        <Link
          to="/"
          className="mb-5 inline-flex items-center gap-2 self-start rounded-full border border-zinc-700/80 bg-zinc-900/70 px-4 py-2 text-sm font-medium text-zinc-200 backdrop-blur transition-colors hover:border-zinc-500 hover:text-[var(--accent-400)] lg:absolute lg:left-4 lg:top-6 lg:mb-0"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Landing Page
        </Link>

        <main id="enroll-main" className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
          <section className="hidden overflow-hidden rounded-3xl border border-zinc-800/80 bg-zinc-950/65 p-8 shadow-2xl lg:block">
            <div className="flex h-full flex-col justify-between">
              <div>
                <div className="mb-4">
                  <BrandLogo alt="Diesel Bridge Network" variant="public" className="h-8 w-auto" />
                </div>
                <p className="mb-4 inline-flex items-center rounded-full border border-zinc-700 bg-zinc-900/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300">
                  Founding Shop Access
                </p>
                <h2 className="text-4xl font-black tracking-tight text-zinc-100">
                  Launch your shop.
                  <span className="mt-1 block text-[var(--accent-400)]">Join the network.</span>
                </h2>
                <p className="mt-4 max-w-md text-zinc-400">
                  Complete a short four-step application. Once approved, your owner account is ready to sign in and start operations.
                </p>
              </div>

              <ul className="mt-10 space-y-3 text-sm text-zinc-300">
                <li className="flex items-start gap-3 rounded-xl border border-zinc-800/70 bg-zinc-900/60 p-3">
                  <Building2 className="mt-0.5 h-4 w-4 text-[var(--accent-400)]" />
                  <span>Shop profile setup with URL, contact data, and business verification details.</span>
                </li>
                <li className="flex items-start gap-3 rounded-xl border border-zinc-800/70 bg-zinc-900/60 p-3">
                  <ShieldCheck className="mt-0.5 h-4 w-4 text-[var(--accent-400)]" />
                  <span>Owner account credentials are created securely and tied to your shop workspace.</span>
                </li>
                <li className="flex items-start gap-3 rounded-xl border border-zinc-800/70 bg-zinc-900/60 p-3">
                  <CheckCircle className="mt-0.5 h-4 w-4 text-[var(--accent-400)]" />
                  <span>Review before submit so your application is accurate on first pass.</span>
                </li>
              </ul>
            </div>
          </section>

          <section className="rounded-3xl border border-zinc-800/80 bg-zinc-950/75 p-6 shadow-2xl backdrop-blur sm:p-8">
            <div className="mb-6">
              <div className="mb-3 lg:hidden">
                <BrandLogo alt="Diesel Bridge Network" variant="public" className="h-8 w-auto" />
              </div>
              <p className="mb-2 inline-flex items-center gap-2 rounded-full border border-zinc-700/80 bg-zinc-900/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300">
                <Building2 className="h-3.5 w-3.5 text-[var(--accent-400)]" />
                Shop Enrollment
              </p>
              <h1 className="text-3xl font-black tracking-tight text-zinc-100">Apply for Founding Shop Access</h1>
              <p className="mt-2 text-sm text-zinc-400">Register your shop in four guided steps.</p>
            </div>

            <div className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900/55 p-4">
              <div className="grid grid-cols-4 gap-2">
                {steps.map((step) => {
                  const isComplete = currentStep > step.id
                  const isCurrent = currentStep === step.id
                  return (
                    <div key={step.id} className="flex flex-col items-center gap-2 text-center">
                      <div
                        className={`flex h-9 w-9 items-center justify-center rounded-full border text-xs font-semibold transition-colors ${
                          isComplete
                            ? 'border-[var(--accent-500)] bg-[var(--accent-500)] text-white'
                            : isCurrent
                            ? 'border-[var(--accent-500)] text-[var(--accent-400)]'
                            : 'border-zinc-700 text-zinc-500'
                        }`}
                      >
                        {isComplete ? <CheckCircle className="h-4 w-4" /> : <step.icon className="h-4 w-4" />}
                      </div>
                      <span className={`text-[11px] sm:text-xs ${isCurrent ? 'text-zinc-200' : 'text-zinc-500'}`}>
                        {step.name}
                      </span>
                    </div>
                  )
                })}
              </div>
              <div className="mt-3 h-1 overflow-hidden rounded-full bg-zinc-800">
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${progressPercent}%`,
                    background: 'linear-gradient(135deg, var(--accent-500) 0%, var(--accent-600) 100%)',
                  }}
                />
              </div>
            </div>

            {error && (
              <div className="mb-5 flex items-center gap-3 rounded-xl border border-red-700/50 bg-red-900/20 px-4 py-3 text-red-300">
                <svg className="h-5 w-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
                <span className="text-sm">{error}</span>
              </div>
            )}

            {/* Step 1: Shop Info */}
            {currentStep === 1 && (
              <form onSubmit={step1Form.handleSubmit(handleStep1Submit)} className="space-y-4">
                <div>
                  <label htmlFor="garage_name" className="mb-1 block text-sm font-medium text-zinc-300">
                    Shop Name <span className="text-red-400">*</span>
                  </label>
                  <input
                    {...step1Form.register('garage_name', {
                      onChange: (e) => {
                        const slug = generateSlug(e.target.value)
                        step1Form.setValue('slug', slug)
                      },
                    })}
                    type="text"
                    id="garage_name"
                    className={getInputClasses(!!step1Form.formState.errors.garage_name)}
                    placeholder="ABC Truck Repair"
                  />
                  {step1Form.formState.errors.garage_name && (
                    <p className="mt-1.5 text-sm text-red-400">{step1Form.formState.errors.garage_name.message}</p>
                  )}
                </div>

                <div>
                  <label htmlFor="slug" className="mb-1 block text-sm font-medium text-zinc-300">
                    URL Slug <span className="text-red-400">*</span>
                  </label>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-zinc-500">dieselbridge.com/</span>
                    <input
                      {...step1Form.register('slug')}
                      type="text"
                      id="slug"
                      className={getInputClasses(!!step1Form.formState.errors.slug)}
                      placeholder="abc-truck-repair"
                    />
                  </div>
                  {step1Form.formState.errors.slug && (
                    <p className="mt-1.5 text-sm text-red-400">{step1Form.formState.errors.slug.message}</p>
                  )}
                </div>

                <div>
                  <label htmlFor="address" className="mb-1 block text-sm font-medium text-zinc-300">
                    Address <span className="text-red-400">*</span>
                  </label>
                  <input
                    {...step1Form.register('address')}
                    type="text"
                    id="address"
                    className={getInputClasses(!!step1Form.formState.errors.address)}
                    placeholder="123 Main St, City, State 12345"
                  />
                  {step1Form.formState.errors.address && (
                    <p className="mt-1.5 text-sm text-red-400">{step1Form.formState.errors.address.message}</p>
                  )}
                </div>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="phone" className="mb-1 block text-sm font-medium text-zinc-300">
                      Phone <span className="text-red-400">*</span>
                    </label>
                    <input
                      {...step1Form.register('phone', {
                        onChange: (e) => step1Form.setValue('phone', formatUSPhone(e.target.value)),
                      })}
                      type="tel"
                      id="phone"
                      autoComplete="tel"
                      className={getInputClasses(!!step1Form.formState.errors.phone)}
                      placeholder="(555) 123-4567"
                    />
                    {step1Form.formState.errors.phone && (
                      <p className="mt-1.5 text-sm text-red-400">{step1Form.formState.errors.phone.message}</p>
                    )}
                  </div>
                  <div>
                    <label htmlFor="email" className="mb-1 block text-sm font-medium text-zinc-300">
                      Business Contact Email <span className="text-red-400">*</span>
                    </label>
                    <input
                      {...step1Form.register('email')}
                      type="email"
                      id="email"
                      autoComplete="email"
                      className={getInputClasses(!!step1Form.formState.errors.email)}
                      placeholder="info@shop.com"
                    />
                    {step1Form.formState.errors.email && (
                      <p className="mt-1.5 text-sm text-red-400">{step1Form.formState.errors.email.message}</p>
                    )}
                  </div>
                </div>

                <div>
                  <label htmlFor="website" className="mb-1 block text-sm font-medium text-zinc-300">
                    Website <span className="text-zinc-500">(optional)</span>
                  </label>
                  <input
                    {...step1Form.register('website')}
                    type="url"
                    id="website"
                    className={getInputClasses(!!step1Form.formState.errors.website)}
                    placeholder="https://www.yourshop.com"
                  />
                  {step1Form.formState.errors.website && (
                    <p className="mt-1.5 text-sm text-red-400">{step1Form.formState.errors.website.message}</p>
                  )}
                </div>

                <div className="flex items-center justify-between pt-4">
                  <Link to="/login" className={backButtonClasses}>
                    <ArrowLeft className="h-4 w-4" />
                    Back to Login
                  </Link>
                  <button
                    type="submit"
                    className={primaryButtonClasses}
                    style={{ background: 'linear-gradient(135deg, var(--accent-500) 0%, var(--accent-600) 100%)' }}
                  >
                    {resumeStepAfterGarageEdit === 4 ? 'Return to Review' : 'Next'}
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </div>
              </form>
            )}

            {/* Step 2: Business Details */}
            {currentStep === 2 && (
              <form onSubmit={step2Form.handleSubmit(handleStep2Submit)} className="space-y-4">
                <div className="rounded-xl border border-cyan-800/50 bg-cyan-900/15 p-4 text-sm text-cyan-200">
                  These fields are optional, but they can speed up business verification.
                </div>

                <div>
                  <label htmlFor="business_license" className="mb-1 block text-sm font-medium text-zinc-300">
                    Business License Number <span className="text-zinc-500">(optional)</span>
                  </label>
                  <input
                    {...step2Form.register('business_license')}
                    type="text"
                    id="business_license"
                    className={getInputClasses(!!step2Form.formState.errors.business_license)}
                    placeholder="BL-123456"
                  />
                  {step2Form.formState.errors.business_license && (
                    <p className="mt-1.5 text-sm text-red-400">{step2Form.formState.errors.business_license.message}</p>
                  )}
                </div>

                <div>
                  <label htmlFor="ein" className="mb-1 block text-sm font-medium text-zinc-300">
                    EIN (Employer Identification Number) <span className="text-zinc-500">(optional)</span>
                  </label>
                  <input
                    {...step2Form.register('ein')}
                    type="text"
                    id="ein"
                    className={getInputClasses(!!step2Form.formState.errors.ein)}
                    placeholder="XX-XXXXXXX"
                  />
                  <p className="mt-1 text-xs text-zinc-500">Format: XX-XXXXXXX (example: 12-3456789)</p>
                  {step2Form.formState.errors.ein && (
                    <p className="mt-1.5 text-sm text-red-400">{step2Form.formState.errors.ein.message}</p>
                  )}
                </div>

                <div className="flex items-center justify-between pt-4">
                  <button type="button" onClick={goBack} className={backButtonClasses}>
                    <ArrowLeft className="h-4 w-4" />
                    Back
                  </button>
                  <button
                    type="submit"
                    className={primaryButtonClasses}
                    style={{ background: 'linear-gradient(135deg, var(--accent-500) 0%, var(--accent-600) 100%)' }}
                  >
                    Next
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </div>
              </form>
            )}

            {/* Step 3: Owner Account */}
            {currentStep === 3 && (
              <form onSubmit={step3Form.handleSubmit(handleStep3Submit)} className="space-y-4">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="owner_first_name" className="mb-1 block text-sm font-medium text-zinc-300">
                      First Name <span className="text-red-400">*</span>
                    </label>
                    <input
                      {...step3Form.register('owner_first_name')}
                      type="text"
                      id="owner_first_name"
                      className={getInputClasses(!!step3Form.formState.errors.owner_first_name)}
                      placeholder="John"
                    />
                    {step3Form.formState.errors.owner_first_name && (
                      <p className="mt-1.5 text-sm text-red-400">{step3Form.formState.errors.owner_first_name.message}</p>
                    )}
                  </div>
                  <div>
                    <label htmlFor="owner_last_name" className="mb-1 block text-sm font-medium text-zinc-300">
                      Last Name <span className="text-red-400">*</span>
                    </label>
                    <input
                      {...step3Form.register('owner_last_name')}
                      type="text"
                      id="owner_last_name"
                      className={getInputClasses(!!step3Form.formState.errors.owner_last_name)}
                      placeholder="Doe"
                    />
                    {step3Form.formState.errors.owner_last_name && (
                      <p className="mt-1.5 text-sm text-red-400">{step3Form.formState.errors.owner_last_name.message}</p>
                    )}
                  </div>
                </div>

                <div>
                  <label htmlFor="owner_email" className="mb-1 block text-sm font-medium text-zinc-300">
                    Owner Login Email <span className="text-red-400">*</span>
                  </label>
                  <p className="mb-1 text-xs text-zinc-500">Uses the same email as Business Contact Email.</p>
                  <input
                    {...step3Form.register('owner_email')}
                    type="email"
                    id="owner_email"
                    readOnly
                    className={getInputClasses(!!step3Form.formState.errors.owner_email, true)}
                    placeholder="john@example.com"
                  />
                  {step3Form.formState.errors.owner_email && (
                    <p className="mt-1.5 text-sm text-red-400">{step3Form.formState.errors.owner_email.message}</p>
                  )}
                </div>

                <div>
                  <label htmlFor="owner_phone" className="mb-1 block text-sm font-medium text-zinc-300">
                    Phone <span className="text-red-400">*</span>
                  </label>
                  <p className="mb-1 text-xs text-zinc-500">Prefilled from Shop Info. Change only if needed.</p>
                  <input
                    {...step3Form.register('owner_phone', {
                      onChange: (e) => step3Form.setValue('owner_phone', formatUSPhone(e.target.value)),
                    })}
                    type="tel"
                    id="owner_phone"
                    className={getInputClasses(!!step3Form.formState.errors.owner_phone)}
                    placeholder="(555) 123-4567"
                  />
                  {step3Form.formState.errors.owner_phone && (
                    <p className="mt-1.5 text-sm text-red-400">{step3Form.formState.errors.owner_phone.message}</p>
                  )}
                </div>

                <div>
                  <label htmlFor="owner_password" className="mb-1 block text-sm font-medium text-zinc-300">
                    Password <span className="text-red-400">*</span>
                  </label>
                  <div className="relative">
                    <input
                      {...step3Form.register('owner_password')}
                      type={showOwnerPassword ? 'text' : 'password'}
                      id="owner_password"
                      className={getInputClasses(!!step3Form.formState.errors.owner_password)}
                      placeholder="8+ chars, upper/lower/digit/special"
                    />
                    <button
                      type="button"
                      onClick={() => setShowOwnerPassword((prev) => !prev)}
                      className="absolute inset-y-0 right-0 flex items-center pr-3 text-zinc-400 hover:text-zinc-200 focus:outline-none"
                      aria-label={showOwnerPassword ? 'Hide password' : 'Show password'}
                    >
                      {showOwnerPassword ? (
                        <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                        </svg>
                      ) : (
                        <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                        </svg>
                      )}
                    </button>
                  </div>
                  {ownerPassword && (
                    <div className="mt-2">
                      <div className="mb-1 flex gap-1">
                        {[...Array(5)].map((_, i) => (
                          <div
                            key={i}
                            className={`h-1.5 flex-1 rounded-full transition-colors ${
                              i < passwordStrength
                                ? ['bg-red-500', 'bg-orange-500', 'bg-yellow-500', 'bg-lime-500', 'bg-emerald-500'][passwordStrength - 1]
                                : 'bg-zinc-700'
                            }`}
                          />
                        ))}
                      </div>
                    </div>
                  )}
                  {step3Form.formState.errors.owner_password && (
                    <p className="mt-1.5 text-sm text-red-400">{step3Form.formState.errors.owner_password.message}</p>
                  )}
                </div>

                <div>
                  <label htmlFor="confirm_password" className="mb-1 block text-sm font-medium text-zinc-300">
                    Confirm Password <span className="text-red-400">*</span>
                  </label>
                  <div className="relative">
                    <input
                      {...step3Form.register('confirm_password')}
                      type={showConfirmPassword ? 'text' : 'password'}
                      id="confirm_password"
                      className={getInputClasses(!!step3Form.formState.errors.confirm_password)}
                      placeholder="Confirm your password"
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword((prev) => !prev)}
                      className="absolute inset-y-0 right-0 flex items-center pr-3 text-zinc-400 hover:text-zinc-200 focus:outline-none"
                      aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
                    >
                      {showConfirmPassword ? (
                        <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                        </svg>
                      ) : (
                        <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                        </svg>
                      )}
                    </button>
                  </div>
                  {step3Form.formState.errors.confirm_password && (
                    <p className="mt-1.5 text-sm text-red-400">{step3Form.formState.errors.confirm_password.message}</p>
                  )}
                  {passwordsMatch && !step3Form.formState.errors.confirm_password && (
                    <p className="mt-1.5 text-sm text-emerald-400">Passwords match.</p>
                  )}
                </div>

                <div className="flex items-center justify-between pt-4">
                  <button type="button" onClick={goBack} className={backButtonClasses}>
                    <ArrowLeft className="h-4 w-4" />
                    Back
                  </button>
                  <button
                    type="submit"
                    className={primaryButtonClasses}
                    style={{ background: 'linear-gradient(135deg, var(--accent-500) 0%, var(--accent-600) 100%)' }}
                  >
                    Review
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </div>
              </form>
            )}

            {/* Step 4: Review */}
            {currentStep === 4 && (
              <div className="space-y-4">
                <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.1em] text-zinc-300">
                      <Building2 className="h-4 w-4 text-[var(--accent-400)]" />
                      Shop Information
                    </h2>
                    <button
                      type="button"
                      onClick={() => {
                        setResumeStepAfterGarageEdit(4)
                        setCurrentStep(1)
                      }}
                      className="text-xs font-medium text-zinc-300 underline transition-colors hover:text-[var(--accent-400)]"
                    >
                      Edit
                    </button>
                  </div>
                  <div className="grid grid-cols-1 gap-3 text-sm text-zinc-300 sm:grid-cols-2">
                    <div>
                      <span className="text-zinc-500">Name</span>
                      <p className="font-medium text-zinc-100">{formData.garage_name}</p>
                    </div>
                    <div>
                      <span className="text-zinc-500">URL</span>
                      <p className="font-medium text-zinc-100">dieselbridge.com/{formData.slug}</p>
                    </div>
                    <div className="sm:col-span-2">
                      <span className="text-zinc-500">Address</span>
                      <p className="font-medium text-zinc-100">{formData.address}</p>
                    </div>
                    <div className="sm:col-span-2">
                      <span className="text-zinc-500">Phone</span>
                      <p className="font-medium text-zinc-100">{formData.phone}</p>
                      <div className="mt-2">
                        <span className="text-zinc-500">Business Email</span>
                        <p className="break-all font-medium text-zinc-100">{formData.email}</p>
                      </div>
                    </div>
                    {formData.website && (
                      <div className="sm:col-span-2">
                        <span className="text-zinc-500">Website</span>
                        <p className="font-medium text-zinc-100">{formData.website}</p>
                      </div>
                    )}
                  </div>
                </div>

                {(formData.business_license || formData.ein) && (
                  <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-4">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.1em] text-zinc-300">
                        <FileText className="h-4 w-4 text-[var(--accent-400)]" />
                        Business Details
                      </h2>
                      <button
                        type="button"
                        onClick={() => setCurrentStep(2)}
                        className="text-xs font-medium text-zinc-300 underline transition-colors hover:text-[var(--accent-400)]"
                      >
                        Edit
                      </button>
                    </div>
                    <div className="grid grid-cols-1 gap-3 text-sm text-zinc-300 sm:grid-cols-2">
                      {formData.business_license && (
                        <div>
                          <span className="text-zinc-500">License</span>
                          <p className="font-medium text-zinc-100">{formData.business_license}</p>
                        </div>
                      )}
                      {formData.ein && (
                        <div>
                          <span className="text-zinc-500">EIN</span>
                          <p className="font-medium text-zinc-100">{formData.ein}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.1em] text-zinc-300">
                      <User className="h-4 w-4 text-[var(--accent-400)]" />
                      Owner Account
                    </h2>
                    <button
                      type="button"
                      onClick={() => setCurrentStep(3)}
                      className="text-xs font-medium text-zinc-300 underline transition-colors hover:text-[var(--accent-400)]"
                    >
                      Edit
                    </button>
                  </div>
                  <div className="grid grid-cols-1 gap-3 text-sm text-zinc-300 sm:grid-cols-2">
                    <div className="sm:col-span-2">
                      <span className="text-zinc-500">Name</span>
                      <p className="font-medium text-zinc-100">
                        {formData.owner_first_name} {formData.owner_last_name}
                      </p>
                      <div className="mt-2">
                        <span className="text-zinc-500">Owner Login Email</span>
                        <p className="break-all font-medium text-zinc-100">{formData.owner_email}</p>
                      </div>
                    </div>
                    <div>
                      <span className="text-zinc-500">Phone</span>
                      <p className="font-medium text-zinc-100">{formData.owner_phone}</p>
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-zinc-800/70 bg-zinc-900/55 px-3 py-2 text-xs text-zinc-400">
                  Review details carefully before submitting. DieselBridge staff will never ask for your password.
                </div>

                <div className="flex items-center justify-between pt-2">
                  <button type="button" onClick={goBack} className={backButtonClasses}>
                    <ArrowLeft className="h-4 w-4" />
                    Back
                  </button>
                  <button
                    onClick={handleFinalSubmit}
                    disabled={isLoading}
                    className={primaryButtonClasses}
                    style={{ background: 'linear-gradient(135deg, var(--accent-500) 0%, var(--accent-600) 100%)' }}
                  >
                    {isLoading ? (
                      <>
                        <Spinner size="xs" />
                        Submitting...
                      </>
                    ) : (
                      <>
                        Submit Application
                        <CheckCircle className="h-4 w-4" />
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </section>
        </main>
      </div>
    </div>
  )
}
