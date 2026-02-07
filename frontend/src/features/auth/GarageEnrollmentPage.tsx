import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import api from '../../lib/api'
import { formatUSPhone, isValidUSPhone } from '@/utils/phone'
import { Building2, User, FileText, CheckCircle, ArrowLeft, ArrowRight, Loader2 } from 'lucide-react'

// Step 1: Garage Info
const garageInfoSchema = z.object({
  garage_name: z.string().min(2, 'Garage name must be at least 2 characters').max(255),
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
  owner_password: z.string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Password must contain at least one uppercase letter')
    .regex(/[a-z]/, 'Password must contain at least one lowercase letter')
    .regex(/[0-9]/, 'Password must contain at least one number'),
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

const steps = [
  { id: 1, name: 'Garage Info', icon: Building2 },
  { id: 2, name: 'Business Details', icon: FileText },
  { id: 3, name: 'Owner Account', icon: User },
  { id: 4, name: 'Review', icon: CheckCircle },
]

export default function GarageEnrollmentPage() {
  const [currentStep, setCurrentStep] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)
  
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

  const generateSlug = (name: string) => {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, '')
      .replace(/\s+/g, '-')
      .replace(/-+/g, '-')
      .trim()
  }

  const handleStep1Submit = (data: GarageInfoData) => {
    setFormData(prev => ({ ...prev, ...data }))
    setCurrentStep(2)
  }

  const handleStep2Submit = (data: BusinessDetailsData) => {
    setFormData(prev => ({ ...prev, ...data }))
    setCurrentStep(3)
  }

  const handleStep3Submit = (data: OwnerAccountData) => {
    setFormData(prev => ({ ...prev, ...data }))
    setCurrentStep(4)
  }

  const handleFinalSubmit = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const { confirm_password, ...submitData } = formData as EnrollmentData & { confirm_password: string }
      await api.post('/auth/enroll-garage', submitData)
      setIsSuccess(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Enrollment failed. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  const goBack = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1)
    }
  }

  const getInputClasses = (hasError: boolean) => {
    const baseClasses = "block w-full px-4 py-3 border rounded-lg text-gray-900 bg-white placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors sm:text-sm"
    if (hasError) {
      return `${baseClasses} border-red-400 focus:ring-red-500 focus:border-red-500`
    }
    return `${baseClasses} border-gray-300 focus:ring-emerald-500 focus:border-emerald-500`
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

  // Success screen
  if (isSuccess) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4 py-8 bg-gradient-to-br from-emerald-50 via-teal-50 to-cyan-50">
        <div className="w-full max-w-md text-center space-y-6 p-8 bg-white rounded-xl shadow-xl">
          <div className="w-20 h-20 bg-emerald-100 rounded-full flex items-center justify-center mx-auto">
            <CheckCircle className="w-10 h-10 text-emerald-600" />
          </div>
          <h2 className="text-2xl font-bold text-gray-900">Application Submitted!</h2>
          <p className="text-gray-600">
            Thank you for applying to join Truck Pit Stop. We'll review your application and get back to you within 1-2 business days.
          </p>
          <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 text-left">
            <h3 className="font-semibold text-emerald-800 mb-2">What happens next?</h3>
            <ul className="text-sm text-emerald-700 space-y-1">
              <li>1. We'll verify your business information</li>
              <li>2. You'll receive an email once approved</li>
              <li>3. Log in and start managing your shop!</li>
            </ul>
          </div>
          <Link
            to="/login"
            className="inline-block w-full py-3 px-4 bg-emerald-600 text-white font-semibold rounded-lg hover:bg-emerald-700 transition-colors"
          >
            Back to Login
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-8 bg-gradient-to-br from-emerald-50 via-teal-50 to-cyan-50">
      <div className="w-full max-w-2xl space-y-6 p-6 sm:p-8 bg-white rounded-xl shadow-xl">
        {/* Header */}
        <div className="text-center">
          <h2 className="text-3xl font-extrabold text-gray-900">Join Truck Pit Stop</h2>
          <p className="mt-2 text-gray-600">Register your garage in just a few steps</p>
        </div>

        {/* Progress Steps */}
        <div className="flex justify-between items-center">
          {steps.map((step, index) => (
            <div key={step.id} className="flex items-center">
              <div className={`flex items-center justify-center w-10 h-10 rounded-full border-2 transition-colors ${
                currentStep > step.id
                  ? 'bg-emerald-600 border-emerald-600 text-white'
                  : currentStep === step.id
                  ? 'border-emerald-600 text-emerald-600'
                  : 'border-gray-300 text-gray-400'
              }`}>
                {currentStep > step.id ? (
                  <CheckCircle className="w-5 h-5" />
                ) : (
                  <step.icon className="w-5 h-5" />
                )}
              </div>
              {index < steps.length - 1 && (
                <div className={`hidden sm:block w-16 h-0.5 mx-2 ${
                  currentStep > step.id ? 'bg-emerald-600' : 'bg-gray-300'
                }`} />
              )}
            </div>
          ))}
        </div>

        {/* Step Labels */}
        <div className="flex justify-between text-xs text-gray-500">
          {steps.map((step) => (
            <span key={step.id} className={`${currentStep === step.id ? 'text-emerald-600 font-medium' : ''}`}>
              {step.name}
            </span>
          ))}
        </div>

        {error && (
          <div className="flex items-center gap-3 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
            <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <span className="text-sm">{error}</span>
          </div>
        )}

        {/* Step 1: Garage Info */}
        {currentStep === 1 && (
          <form onSubmit={step1Form.handleSubmit(handleStep1Submit)} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Garage Name <span className="text-red-500">*</span>
              </label>
              <input
                {...step1Form.register('garage_name', {
                  onChange: (e) => {
                    const slug = generateSlug(e.target.value)
                    step1Form.setValue('slug', slug)
                  }
                })}
                type="text"
                className={getInputClasses(!!step1Form.formState.errors.garage_name)}
                placeholder="ABC Truck Repair"
              />
              {step1Form.formState.errors.garage_name && (
                <p className="mt-1 text-sm text-red-600">{step1Form.formState.errors.garage_name.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                URL Slug <span className="text-red-500">*</span>
              </label>
              <div className="flex items-center">
                <span className="text-gray-500 text-sm mr-2">truckpitstop.com/</span>
                <input
                  {...step1Form.register('slug')}
                  type="text"
                  className={getInputClasses(!!step1Form.formState.errors.slug)}
                  placeholder="abc-truck-repair"
                />
              </div>
              {step1Form.formState.errors.slug && (
                <p className="mt-1 text-sm text-red-600">{step1Form.formState.errors.slug.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Address <span className="text-red-500">*</span>
              </label>
              <input
                {...step1Form.register('address')}
                type="text"
                className={getInputClasses(!!step1Form.formState.errors.address)}
                placeholder="123 Main St, City, State 12345"
              />
              {step1Form.formState.errors.address && (
                <p className="mt-1 text-sm text-red-600">{step1Form.formState.errors.address.message}</p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Phone <span className="text-red-500">*</span>
                </label>
                <input
                  {...step1Form.register('phone', {
                    onChange: (e) => step1Form.setValue('phone', formatUSPhone(e.target.value)),
                  })}
                  type="tel"
                  className={getInputClasses(!!step1Form.formState.errors.phone)}
                  placeholder="(555) 123-4567"
                />
                {step1Form.formState.errors.phone && (
                  <p className="mt-1 text-sm text-red-600">{step1Form.formState.errors.phone.message}</p>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Email <span className="text-red-500">*</span>
                </label>
                <input
                  {...step1Form.register('email')}
                  type="email"
                  className={getInputClasses(!!step1Form.formState.errors.email)}
                  placeholder="info@garage.com"
                />
                {step1Form.formState.errors.email && (
                  <p className="mt-1 text-sm text-red-600">{step1Form.formState.errors.email.message}</p>
                )}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Website <span className="text-gray-400">(optional)</span>
              </label>
              <input
                {...step1Form.register('website')}
                type="url"
                className={getInputClasses(!!step1Form.formState.errors.website)}
                placeholder="https://www.yourgarage.com"
              />
              {step1Form.formState.errors.website && (
                <p className="mt-1 text-sm text-red-600">{step1Form.formState.errors.website.message}</p>
              )}
            </div>

            <div className="flex justify-between pt-4">
              <Link to="/login" className="text-gray-600 hover:text-gray-800 flex items-center gap-2">
                <ArrowLeft className="w-4 h-4" /> Back to Login
              </Link>
              <button
                type="submit"
                className="px-6 py-2 bg-emerald-600 text-white font-semibold rounded-lg hover:bg-emerald-700 transition-colors flex items-center gap-2"
              >
                Next <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </form>
        )}

        {/* Step 2: Business Details */}
        {currentStep === 2 && (
          <form onSubmit={step2Form.handleSubmit(handleStep2Submit)} className="space-y-4">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
              <p className="text-sm text-blue-800">
                These fields are optional but help us verify your business faster.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Business License Number <span className="text-gray-400">(optional)</span>
              </label>
              <input
                {...step2Form.register('business_license')}
                type="text"
                className={getInputClasses(!!step2Form.formState.errors.business_license)}
                placeholder="BL-123456"
              />
              {step2Form.formState.errors.business_license && (
                <p className="mt-1 text-sm text-red-600">{step2Form.formState.errors.business_license.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                EIN (Employer Identification Number) <span className="text-gray-400">(optional)</span>
              </label>
              <input
                {...step2Form.register('ein')}
                type="text"
                className={getInputClasses(!!step2Form.formState.errors.ein)}
                placeholder="XX-XXXXXXX"
              />
              <p className="mt-1 text-xs text-gray-500">Format: XX-XXXXXXX (e.g., 12-3456789)</p>
              {step2Form.formState.errors.ein && (
                <p className="mt-1 text-sm text-red-600">{step2Form.formState.errors.ein.message}</p>
              )}
            </div>

            <div className="flex justify-between pt-4">
              <button
                type="button"
                onClick={goBack}
                className="text-gray-600 hover:text-gray-800 flex items-center gap-2"
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>
              <button
                type="submit"
                className="px-6 py-2 bg-emerald-600 text-white font-semibold rounded-lg hover:bg-emerald-700 transition-colors flex items-center gap-2"
              >
                Next <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </form>
        )}

        {/* Step 3: Owner Account */}
        {currentStep === 3 && (
          <form onSubmit={step3Form.handleSubmit(handleStep3Submit)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  First Name <span className="text-red-500">*</span>
                </label>
                <input
                  {...step3Form.register('owner_first_name')}
                  type="text"
                  className={getInputClasses(!!step3Form.formState.errors.owner_first_name)}
                  placeholder="John"
                />
                {step3Form.formState.errors.owner_first_name && (
                  <p className="mt-1 text-sm text-red-600">{step3Form.formState.errors.owner_first_name.message}</p>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Last Name <span className="text-red-500">*</span>
                </label>
                <input
                  {...step3Form.register('owner_last_name')}
                  type="text"
                  className={getInputClasses(!!step3Form.formState.errors.owner_last_name)}
                  placeholder="Doe"
                />
                {step3Form.formState.errors.owner_last_name && (
                  <p className="mt-1 text-sm text-red-600">{step3Form.formState.errors.owner_last_name.message}</p>
                )}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Email <span className="text-red-500">*</span>
              </label>
              <input
                {...step3Form.register('owner_email')}
                type="email"
                className={getInputClasses(!!step3Form.formState.errors.owner_email)}
                placeholder="john@example.com"
              />
              {step3Form.formState.errors.owner_email && (
                <p className="mt-1 text-sm text-red-600">{step3Form.formState.errors.owner_email.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Phone <span className="text-red-500">*</span>
              </label>
              <input
                {...step3Form.register('owner_phone', {
                  onChange: (e) => step3Form.setValue('owner_phone', formatUSPhone(e.target.value)),
                })}
                type="tel"
                className={getInputClasses(!!step3Form.formState.errors.owner_phone)}
                placeholder="(555) 123-4567"
              />
              {step3Form.formState.errors.owner_phone && (
                <p className="mt-1 text-sm text-red-600">{step3Form.formState.errors.owner_phone.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Password <span className="text-red-500">*</span>
              </label>
              <input
                {...step3Form.register('owner_password')}
                type="password"
                className={getInputClasses(!!step3Form.formState.errors.owner_password)}
                placeholder="Min 8 characters"
              />
              {step3Form.watch('owner_password') && (
                <div className="mt-2">
                  <div className="flex gap-1 mb-1">
                    {[...Array(5)].map((_, i) => (
                      <div
                        key={i}
                        className={`h-1.5 flex-1 rounded-full transition-colors ${
                          i < getPasswordStrength(step3Form.watch('owner_password') || '')
                            ? ['bg-red-500', 'bg-orange-500', 'bg-yellow-500', 'bg-lime-500', 'bg-green-500'][
                                getPasswordStrength(step3Form.watch('owner_password') || '') - 1
                              ]
                            : 'bg-gray-200'
                        }`}
                      />
                    ))}
                  </div>
                </div>
              )}
              {step3Form.formState.errors.owner_password && (
                <p className="mt-1 text-sm text-red-600">{step3Form.formState.errors.owner_password.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Confirm Password <span className="text-red-500">*</span>
              </label>
              <input
                {...step3Form.register('confirm_password')}
                type="password"
                className={getInputClasses(!!step3Form.formState.errors.confirm_password)}
                placeholder="Confirm your password"
              />
              {step3Form.formState.errors.confirm_password && (
                <p className="mt-1 text-sm text-red-600">{step3Form.formState.errors.confirm_password.message}</p>
              )}
            </div>

            <div className="flex justify-between pt-4">
              <button
                type="button"
                onClick={goBack}
                className="text-gray-600 hover:text-gray-800 flex items-center gap-2"
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>
              <button
                type="submit"
                className="px-6 py-2 bg-emerald-600 text-white font-semibold rounded-lg hover:bg-emerald-700 transition-colors flex items-center gap-2"
              >
                Review <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </form>
        )}

        {/* Step 4: Review */}
        {currentStep === 4 && (
          <div className="space-y-6">
            <div className="bg-gray-50 rounded-lg p-4 space-y-4">
              <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                <Building2 className="w-5 h-5 text-emerald-600" /> Garage Information
              </h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Name:</span>
                  <p className="font-medium">{formData.garage_name}</p>
                </div>
                <div>
                  <span className="text-gray-500">URL:</span>
                  <p className="font-medium">truckpitstop.com/{formData.slug}</p>
                </div>
                <div className="col-span-2">
                  <span className="text-gray-500">Address:</span>
                  <p className="font-medium">{formData.address}</p>
                </div>
                <div>
                  <span className="text-gray-500">Phone:</span>
                  <p className="font-medium">{formData.phone}</p>
                </div>
                <div>
                  <span className="text-gray-500">Email:</span>
                  <p className="font-medium">{formData.email}</p>
                </div>
                {formData.website && (
                  <div className="col-span-2">
                    <span className="text-gray-500">Website:</span>
                    <p className="font-medium">{formData.website}</p>
                  </div>
                )}
              </div>
            </div>

            {(formData.business_license || formData.ein) && (
              <div className="bg-gray-50 rounded-lg p-4 space-y-4">
                <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                  <FileText className="w-5 h-5 text-emerald-600" /> Business Details
                </h3>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  {formData.business_license && (
                    <div>
                      <span className="text-gray-500">License:</span>
                      <p className="font-medium">{formData.business_license}</p>
                    </div>
                  )}
                  {formData.ein && (
                    <div>
                      <span className="text-gray-500">EIN:</span>
                      <p className="font-medium">{formData.ein}</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="bg-gray-50 rounded-lg p-4 space-y-4">
              <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                <User className="w-5 h-5 text-emerald-600" /> Owner Account
              </h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Name:</span>
                  <p className="font-medium">{formData.owner_first_name} {formData.owner_last_name}</p>
                </div>
                <div>
                  <span className="text-gray-500">Email:</span>
                  <p className="font-medium">{formData.owner_email}</p>
                </div>
                <div>
                  <span className="text-gray-500">Phone:</span>
                  <p className="font-medium">{formData.owner_phone}</p>
                </div>
              </div>
            </div>

            <div className="flex justify-between pt-4">
              <button
                type="button"
                onClick={goBack}
                className="text-gray-600 hover:text-gray-800 flex items-center gap-2"
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>
              <button
                onClick={handleFinalSubmit}
                disabled={isLoading}
                className="px-6 py-2 bg-emerald-600 text-white font-semibold rounded-lg hover:bg-emerald-700 transition-colors flex items-center gap-2 disabled:opacity-50"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" /> Submitting...
                  </>
                ) : (
                  <>
                    Submit Application <CheckCircle className="w-4 h-4" />
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
