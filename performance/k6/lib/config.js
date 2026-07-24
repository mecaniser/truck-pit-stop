import { fail } from 'k6'

function required(name) {
  const value = __ENV[name]
  if (!value) {
    fail(`${name} is required`)
  }
  return value
}

function optional(name) {
  return __ENV[name] || null
}

function asPositiveNumber(name, fallback) {
  const rawValue = __ENV[name]
  if (!rawValue) {
    return fallback
  }

  const value = Number(rawValue)
  if (!Number.isFinite(value) || value <= 0) {
    fail(`${name} must be a positive number`)
  }
  return value
}

function normalizeBaseUrl(value) {
  return value.replace(/\/+$/, '')
}

export function loadConfig({ allowProduction }) {
  const baseUrl = normalizeBaseUrl(required('BASE_URL'))
  const target = (__ENV.TARGET_ENV || 'staging').toLowerCase()
  const isKnownProductionHost = /^https:\/\/(www\.)?dieselbridge\.com(?:\/|$)/i.test(baseUrl)

  if (isKnownProductionHost && target !== 'production') {
    fail('TARGET_ENV=production is required when BASE_URL is dieselbridge.com')
  }

  if (target === 'production') {
    if (!allowProduction) {
      fail('This profile cannot run against production')
    }
    if (__ENV.ALLOW_PRODUCTION !== 'true') {
      fail('ALLOW_PRODUCTION=true is required for a production canary')
    }
  }

  if (target !== 'production' && target !== 'staging' && target !== 'local' && target !== 'performance') {
    fail('TARGET_ENV must be production, staging, local, or performance')
  }

  return {
    accessToken: optional('K6_ACCESS_TOKEN'),
    baseUrl,
    target,
    orderId: __ENV.REPAIR_ORDER_ID || null,
    canaryRate: asPositiveNumber('CANARY_RATE_PER_MINUTE', 2),
    loadTestPassword: optional('K6_LOAD_TEST_PASSWORD'),
    loadTestUserPrefix: __ENV.K6_LOAD_TEST_USER_PREFIX || 'performance-load',
    loadTestEmailDomain: __ENV.K6_LOAD_TEST_EMAIL_DOMAIN || 'dieselbridge.com',
  }
}

export function requireAccessToken(config) {
  if (!config.accessToken) {
    fail('K6_ACCESS_TOKEN is required')
  }
  return config.accessToken
}

export function requireLoadTestPassword(config) {
  if (!config.loadTestPassword) {
    fail('K6_LOAD_TEST_PASSWORD is required for the multi-user performance capacity test')
  }
  return config.loadTestPassword
}
