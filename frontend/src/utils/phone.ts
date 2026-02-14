// Format to US phone pattern: (XXX) XXX-XXXX
export function formatUSPhone(value: string): string {
  const rawDigits = value.replace(/\D/g, '')
  const digits =
    rawDigits.length === 11 && rawDigits.startsWith('1')
      ? rawDigits.slice(1)
      : rawDigits.slice(0, 10)
  if (digits.length === 0) return ''
  if (digits.length <= 3) return `(${digits}`
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`
}

// Validate by counting digits only (must be exactly 10 for US)
export function isValidUSPhone(value?: string | null): boolean {
  if (!value) return true
  const digits = value.replace(/\D/g, '')
  if (digits.length === 10) return true
  return digits.length === 11 && digits.startsWith('1')
}
