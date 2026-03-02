import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'
import { formatUSPhone } from '../utils/phone'

interface PlatformContactResponse {
  support_name: string
  support_email: string | null
  support_phone: string | null
}

const FALLBACK_SUPPORT_NAME = 'Diesel Bridge Support'
const FALLBACK_SUPPORT_EMAIL = 'support@dieselbridge.network'

const buildTelHref = (phone: string | null): string | null => {
  if (!phone) return null
  const digits = phone.replace(/\D/g, '')
  if (!digits) return null
  if (digits.length === 10) return `tel:+1${digits}`
  if (digits.length === 11 && digits.startsWith('1')) return `tel:+${digits}`
  return `tel:+${digits}`
}

const formatSupportPhone = (phone: string | null): string | null => {
  if (!phone) return null
  const digits = phone.replace(/\D/g, '')
  if (digits.length === 10 || (digits.length === 11 && digits.startsWith('1'))) {
    return formatUSPhone(phone)
  }
  return phone
}

export function usePlatformContact() {
  const { data, isLoading } = useQuery<PlatformContactResponse>({
    queryKey: ['platform-contact'],
    queryFn: async () => {
      const response = await api.get('/auth/platform-contact')
      return response.data as PlatformContactResponse
    },
    staleTime: 5 * 60 * 1000,
    retry: 1,
  })

  return useMemo(() => {
    const supportName = data?.support_name?.trim() || FALLBACK_SUPPORT_NAME
    const supportEmail = data?.support_email || FALLBACK_SUPPORT_EMAIL
    const supportPhone = data?.support_phone || null
    const supportPhoneDisplay = formatSupportPhone(supportPhone)
    const mailtoHref = supportEmail ? `mailto:${supportEmail}` : null
    const telHref = buildTelHref(supportPhone)

    return {
      supportName,
      supportEmail,
      supportPhone,
      supportPhoneDisplay,
      mailtoHref,
      telHref,
      isLoading,
    }
  }, [data, isLoading])
}
