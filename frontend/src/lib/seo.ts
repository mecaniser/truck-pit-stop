type JsonLdData = Record<string, unknown> | Array<Record<string, unknown>>

interface StructuredDataConfig {
  id: string
  data: JsonLdData
}

export interface SeoConfig {
  title?: string
  description?: string
  canonicalUrl?: string
  robots?: string
  ogTitle?: string
  ogDescription?: string
  ogUrl?: string
  ogType?: string
  ogImage?: string
  ogSiteName?: string
  twitterCard?: string
  twitterTitle?: string
  twitterDescription?: string
  twitterImage?: string
  structuredData?: StructuredDataConfig
}

const upsertMetaByName = (name: string, content: string) => {
  let metaTag = document.querySelector(`meta[name="${name}"]`) as HTMLMetaElement | null
  if (!metaTag) {
    metaTag = document.createElement('meta')
    metaTag.setAttribute('name', name)
    document.head.appendChild(metaTag)
  }
  metaTag.setAttribute('content', content)
}

const upsertMetaByProperty = (property: string, content: string) => {
  let metaTag = document.querySelector(`meta[property="${property}"]`) as HTMLMetaElement | null
  if (!metaTag) {
    metaTag = document.createElement('meta')
    metaTag.setAttribute('property', property)
    document.head.appendChild(metaTag)
  }
  metaTag.setAttribute('content', content)
}

const upsertCanonical = (href: string) => {
  let canonical = document.querySelector('link[rel="canonical"]') as HTMLLinkElement | null
  if (!canonical) {
    canonical = document.createElement('link')
    canonical.setAttribute('rel', 'canonical')
    document.head.appendChild(canonical)
  }
  canonical.setAttribute('href', href)
}

const upsertStructuredData = (id: string, data: JsonLdData) => {
  let script = document.getElementById(id) as HTMLScriptElement | null
  if (!script) {
    script = document.createElement('script')
    script.id = id
    script.type = 'application/ld+json'
    document.head.appendChild(script)
  }
  script.textContent = JSON.stringify(data)
}

export const removeStructuredData = (id: string) => {
  const script = document.getElementById(id)
  if (script?.tagName.toLowerCase() === 'script') {
    script.remove()
  }
}

export const applySeo = ({
  title,
  description,
  canonicalUrl,
  robots,
  ogTitle,
  ogDescription,
  ogUrl,
  ogType = 'website',
  ogImage,
  ogSiteName,
  twitterCard = 'summary_large_image',
  twitterTitle,
  twitterDescription,
  twitterImage,
  structuredData,
}: SeoConfig) => {
  if (title) {
    document.title = title
  }

  if (description) {
    upsertMetaByName('description', description)
  }

  if (robots) {
    upsertMetaByName('robots', robots)
  }

  if (canonicalUrl) {
    upsertCanonical(canonicalUrl)
  }

  const resolvedOgTitle = ogTitle || title
  const resolvedOgDescription = ogDescription || description
  const resolvedOgUrl = ogUrl || canonicalUrl
  const resolvedTwitterTitle = twitterTitle || resolvedOgTitle
  const resolvedTwitterDescription = twitterDescription || resolvedOgDescription
  const resolvedTwitterImage = twitterImage || ogImage

  if (resolvedOgTitle) {
    upsertMetaByProperty('og:title', resolvedOgTitle)
  }
  if (resolvedOgDescription) {
    upsertMetaByProperty('og:description', resolvedOgDescription)
  }
  if (resolvedOgUrl) {
    upsertMetaByProperty('og:url', resolvedOgUrl)
  }
  if (ogType) {
    upsertMetaByProperty('og:type', ogType)
  }
  if (ogImage) {
    upsertMetaByProperty('og:image', ogImage)
  }
  if (ogSiteName) {
    upsertMetaByProperty('og:site_name', ogSiteName)
  }

  if (twitterCard) {
    upsertMetaByName('twitter:card', twitterCard)
  }
  if (resolvedTwitterTitle) {
    upsertMetaByName('twitter:title', resolvedTwitterTitle)
  }
  if (resolvedTwitterDescription) {
    upsertMetaByName('twitter:description', resolvedTwitterDescription)
  }
  if (resolvedTwitterImage) {
    upsertMetaByName('twitter:image', resolvedTwitterImage)
  }

  if (structuredData) {
    upsertStructuredData(structuredData.id, structuredData.data)
  }
}
