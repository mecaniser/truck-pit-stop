export interface JwtPayload {
  exp?: number
}

export function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const payloadSegment = token.split('.')[1]
    if (!payloadSegment) {
      return null
    }

    const base64 = payloadSegment.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
    return JSON.parse(globalThis.atob(padded)) as JwtPayload
  } catch {
    return null
  }
}

export function isTokenExpiredOrNearExpiry(token: string, skewSeconds = 0): boolean {
  const payload = decodeJwtPayload(token)
  if (!payload?.exp) {
    return true
  }

  const now = Math.floor(Date.now() / 1000)
  return payload.exp <= now + skewSeconds
}

export function isTokenExpired(token: string): boolean {
  return isTokenExpiredOrNearExpiry(token, 0)
}
