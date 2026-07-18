import { useState } from 'react'
import { Spinner } from '@/components/ui'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ArrowLeft } from 'lucide-react'
import api from '../../lib/api'
import { Link } from 'react-router-dom'
import BrandLogo from '../../components/brand/BrandLogo'

const forgotPasswordSchema = z.object({
  email: z
    .string()
    .min(1, 'Email is required')
    .email('Please enter a valid email address'),
})

type ForgotPasswordFormData = z.infer<typeof forgotPasswordSchema>

export default function ForgotPasswordPage() {
  const [isLoading, setIsLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ForgotPasswordFormData>({
    resolver: zodResolver(forgotPasswordSchema),
    mode: 'onBlur',
  })

  const onSubmit = async (data: ForgotPasswordFormData) => {
    setIsLoading(true)
    setError(null)

    try {
      await api.post('/auth/forgot-password', data)
      setSuccess(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to send reset email. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(6,182,212,0.22),transparent_36%),radial-gradient(circle_at_85%_15%,rgba(79,70,229,0.2),transparent_34%),radial-gradient(circle_at_70%_80%,rgba(14,116,144,0.16),transparent_44%)]" />

      <div className="relative mx-auto flex min-h-screen w-full max-w-md flex-col items-center justify-center px-4 py-8">
        <Link
          to="/login"
          className="mb-6 inline-flex items-center gap-2 self-start rounded-full border border-zinc-700/80 bg-zinc-900/70 px-4 py-2 text-sm font-medium text-zinc-200 backdrop-blur transition-colors hover:border-zinc-500 hover:text-[var(--accent-400)]"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Login
        </Link>

        <div className="w-full rounded-3xl border border-zinc-800/80 bg-zinc-950/75 p-6 shadow-2xl backdrop-blur sm:p-8">
          <div className="mb-6">
            <div className="mb-4">
              <BrandLogo alt="Diesel Bridge Network" variant="admin" className="h-8 w-auto" />
            </div>
            <h2 className="text-3xl font-black tracking-tight text-zinc-100">Reset Password</h2>
            <p className="mt-2 text-sm text-zinc-400">
              Enter your email address and we'll send you a link to reset your password.
            </p>
          </div>

          {success ? (
            <div className="space-y-4">
              <div className="flex items-center gap-3 rounded-xl border border-emerald-700/50 bg-emerald-900/20 px-4 py-3 text-emerald-300">
                <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
                <span className="text-sm">
                  Check your email for a password reset link. It will expire in 1 hour.
                </span>
              </div>
              <Link
                to="/login"
                className="flex w-full justify-center rounded-xl border border-transparent px-4 py-3 text-sm font-semibold text-white transition-all hover:shadow-[0_0_24px_var(--accent-500)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-500)] focus:ring-offset-2 focus:ring-offset-zinc-950"
                style={{ background: 'linear-gradient(135deg, var(--accent-500) 0%, var(--accent-600) 100%)' }}
              >
                Back to Login
              </Link>
            </div>
          ) : (
            <form className="space-y-5" onSubmit={handleSubmit(onSubmit)}>
              {error && (
                <div className="flex items-center gap-3 rounded-xl border border-red-700/50 bg-red-900/20 px-4 py-3 text-red-300">
                  <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                  </svg>
                  <span className="text-sm">{error}</span>
                </div>
              )}

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
                    className={`block w-full rounded-xl border bg-zinc-950/70 px-4 py-3 text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:ring-2 transition-colors sm:text-sm ${
                      errors.email
                        ? 'border-red-500 focus:ring-red-500 focus:border-red-500'
                        : 'border-zinc-700 hover:border-zinc-500 focus:border-[var(--accent-500)] focus:ring-[var(--accent-500)]'
                    }`}
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

              <div className="pt-2">
                <button
                  type="submit"
                  disabled={isLoading}
                  className="flex w-full justify-center rounded-xl border border-transparent px-4 py-3 text-sm font-semibold text-white transition-all disabled:cursor-not-allowed disabled:opacity-50 hover:shadow-[0_0_24px_var(--accent-500)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-500)] focus:ring-offset-2 focus:ring-offset-zinc-950"
                  style={{ background: 'linear-gradient(135deg, var(--accent-500) 0%, var(--accent-600) 100%)' }}
                >
                  {isLoading ? (
                    <span className="flex items-center gap-2">
                      <Spinner size="sm" className="border-white/40 border-t-white" />
                      Sending...
                    </span>
                  ) : (
                    'Send Reset Link'
                  )}
                </button>
              </div>

              <div className="text-center text-sm">
                <Link
                  to="/login"
                  className="font-medium text-zinc-300 transition-colors hover:text-[var(--accent-400)]"
                >
                  Back to Login
                </Link>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
