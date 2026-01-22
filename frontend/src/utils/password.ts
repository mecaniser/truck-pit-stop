/**
 * Generates a mechanic password using their first name and the last four digits of their phone number.
 * Ensures at least 8 characters with a mix of upper/lower and numbers to satisfy basic password rules.
 */
export function generateMechanicPassword(firstName: string, phone: string): string {
  const cleanedName = (firstName || 'Mechanic').trim()
  const namePortion =
    cleanedName.length > 0
      ? cleanedName.charAt(0).toUpperCase() + cleanedName.slice(1).toLowerCase()
      : 'Mechanic'

  const digits = (phone || '').replace(/\D/g, '')
  const last4 = digits.slice(-4) || '0000'

  let password = `${namePortion}${last4}`

  if (password.length < 8) {
    password = password.padEnd(8, 'X')
  }

  return password
}
