import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import api from '../../lib/api'
import toast from 'react-hot-toast'
import { CheckCircle, AlertCircle, ExternalLink, CreditCard, RefreshCw, QrCode, Save, Bell, BellOff, Percent, Upload, Trash2, ImageIcon } from 'lucide-react'

interface ConnectStatus {
  is_connected: boolean
  onboarding_complete: boolean
  charges_enabled: boolean
  payouts_enabled: boolean
  account_id: string | null
}

interface ZelleSettings {
  zelle_email: string | null
  zelle_phone: string | null
  zelle_qr_image: string | null
}

interface ReminderSettings {
  invoice_reminders_enabled: boolean
  reminder_frequency_days: number
  max_invoice_reminders: number
}

interface TaxFeeSettings {
  sales_tax_rate: number
  shop_supplies_rate: number
  service_fee_rate: number
}

export default function GarageSettingsPage() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [isRedirecting, setIsRedirecting] = useState(false)
  const [zelleQrPreview, setZelleQrPreview] = useState<string | null>(null)
  const [isUploadingQr, setIsUploadingQr] = useState(false)
  
  // Reminder settings state
  const [remindersEnabled, setRemindersEnabled] = useState(true)
  const [reminderFrequency, setReminderFrequency] = useState(3)
  const [maxReminders, setMaxReminders] = useState(3)
  const [isEditingReminders, setIsEditingReminders] = useState(false)
  const [isEditingZelle, setIsEditingZelle] = useState(false)
  
  // Tax/fee settings state (strings for input handling)
  const [salesTaxRate, setSalesTaxRate] = useState('')
  const [shopSuppliesRate, setShopSuppliesRate] = useState('')
  const [serviceFeeRate, setServiceFeeRate] = useState('')
  const [isEditingTaxFees, setIsEditingTaxFees] = useState(false)

  const { data: status, isLoading, refetch } = useQuery<ConnectStatus>({
    queryKey: ['stripe-connect-status'],
    queryFn: async () => {
      const response = await api.get('/stripe/connect/status')
      return response.data
    },
  })

  const { data: zelleSettings } = useQuery<ZelleSettings>({
    queryKey: ['zelle-settings'],
    queryFn: async () => {
      const response = await api.get('/admin/zelle-settings')
      return response.data
    },
  })

  const { data: reminderSettings } = useQuery<ReminderSettings>({
    queryKey: ['reminder-settings'],
    queryFn: async () => {
      const response = await api.get('/admin/reminder-settings')
      return response.data
    },
  })

  const { data: taxFeeSettings } = useQuery<TaxFeeSettings>({
    queryKey: ['tax-fee-settings'],
    queryFn: async () => {
      const response = await api.get('/admin/tax-fee-settings')
      return response.data
    },
  })

  useEffect(() => {
    if (reminderSettings) {
      setRemindersEnabled(reminderSettings.invoice_reminders_enabled)
      setReminderFrequency(reminderSettings.reminder_frequency_days)
      setMaxReminders(reminderSettings.max_invoice_reminders)
    }
  }, [reminderSettings])

  useEffect(() => {
    if (taxFeeSettings) {
      setSalesTaxRate(taxFeeSettings.sales_tax_rate?.toString() || '')
      setShopSuppliesRate(taxFeeSettings.shop_supplies_rate?.toString() || '')
      setServiceFeeRate(taxFeeSettings.service_fee_rate?.toString() || '')
    }
  }, [taxFeeSettings])

  const uploadQrMutation = useMutation({
    mutationFn: async (base64Image: string | null) => {
      const response = await api.put('/admin/zelle-qr-image', {
        zelle_qr_image: base64Image,
      })
      return response.data
    },
    onSuccess: () => {
      toast.success(zelleQrPreview ? 'QR code uploaded' : 'QR code removed')
      queryClient.invalidateQueries({ queryKey: ['zelle-settings'] })
      setZelleQrPreview(null)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to upload QR code')
    },
  })

  const handleQrFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Validate file type
    if (!file.type.startsWith('image/')) {
      toast.error('Please select an image file')
      return
    }

    // Validate file size (max 1.5MB)
    if (file.size > 1.5 * 1024 * 1024) {
      toast.error('Image too large. Maximum size is 1.5MB')
      return
    }

    setIsUploadingQr(true)
    const reader = new FileReader()
    reader.onload = (event) => {
      const base64 = event.target?.result as string
      setZelleQrPreview(base64)
      setIsUploadingQr(false)
    }
    reader.onerror = () => {
      toast.error('Failed to read file')
      setIsUploadingQr(false)
    }
    reader.readAsDataURL(file)
  }

  const handleSaveQrImage = () => {
    if (zelleQrPreview) {
      uploadQrMutation.mutate(zelleQrPreview)
    }
  }

  const handleRemoveQrImage = () => {
    uploadQrMutation.mutate(null)
    setZelleQrPreview(null)
  }

  const saveRemindersMutation = useMutation({
    mutationFn: async () => {
      const response = await api.put('/admin/reminder-settings', {
        invoice_reminders_enabled: remindersEnabled,
        reminder_frequency_days: reminderFrequency,
        max_invoice_reminders: maxReminders,
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Reminder settings saved')
      queryClient.invalidateQueries({ queryKey: ['reminder-settings'] })
      setIsEditingReminders(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to save reminder settings')
    },
  })

  const cancelReminderEdit = () => {
    // Reset to saved values
    if (reminderSettings) {
      setRemindersEnabled(reminderSettings.invoice_reminders_enabled)
      setReminderFrequency(reminderSettings.reminder_frequency_days)
      setMaxReminders(reminderSettings.max_invoice_reminders)
    }
    setIsEditingReminders(false)
  }

  const saveTaxFeesMutation = useMutation({
    mutationFn: async () => {
      const response = await api.put('/admin/tax-fee-settings', {
        sales_tax_rate: parseFloat(salesTaxRate) || 0,
        shop_supplies_rate: parseFloat(shopSuppliesRate) || 0,
        service_fee_rate: parseFloat(serviceFeeRate) || 0,
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Tax & fee settings saved')
      queryClient.invalidateQueries({ queryKey: ['tax-fee-settings'] })
      setIsEditingTaxFees(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to save tax & fee settings')
    },
  })

  const cancelTaxFeesEdit = () => {
    if (taxFeeSettings) {
      setSalesTaxRate(taxFeeSettings.sales_tax_rate?.toString() || '')
      setShopSuppliesRate(taxFeeSettings.shop_supplies_rate?.toString() || '')
      setServiceFeeRate(taxFeeSettings.service_fee_rate?.toString() || '')
    }
    setIsEditingTaxFees(false)
  }

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
    <div className="max-w-2xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Garage Settings</h1>
        <p className="text-gray-400 mt-1">Configure your garage's payment and notification preferences</p>
      </div>

      {/* ============ PAYMENTS SECTION ============ */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <CreditCard className="w-5 h-5 text-gray-400" />
          Payments
        </h2>

        {/* Stripe Status Card */}
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

        {/* Zelle Settings */}
        <div className="bg-white border border-gray-200 rounded-xl p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <QrCode className="w-6 h-6 text-purple-600" />
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Zelle Payments</h2>
              {!isEditingZelle && (
                <p className="text-sm text-gray-600">
                  {zelleSettings?.zelle_qr_image ? (
                    'QR code uploaded'
                  ) : zelleSettings?.zelle_email || zelleSettings?.zelle_phone ? (
                    zelleSettings.zelle_email || zelleSettings.zelle_phone
                  ) : (
                    'Not configured'
                  )}
                </p>
              )}
            </div>
          </div>
          {!isEditingZelle && (
            <button
              onClick={() => setIsEditingZelle(true)}
              className="text-sm text-purple-600 hover:text-purple-700 font-medium"
            >
              Edit
            </button>
          )}
        </div>

        {isEditingZelle && (
          <div className="mt-4 pt-4 border-t border-gray-200 space-y-4">
            {/* QR Code Upload Section */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Zelle QR Code</label>
              
              {/* Current/Preview QR Image */}
              {(zelleQrPreview || zelleSettings?.zelle_qr_image) && (
                <div className="mb-3 p-4 bg-gray-50 rounded-lg border border-gray-200">
                  <div className="flex items-start gap-4">
                    <img
                      src={zelleQrPreview || zelleSettings?.zelle_qr_image || ''}
                      alt="Zelle QR Code"
                      className="w-32 h-32 object-contain bg-white rounded border"
                    />
                    <div className="flex-1">
                      <p className="text-sm text-gray-600 mb-2">
                        {zelleQrPreview ? 'Preview - click Save to upload' : 'Current QR code'}
                      </p>
                      <div className="flex gap-2">
                        {zelleQrPreview && (
                          <button
                            onClick={handleSaveQrImage}
                            disabled={uploadQrMutation.isPending}
                            className="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 text-white text-sm font-medium rounded-lg flex items-center gap-1"
                          >
                            {uploadQrMutation.isPending ? (
                              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                            ) : (
                              <>
                                <Save className="w-3.5 h-3.5" />
                                Save QR
                              </>
                            )}
                          </button>
                        )}
                        <button
                          onClick={() => {
                            setZelleQrPreview(null)
                            if (!zelleQrPreview && zelleSettings?.zelle_qr_image) {
                              handleRemoveQrImage()
                            }
                          }}
                          disabled={uploadQrMutation.isPending}
                          className="px-3 py-1.5 border border-red-300 text-red-600 hover:bg-red-50 text-sm font-medium rounded-lg flex items-center gap-1"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          {zelleQrPreview ? 'Cancel' : 'Remove'}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Upload Button */}
              {!zelleQrPreview && !zelleSettings?.zelle_qr_image && (
                <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-gray-300 rounded-lg cursor-pointer hover:border-purple-400 hover:bg-purple-50/50 transition-colors">
                  <div className="flex flex-col items-center justify-center pt-5 pb-6">
                    {isUploadingQr ? (
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
                    ) : (
                      <>
                        <ImageIcon className="w-8 h-8 text-gray-400 mb-2" />
                        <p className="text-sm text-gray-600">
                          <span className="font-medium text-purple-600">Click to upload</span> your Zelle QR code
                        </p>
                        <p className="text-xs text-gray-500 mt-1">PNG, JPG up to 1.5MB</p>
                      </>
                    )}
                  </div>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleQrFileChange}
                    className="hidden"
                    disabled={isUploadingQr}
                  />
                </label>
              )}

              {/* Change QR button when one exists */}
              {!zelleQrPreview && zelleSettings?.zelle_qr_image && (
                <label className="inline-flex items-center gap-2 px-3 py-1.5 text-sm text-purple-600 hover:text-purple-700 cursor-pointer">
                  <Upload className="w-4 h-4" />
                  Upload new QR code
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleQrFileChange}
                    className="hidden"
                    disabled={isUploadingQr}
                  />
                </label>
              )}
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setIsEditingZelle(false)}
                className="px-4 py-2 border border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50"
              >
                Done
              </button>
            </div>
          </div>
        )}
        </div>

        {/* Tax & Fee Settings */}
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Percent className="w-6 h-6 text-green-600" />
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Taxes & Fees</h2>
                {!isEditingTaxFees && (
                  <p className="text-sm text-gray-600">
                    {(taxFeeSettings?.sales_tax_rate || 0) > 0 || (taxFeeSettings?.shop_supplies_rate || 0) > 0 || (taxFeeSettings?.service_fee_rate || 0) > 0 ? (
                      <>
                        Tax: {taxFeeSettings?.sales_tax_rate || 0}% | Supplies: {taxFeeSettings?.shop_supplies_rate || 0}% | Service: {taxFeeSettings?.service_fee_rate || 0}%
                      </>
                    ) : (
                      'No taxes or fees configured'
                    )}
                  </p>
                )}
              </div>
            </div>
            {!isEditingTaxFees && (
              <button
                onClick={() => setIsEditingTaxFees(true)}
                className="text-sm text-green-600 hover:text-green-700 font-medium"
              >
                Edit
              </button>
            )}
          </div>

          {isEditingTaxFees && (
            <div className="mt-4 pt-4 border-t border-gray-200 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Sales Tax Rate (%)
                </label>
                <input
                  type="number"
                  step="0.001"
                  min="0"
                  max="100"
                  value={salesTaxRate}
                  onChange={(e) => setSalesTaxRate(e.target.value)}
                  placeholder="8.25"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
                />
                <p className="text-xs text-gray-500 mt-1">Applied to taxable total</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Shop Supplies Rate (%)
                </label>
                <input
                  type="number"
                  step="0.001"
                  min="0"
                  max="100"
                  value={shopSuppliesRate}
                  onChange={(e) => setShopSuppliesRate(e.target.value)}
                  placeholder="3"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
                />
                <p className="text-xs text-gray-500 mt-1">Percentage of labor charges</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Service Fee Rate (%)
                </label>
                <input
                  type="number"
                  step="0.001"
                  min="0"
                  max="100"
                  value={serviceFeeRate}
                  onChange={(e) => setServiceFeeRate(e.target.value)}
                  placeholder="0"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
                />
                <p className="text-xs text-gray-500 mt-1">Percentage of subtotal</p>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={cancelTaxFeesEdit}
                  className="flex-1 py-2 border border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={() => saveTaxFeesMutation.mutate()}
                  disabled={saveTaxFeesMutation.isPending}
                  className="flex-1 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-medium rounded-lg flex items-center justify-center gap-2"
                >
                  {saveTaxFeesMutation.isPending ? (
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                  ) : (
                    <>
                      <Save className="w-4 h-4" />
                      Save
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ============ NOTIFICATIONS SECTION ============ */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Bell className="w-5 h-5 text-gray-400" />
          Notifications
        </h2>

        {/* Invoice Reminder Settings */}
        <div className="bg-white border border-gray-200 rounded-xl p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {reminderSettings?.invoice_reminders_enabled !== false ? (
              <Bell className="w-6 h-6 text-amber-600" />
            ) : (
              <BellOff className="w-6 h-6 text-gray-400" />
            )}
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Invoice Reminders</h2>
              {!isEditingReminders && (
                <p className="text-sm text-gray-600">
                  {reminderSettings?.invoice_reminders_enabled !== false ? (
                    <>
                      {reminderSettings?.max_invoice_reminders || 3} reminders, every {reminderSettings?.reminder_frequency_days || 3} days
                    </>
                  ) : (
                    'Disabled'
                  )}
                </p>
              )}
            </div>
          </div>
          {!isEditingReminders && (
            <button
              onClick={() => setIsEditingReminders(true)}
              className="text-sm text-amber-600 hover:text-amber-700 font-medium"
            >
              Edit
            </button>
          )}
        </div>

        {isEditingReminders && (
          <div className="mt-4 pt-4 border-t border-gray-200 space-y-4">
            {/* Enable/Disable Toggle */}
            <div className="flex items-center justify-between py-2">
              <div>
                <p className="font-medium text-gray-900">Enable Automatic Reminders</p>
                <p className="text-sm text-gray-500">Send SMS and email reminders for overdue invoices</p>
              </div>
              <button
                onClick={() => setRemindersEnabled(!remindersEnabled)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  remindersEnabled ? 'bg-amber-500' : 'bg-gray-300'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    remindersEnabled ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            {remindersEnabled && (
              <>
                {/* Frequency */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Reminder Frequency
                  </label>
                  <select
                    value={reminderFrequency}
                    onChange={(e) => setReminderFrequency(Number(e.target.value))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                  >
                    <option value={1}>Every day</option>
                    <option value={2}>Every 2 days</option>
                    <option value={3}>Every 3 days</option>
                    <option value={5}>Every 5 days</option>
                    <option value={7}>Every week</option>
                    <option value={14}>Every 2 weeks</option>
                  </select>
                </div>

                {/* Max Reminders */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Maximum Reminders
                  </label>
                  <select
                    value={maxReminders}
                    onChange={(e) => setMaxReminders(Number(e.target.value))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                  >
                    {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                      <option key={n} value={n}>
                        {n} reminder{n > 1 ? 's' : ''}
                      </option>
                    ))}
                  </select>
                </div>
              </>
            )}

            <p className="text-xs text-gray-500">
              Reminders are sent daily at 9 AM UTC, starting on the due date.
            </p>

            <div className="flex gap-2">
              <button
                onClick={cancelReminderEdit}
                className="flex-1 py-2 border border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => saveRemindersMutation.mutate()}
                disabled={saveRemindersMutation.isPending}
                className="flex-1 py-2 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-400 text-white font-medium rounded-lg flex items-center justify-center gap-2"
              >
                {saveRemindersMutation.isPending ? (
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                ) : (
                  <>
                    <Save className="w-4 h-4" />
                    Save
                  </>
                )}
              </button>
            </div>
          </div>
        )}
        </div>
      </section>
    </div>
  )
}
