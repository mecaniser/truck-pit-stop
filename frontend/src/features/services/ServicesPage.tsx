import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import api from '../../lib/api'
import { Service, ServiceCategory } from '../../types'

export default function ServicesPage() {
  const navigate = useNavigate()
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)

  const { data: categories } = useQuery<ServiceCategory[]>({
    queryKey: ['service-categories'],
    queryFn: async () => {
      const response = await api.get('/services/categories')
      return response.data
    },
  })

  const { data: services, isLoading } = useQuery<Service[]>({
    queryKey: ['services', selectedCategory],
    queryFn: async () => {
      const params = selectedCategory ? `?category_id=${selectedCategory}` : ''
      const response = await api.get(`/services${params}`)
      return response.data
    },
  })

  const handleBookService = (service: Service) => {
    navigate(`/portal/book/${service.id}`)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Our Services</h1>
        <p className="text-gray-400 mt-1">Book an appointment for any of our services</p>
      </div>

      {/* Category Filter */}
      {categories && Array.isArray(categories) && categories.length > 0 && (
        <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
          <div className="flex gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
            <button
              onClick={() => setSelectedCategory(null)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                selectedCategory === null
                  ? 'bg-amber-500 text-white'
                  : 'bg-white/10 text-white hover:bg-white/20'
              }`}
            >
              All Services
            </button>
            {categories.map((cat) => (
              <button
                key={cat.id}
                onClick={() => setSelectedCategory(cat.id)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap flex items-center gap-2 ${
                  selectedCategory === cat.id
                    ? 'bg-amber-500 text-white'
                    : 'bg-white/10 text-white hover:bg-white/20'
                }`}
              >
                {cat.icon && <span>{cat.icon}</span>}
                {cat.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Services Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {services && Array.isArray(services) && services.map((service) => (
          <div
            key={service.id}
            className="bg-white/5 rounded-xl p-5 border border-white/10 hover:border-amber-500/50 transition-all"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="text-3xl">{service.icon || '🔧'}</div>
              <div className="text-right">
                <div className="text-2xl font-bold text-amber-400">
                  ${parseFloat(service.base_price).toFixed(0)}
                </div>
                <div className="text-xs text-gray-500">starting at</div>
              </div>
            </div>

            <h3 className="text-lg font-semibold text-white mb-2">{service.name}</h3>
            
            {service.description && (
              <p className="text-gray-400 text-sm mb-4 line-clamp-2">{service.description}</p>
            )}

            <div className="flex items-center justify-between text-sm text-gray-500 mb-4">
              <span className="flex items-center gap-1">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                ~{service.duration_minutes} min
              </span>
              {service.requires_vehicle && (
                <span className="flex items-center gap-1">
                  <span>🚛</span> Vehicle required
                </span>
              )}
            </div>

            <button
              onClick={() => handleBookService(service)}
              className="w-full py-2.5 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg transition-colors"
            >
              Book Now
            </button>
          </div>
        ))}
      </div>

      {services && Array.isArray(services) && services.length === 0 && (
        <div className="text-center py-12">
          <div className="text-4xl mb-3">📋</div>
          <p className="text-gray-400">No services available at the moment</p>
        </div>
      )}
    </div>
  )
}

