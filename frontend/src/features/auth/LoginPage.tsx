import { useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ArrowLeft, Clock3, MessageSquare, Route, Wrench } from 'lucide-react'
import api from '../../lib/api'
import { useAuthStore } from '../../stores/authStore'

const loginSchema = z.object({
  email: z
    .string()
    .min(1, 'Email is required')
    .email('Please enter a valid email address'),
  password: z
    .string()
    .min(1, 'Password is required')
    .min(6, 'Password must be at least 6 characters'),
  remember_me: z.boolean().default(false),
})

type LoginFormData = z.infer<typeof loginSchema>
type ApiErrorShape = {
  response?: {
    data?: {
      detail?: string
    }
  }
}

export default function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { login } = useAuthStore()
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const resetSuccess = searchParams.get('reset') === 'success'
  const defaultEmail = import.meta.env.DEV ? 'truxpitstop@gmail.com' : ''
  const defaultPassword = import.meta.env.DEV ? 'BUse@1534' : ''

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    mode: 'onBlur',
    defaultValues: {
      email: defaultEmail,
      password: defaultPassword,
      remember_me: false,
    },
  })

  const onSubmit = async (data: LoginFormData) => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await api.post('/auth/login', data)
      const { access_token, refresh_token } = response.data

      api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`
      const userResponse = await api.get('/auth/me', {
        headers: { Authorization: `Bearer ${access_token}` },
      })

      login(access_token, refresh_token, userResponse.data)

      if (userResponse.data.role === 'customer') {
        navigate('/portal')
      } else if (userResponse.data.role === 'mechanic') {
        navigate('/mechanic')
      } else {
        navigate('/dashboard')
      }
    } catch (err: unknown) {
      const errorMessage =
        typeof err === 'object' &&
        err !== null &&
        'response' in err &&
        typeof (err as ApiErrorShape).response?.data?.detail === 'string'
          ? (err as ApiErrorShape).response?.data?.detail
          : undefined
      setError(errorMessage || 'Login failed. Please check your credentials.')
    } finally {
      setIsLoading(false)
    }
  }

  const getInputClasses = (fieldName: keyof LoginFormData) => {
    const baseClasses = 'block w-full rounded-xl border bg-zinc-950/70 px-4 py-3 text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:ring-2 transition-colors sm:text-sm'
    if (errors[fieldName]) {
      return `${baseClasses} border-red-500 focus:ring-red-500 focus:border-red-500`
    }
    return `${baseClasses} border-zinc-700 hover:border-zinc-500 focus:border-[var(--accent-500)] focus:ring-[var(--accent-500)]`
  }

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
                <p className="mb-4 inline-flex items-center rounded-full border border-zinc-700 bg-zinc-900/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300">
                  Diesel Bridge Network
                </p>
                <h1 className="text-4xl font-black tracking-tight text-zinc-100">
                  Run your garage.
                  <span className="mt-1 block text-[var(--accent-400)]">Keep trucks moving.</span>
                </h1>
                <p className="mt-4 max-w-md text-zinc-400">
                  Sign in to manage repair orders, communicate with customers, and keep every
                  update in one thread from intake to invoice.
                </p>
              </div>

              <ul className="mt-10 space-y-3 text-sm text-zinc-300">
                <li className="flex items-start gap-3 rounded-xl border border-zinc-800/70 bg-zinc-900/60 p-3">
                  <Route className="mt-0.5 h-4 w-4 text-[var(--accent-400)]" />
                  <span>Dispatch visibility with nearby qualified shop context.</span>
                </li>
                <li className="flex items-start gap-3 rounded-xl border border-zinc-800/70 bg-zinc-900/60 p-3">
                  <MessageSquare className="mt-0.5 h-4 w-4 text-[var(--accent-400)]" />
                  <span>Two-way texting and quote approvals without workflow switching.</span>
                </li>
                <li className="flex items-start gap-3 rounded-xl border border-zinc-800/70 bg-zinc-900/60 p-3">
                  <Clock3 className="mt-0.5 h-4 w-4 text-[var(--accent-400)]" />
                  <span>Live time tracking and progress updates by mechanic and job.</span>
                </li>
              </ul>
            </div>
          </section>

          <section className="rounded-3xl border border-zinc-800/80 bg-zinc-950/75 p-6 shadow-2xl backdrop-blur sm:p-8">
            <div className="mb-6">
              <p className="mb-2 inline-flex items-center gap-2 rounded-full border border-zinc-700/80 bg-zinc-900/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300">
                <Wrench className="h-3.5 w-3.5 text-[var(--accent-400)]" />
                Secure Staff Login
              </p>
              <h2 className="text-3xl font-black tracking-tight text-zinc-100">Welcome back</h2>
              <p className="mt-2 text-sm text-zinc-400">Sign in to your Diesel Bridge Network account.</p>
              <Link
                to="/"
                className="mt-3 inline-flex items-center gap-2 text-sm font-medium text-zinc-300 transition-colors hover:text-[var(--accent-400)] lg:hidden"
              >
                <ArrowLeft className="h-4 w-4" />
                Back to Landing Page
              </Link>
            </div>

            <form className="space-y-5" onSubmit={handleSubmit(onSubmit)}>
          {resetSuccess && (
            <div className="flex items-center gap-3 rounded-xl border border-emerald-700/50 bg-emerald-900/20 px-4 py-3 text-emerald-300">
              <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <span className="text-sm">Password reset successfully! You can now log in with your new password.</span>
            </div>
          )}
          
          {error && (
            <div className="flex items-center gap-3 rounded-xl border border-red-700/50 bg-red-900/20 px-4 py-3 text-red-300">
              <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
              <span className="text-sm">{error}</span>
            </div>
          )}

          <div className="space-y-4">
            {/* Email Field */}
            <div>
              <label htmlFor="email" className="mb-1 block text-sm font-medium text-zinc-300">
                Email Address
              </label>
              <div className="relative">
                <input
                  {...register('email')}
                  type="email"
                  id="email"
                  autoComplete="email"
                  className={getInputClasses('email')}
                  placeholder="you@example.com"
                />
                {errors.email && (
                  <div className="absolute inset-y-0 right-0 flex items-center pr-3">
                    <svg className="w-5 h-5 text-red-500" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                  </div>
                )}
              </div>
              {errors.email && (
                <p className="mt-1.5 flex items-center gap-1 text-sm text-red-400">
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                  {errors.email.message}
                </p>
              )}
            </div>

            {/* Password Field */}
            <div>
              <label htmlFor="password" className="mb-1 block text-sm font-medium text-zinc-300">
                Password
              </label>
              <div className="relative">
                <input
                  {...register('password')}
                  type={showPassword ? 'text' : 'password'}
                  id="password"
                  autoComplete="current-password"
                  className={getInputClasses('password')}
                />
                <div className="absolute inset-y-0 right-0 flex items-center pr-3 gap-2">
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="text-zinc-400 hover:text-zinc-100 focus:outline-none"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? (
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                      </svg>
                    ) : (
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                      </svg>
                    )}
                  </button>
                  {errors.password && (
                    <svg className="w-5 h-5 text-red-500" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                  )}
                </div>
              </div>
              {errors.password && (
                <p className="mt-1.5 flex items-center gap-1 text-sm text-red-400">
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                  {errors.password.message}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between text-sm">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                {...register('remember_me')}
                type="checkbox"
                className="h-4 w-4 cursor-pointer rounded border-zinc-600 bg-zinc-900"
                style={{ accentColor: 'var(--accent-500)' }}
              />
              <span className="text-zinc-300">Remember me</span>
            </label>
            <Link
              to="/forgot-password"
              className="font-medium text-zinc-300 transition-colors hover:text-[var(--accent-400)]"
            >
              Forgot password?
            </Link>
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={isLoading}
              className="flex w-full justify-center rounded-xl border border-transparent px-4 py-3 text-sm font-semibold text-white transition-all disabled:cursor-not-allowed disabled:opacity-50 hover:shadow-[0_0_24px_var(--accent-500)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-500)] focus:ring-offset-2 focus:ring-offset-zinc-950"
              style={{ background: 'linear-gradient(135deg, var(--accent-500) 0%, var(--accent-600) 100%)' }}
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Signing in...
                </span>
              ) : (
                'Sign in'
              )}
            </button>
          </div>

          <div className="text-sm text-center">
            <Link
              to="/register"
              className="font-medium text-zinc-200 transition-colors hover:text-[var(--accent-400)]"
            >
              Don't have an account? Register
            </Link>
          </div>
            </form>
          </section>
        </div>
      </div>
    </div>
  )
}
