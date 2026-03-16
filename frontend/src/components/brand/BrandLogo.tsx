export type BrandLogoVariant = 'public' | 'landing' | 'admin'

const BRAND_LOGO_SOURCES: Record<BrandLogoVariant, { svg: string; png: string }> = {
  public: {
    svg: '/DB_bridge_logo_favi_figma_public.svg',
    png: '/DB_bridge_logo_favi_figma_public.png',
  },
  landing: {
    svg: '/DB_bridge_logo_favi_figma_public.svg',
    png: '/DB_bridge_logo_favi_figma_public_B.png',
  },
  admin: {
    svg: '/DB_bridge_logo_favi_figma_admin.svg',
    png: '/DB_bridge_logo_favi_figma_admin.png',
  },
}

type BrandLogoProps = {
  alt: string
  className?: string
  variant?: BrandLogoVariant
}

export default function BrandLogo({ alt, className, variant = 'public' }: BrandLogoProps) {
  const source = BRAND_LOGO_SOURCES[variant]

  return (
    <picture>
      <source srcSet={source.svg} type="image/svg+xml" />
      <img src={source.png} alt={alt} className={className} />
    </picture>
  )
}
