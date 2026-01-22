import { forwardRef } from 'react'
import { AddressAutofill } from '@mapbox/search-js-react'
import type { AddressAutofillOptions, AddressAutofillRetrieveResponse } from '@mapbox/search-js-core'

type MapboxFeature = AddressAutofillRetrieveResponse['features'][number]

type OnAddressSelectPayload = {
  formatted: string
  feature?: MapboxFeature
  event: AddressAutofillRetrieveResponse
}

export type MapboxAddressInputProps = React.InputHTMLAttributes<HTMLInputElement> & {
  options?: Partial<AddressAutofillOptions>
  onAddressSelect?: (payload: OnAddressSelectPayload) => void
}

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''

export const formatAddressFromFeature = (feature?: MapboxFeature) => {
  const props = feature?.properties as Record<string, unknown> | undefined
  if (!props) return ''

  const parts = [props.place_formatted, props.full_address, props.address_line1, props.name, props.place, props.region, props.postcode]
    .map((value) => (typeof value === 'string' ? value : ''))
    .filter(Boolean)

  if (parts.length === 0) return ''
  const [primary, ...rest] = parts
  return primary || rest.join(', ')
}

const MapboxAddressInput = forwardRef<HTMLInputElement, MapboxAddressInputProps>(
  ({ options, onAddressSelect, type = 'text', ...inputProps }, ref) => {
    const input = <input {...inputProps} type={type} ref={ref} />

    if (!MAPBOX_TOKEN) {
      return input
    }

    return (
      <AddressAutofill
        accessToken={MAPBOX_TOKEN}
        options={{ language: 'en', ...(options || {}) }}
        onRetrieve={(event) => {
          const feature = event?.features?.[0]
          const formatted = formatAddressFromFeature(feature)
          onAddressSelect?.({ formatted, feature, event })
        }}
      >
        {input}
      </AddressAutofill>
    )
  }
)

MapboxAddressInput.displayName = 'MapboxAddressInput'

export default MapboxAddressInput
