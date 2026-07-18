import { useEffect, useState } from 'react'
import { Spinner } from '@/components/ui'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import { CheckCircle, XCircle, Mail } from 'lucide-react'
import api from '../../lib/api'

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [newEmail, setNewEmail] = useState('')

  useEffect(() => {
    const token = searchParams.get('token')
    if (!token) {
      setStatus('error')
      setMessage('Invalid verification link')
      return
    }

    verifyEmail(token)
  }, [searchParams])

  const verifyEmail = async (token: string) => {
    try {
      const response = await api.post('/auth/verify-email', { token })
      setStatus('success')
      setMessage(response.data.message)
      setNewEmail(response.data.email)
      
      // Redirect to login after 3 seconds
      setTimeout(() => {
        navigate('/login')
      }, 3000)
    } catch (error: any) {
      setStatus('error')
      const errorDetail = error.response?.data?.detail || 'Failed to verify email'
      
      // Provide helpful message for conflict errors
      if (error.response?.status === 409) {
        setMessage(errorDetail + ' Please try changing to a different email address.')
      } else {
        setMessage(errorDetail)
      }
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-4">
      <div className="w-full max-w-md">
        <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-8 shadow-2xl">
          {status === 'loading' && (
            <div className="text-center">
              <div className="w-16 h-16 bg-blue-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <Spinner size="lg" />
              </div>
              <h1 className="text-2xl font-bold text-white mb-2">Verifying Email...</h1>
              <p className="text-gray-400">Please wait while we verify your email address</p>
            </div>
          )}

          {status === 'success' && (
            <div className="text-center">
              <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <CheckCircle className="w-8 h-8 text-green-400" />
              </div>
              <h1 className="text-2xl font-bold text-white mb-2">Email Verified!</h1>
              <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4 mb-4">
                <p className="text-green-400 text-sm">{message}</p>
                {newEmail && (
                  <div className="mt-3 flex items-center justify-center gap-2 text-white">
                    <Mail className="w-4 h-4" />
                    <span className="font-medium">{newEmail}</span>
                  </div>
                )}
              </div>
              <p className="text-gray-400 text-sm mb-4">
                You can now log in with your new email address
              </p>
              <p className="text-gray-500 text-xs">
                Redirecting to login in 3 seconds...
              </p>
            </div>
          )}

          {status === 'error' && (
            <div className="text-center">
              <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <XCircle className="w-8 h-8 text-red-400" />
              </div>
              <h1 className="text-2xl font-bold text-white mb-2">Verification Failed</h1>
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6">
                <p className="text-red-400 text-sm">{message}</p>
              </div>
              <p className="text-gray-400 text-sm mb-6">
                The verification link may have expired or is invalid.
              </p>
              <Link
                to="/login"
                className="inline-block px-6 py-3 bg-amber-600 hover:bg-amber-700 text-white font-medium rounded-lg transition-colors"
              >
                Back to Login
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
