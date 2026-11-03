import { useEffect, useState } from 'react'

import BrandLogo, { type BrandLogoVariant } from './BrandLogo'

type TenantBrandLogoProps = {
  tenantLogoUrl?: string | null
  tenantName?: string | null
  alt?: string
  className?: string
  fallbackVariant?: BrandLogoVariant
  tenantOnly?: boolean
  forcePlatform?: boolean
  tenantWrapperClassName?: string
}

export default function TenantBrandLogo({
  tenantLogoUrl,
  tenantName,
  alt,
  className,
  fallbackVariant = 'admin',
  forcePlatform = false,
  tenantOnly = false,
  tenantWrapperClassName,
}: TenantBrandLogoProps) {
  const [hasLoadError, setHasLoadError] = useState(false)

  useEffect(() => {
    setHasLoadError(false)
  }, [tenantLogoUrl])

  if (tenantOnly && (!tenantLogoUrl || hasLoadError)) {
    return <span role="img" aria-label={alt || tenantName || 'Shop'} className={className}>{tenantName || 'Shop'}</span>
  }

  if (forcePlatform || !tenantLogoUrl || hasLoadError) {
    return (
      <BrandLogo
        alt={alt || 'Diesel Bridge Network'}
        variant={fallbackVariant}
        className={className}
      />
    )
  }

  const image = (
    <img
      src={tenantLogoUrl}
      alt={alt || (tenantName ? `${tenantName} logo` : 'Tenant logo')}
      className={className}
      onError={() => setHasLoadError(true)}
    />
  )

  if (!tenantWrapperClassName) {
    return image
  }

  return <span className={tenantWrapperClassName}>{image}</span>
}
