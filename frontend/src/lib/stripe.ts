import { loadStripe, type Stripe } from '@stripe/stripe-js'
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
