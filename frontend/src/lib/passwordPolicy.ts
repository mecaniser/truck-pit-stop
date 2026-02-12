const COMMON_PASSWORDS = new Set([
  'password',
  'password1',
  'password123',
  '123456',
  '12345678',
  '123456789',
  'qwerty',
  'abc123',
  'monkey',
  'master',
  'dragon',
  '111111',
  'baseball',
  'iloveyou',
  'trustno1',
  'sunshine',
  'princess',
  'welcome',
  'admin',
  'letmein',
  'login',
  'passw0rd',
  'p@ssword',
  'p@ssw0rd',
])

const SPECIAL_CHAR_REGEX = /[!@#$%^&*(),.?":{}|<>\-_=+\[\]\\;'/`~]/

export function getPasswordValidationError(password: string): string | null {
  const errors: string[] = []

  if (password.length < 8) {
    errors.push('at least 8 characters')
  }
  if (!/[A-Z]/.test(password)) {
    errors.push('one uppercase letter')
  }
  if (!/[a-z]/.test(password)) {
    errors.push('one lowercase letter')
  }
  if (!/\d/.test(password)) {
    errors.push('one digit')
  }
  if (!SPECIAL_CHAR_REGEX.test(password)) {
    errors.push('one special character (!@#$%^&*...)')
  }
  if (COMMON_PASSWORDS.has(password.toLowerCase())) {
    errors.push('not be a common password')
  }

  return errors.length > 0 ? `Password must contain: ${errors.join(', ')}` : null
}
