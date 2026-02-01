import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import api from '../../lib/api'
import toast from 'react-hot-toast'
import { CheckCircle, AlertCircle, ExternalLink, CreditCard, RefreshCw } from 'lucide-react'

interface ConnectStatus {
  is_connected: boolean
  onboarding_complete: boolean
  charges_enabled: boolean
  payouts_enabled: boolean
  account_id: string | null
}

export default function StripeSettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [isRedirecting, setIsRedirecting] = useState(false)

  const { data: status, isLoading, refetch } = useQuery<ConnectStatus>({
    queryKey: ['stripe-connect-status'],
    queryFn: async () => {
      const response = await api.get('/stripe/connect/status')
      return response.data
    },
  })

  // Handle return from Stripe onboarding
  useEffect(() => {
    const success = searchParams.get('success')
    const refresh = searchParams.get('refresh')
    
    if (success === 'true') {
      toast.success('Stripe setup completed! Verifying status...')
      refetch()
      setSearchParams({}, { replace: true })
    } else if (refresh === 'true') {
      toast('Please complete your Stripe setup')
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, refetch, setSearchParams])

  const onboardMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/stripe/connect/onboard')
      return response.data
    },
    onSuccess: (data) => {
      setIsRedirecting(true)
      window.location.href = data.url
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to start Stripe setup')
    },
  })

  const refreshMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/stripe/connect/refresh')
      return response.data
    },
    onSuccess: (data) => {
      setIsRedirecting(true)
      window.location.href = data.url
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to refresh onboarding link')
    },
  })

  const dashboardMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/stripe/connect/dashboard')
      return response.data
    },
    onSuccess: (data) => {
      window.open(data.url, '_blank')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to open Stripe dashboard')
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  const getStatusDisplay = () => {
    if (!status?.is_connected) {
      return {
        icon: <AlertCircle className="w-8 h-8 text-gray-400" />,
        title: 'Not Connected',
        description: 'Connect your Stripe account to receive customer payments directly.',
        color: 'gray',
      }
    }
    if (!status.onboarding_complete) {
      return {
        icon: <AlertCircle className="w-8 h-8 text-amber-500" />,
        title: 'Setup Incomplete',
        description: 'Your Stripe account is connected but setup is not complete. Please finish the onboarding process.',
        color: 'amber',
      }
    }
    return {
      icon: <CheckCircle className="w-8 h-8 text-green-500" />,
      title: 'Connected & Active',
      description: 'Your Stripe account is fully set up. Customer payments will be deposited directly to your account.',
      color: 'green',
    }
  }

  const statusDisplay = getStatusDisplay()

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Payment Settings</h1>
        <p className="text-gray-600 mt-1">Manage how you receive customer payments</p>
      </div>

      {/* Status Card */}
      <div className={`bg-${statusDisplay.color}-50 border border-${statusDisplay.color}-200 rounded-xl p-6`}>
        <div className="flex items-start gap-4">
          {statusDisplay.icon}
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-gray-900">{statusDisplay.title}</h2>
            <p className="text-gray-600 mt-1">{statusDisplay.description}</p>
            
            {status?.is_connected && status.onboarding_complete && (
              <div className="mt-4 flex flex-wrap gap-2">
                <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm ${
                  status.charges_enabled ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                }`}>
                  {status.charges_enabled ? <CheckCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                  Charges {status.charges_enabled ? 'Enabled' : 'Disabled'}
                </span>
                <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm ${
                  status.payouts_enabled ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                }`}>
                  {status.payouts_enabled ? <CheckCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                  Payouts {status.payouts_enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
        {!status?.is_connected ? (
          // Not connected - show onboard button
          <button
            onClick={() => onboardMutation.mutate()}
            disabled={onboardMutation.isPending || isRedirecting}
            className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-400 text-white font-semibold rounded-lg flex items-center justify-center gap-2"
          >
            {onboardMutation.isPending || isRedirecting ? (
              <>
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                Redirecting to Stripe...
              </>
            ) : (
              <>
                <CreditCard className="w-5 h-5" />
                Connect Stripe Account
              </>
            )}
          </button>
        ) : !status.onboarding_complete ? (
          // Connected but incomplete - show continue button
          <button
            onClick={() => refreshMutation.mutate()}
            disabled={refreshMutation.isPending || isRedirecting}
            className="w-full py-3 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-400 text-white font-semibold rounded-lg flex items-center justify-center gap-2"
          >
            {refreshMutation.isPending || isRedirecting ? (
              <>
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                Redirecting to Stripe...
              </>
            ) : (
              <>
                <RefreshCw className="w-5 h-5" />
                Continue Stripe Setup
              </>
            )}
          </button>
        ) : (
          // Fully connected - show dashboard button
          <button
            onClick={() => dashboardMutation.mutate()}
            disabled={dashboardMutation.isPending}
            className="w-full py-3 bg-gray-900 hover:bg-gray-800 disabled:bg-gray-400 text-white font-semibold rounded-lg flex items-center justify-center gap-2"
          >
            {dashboardMutation.isPending ? (
              <>
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                Opening...
              </>
            ) : (
              <>
                <ExternalLink className="w-5 h-5" />
                Open Stripe Dashboard
              </>
            )}
          </button>
        )}

        {/* Refresh status button */}
        <button
          onClick={() => refetch()}
          className="w-full py-2 text-gray-600 hover:text-gray-900 font-medium flex items-center justify-center gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh Status
        </button>
      </div>

      {/* Info Section */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-6">
        <h3 className="font-semibold text-blue-900 mb-2">How it works</h3>
        <ul className="text-sm text-blue-800 space-y-2">
          <li className="flex items-start gap-2">
            <span className="font-bold">1.</span>
            Connect your Stripe account to enable direct payments from customers.
          </li>
          <li className="flex items-start gap-2">
            <span className="font-bold">2.</span>
            When customers pay invoices, funds go directly to your Stripe account.
          </li>
          <li className="flex items-start gap-2">
            <span className="font-bold">3.</span>
            A small platform fee (1.5%) is deducted from each transaction.
          </li>
          <li className="flex items-start gap-2">
            <span className="font-bold">4.</span>
            Manage payouts and view transaction history in your Stripe Dashboard.
          </li>
        </ul>
      </div>
    </div>
  )
}
