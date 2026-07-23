// The default entrypoint injects Stripe.js as soon as this module is imported.
// Use the pure loader so staff routes do not create payment iframes until a
// customer-facing payment flow explicitly requests Stripe.
import { loadStripe } from '@stripe/stripe-js/pure'
import type { Stripe } from '@stripe/stripe-js'
import api from './api'

const stripePromiseCache = new Map<string, Promise<Stripe | null>>()

const buildCacheKey = (publishableKey: string, stripeAccountId?: string | null) =>
  `${publishableKey}:${stripeAccountId ?? 'platform'}`

export async function getStripeForAccount(stripeAccountId?: string | null): Promise<Stripe | null> {
  const { data } = await api.get<{ publishable_key: string }>('/payments/config')
  const publishableKey = data.publishable_key

  if (!publishableKey) {
    throw new Error('Stripe publishable key is not configured')
  }

  const cacheKey = buildCacheKey(publishableKey, stripeAccountId)
  const cached = stripePromiseCache.get(cacheKey)
  if (cached) {
    return cached
  }

  const options = stripeAccountId ? { stripeAccount: stripeAccountId } : undefined
  const stripePromise = loadStripe(publishableKey, options)
  stripePromiseCache.set(cacheKey, stripePromise)
  return stripePromise
}
