import { useAuthStore } from '@/stores/authStore'
import { usePricingScope } from '@/features/parts-pricing/usePricingScope'
import BusinessSettings from './BusinessSettings'
import CustomerPricingControl from './CustomerPricingControl'
import CustomerTaxExemptionControl from './CustomerTaxExemptionControl'

export default function CustomerBusinessSettings({ customerId }: { customerId: string }) {
  const role = useAuthStore(state => state.user?.role); const scope = usePricingScope()
  if (role !== 'garage_owner' && role !== 'garage_admin') return null
  return <BusinessSettings key={`${scope}:${customerId}`}><CustomerPricingControl customerId={customerId} /><CustomerTaxExemptionControl customerId={customerId} /></BusinessSettings>
}
