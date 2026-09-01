const MONEY_PATTERN = /^\d+(?:\.\d{0,2})?$/

export function moneyToCents(value: string | number | null | undefined): bigint | null {
  const raw = String(value ?? '').trim().replace(/^\$/, '').replace(/,/g, '')
  if (!MONEY_PATTERN.test(raw)) return null
  const [whole, fraction = ''] = raw.split('.')
  return (BigInt(whole || '0') * 100n) + BigInt(fraction.padEnd(2, '0'))
}

export function centsToMoney(cents: bigint): string {
  const safe = cents < 0n ? -cents : cents
  const whole = safe / 100n
  const fraction = (safe % 100n).toString().padStart(2, '0')
  return `${cents < 0n ? '-' : ''}${whole.toString()}.${fraction}`
}

export function normalizeMoney(value: string): string | null {
  const cents = moneyToCents(value)
  return cents === null ? null : centsToMoney(cents)
}

export function formatMoney(value: string | number | null | undefined): string {
  const cents = moneyToCents(value)
  if (cents === null) return '$0.00'
  const normalized = centsToMoney(cents)
  const [whole, fraction] = normalized.replace('-', '').split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${cents < 0n ? '-' : ''}$${grouped}.${fraction}`
}

export function isValidPrincipalAmount(value: string, allocatableBalance: string): boolean {
  const amount = moneyToCents(value)
  const available = moneyToCents(allocatableBalance)
  return amount !== null && available !== null && amount >= 1n && amount <= available
}

export function isPositiveMoney(value: string | number | null | undefined): boolean {
  const cents = moneyToCents(value)
  return cents !== null && cents > 0n
}
