import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import { policySchema } from './configuration'
import { pricingMoney } from './contract'
import { usePricingScope } from './usePricingScope'

/** Only the selected manager view reads private policy; never hydrate shared rows. */
export default function PartPolicySummary({ inventoryId }: { inventoryId: string }) {
  const scope = usePricingScope()
  const role = useAuthStore(state => state.user?.role)
  const manager = role === 'garage_owner' || role === 'garage_admin'
  const query = useQuery({ queryKey: ['part-policy-summary', scope, inventoryId], enabled: manager, gcTime: 0, retry: false, queryFn: async ({ signal }) => {
    const policy = policySchema.parse((await api.get(`/parts-pricing/inventory/${inventoryId}/pricing-policy`, { signal })).data).policy
    if (policy.inventory_id !== inventoryId) throw new Error('Invalid part identity')
    return policy
  } })
  if (!manager || query.isError || !query.data) return null
  return <small className="db-parts-pricing__source db-parts-pricing__policy-summary">{query.data.fixed_sales_price ? 'Fixed catalog price' : 'Shop pricing'}{query.data.pricing_cost_floor !== null && ` · Cost floor ${pricingMoney(query.data.pricing_cost_floor)}`}{query.data.minimum_sale_price !== null && ` · Sale minimum ${pricingMoney(query.data.minimum_sale_price)}`}</small>
}
