import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import api from '../../lib/api'
import { Service, ServiceCategory } from '../../types'
import { ClipboardList, Clock3, Truck, Wrench } from 'lucide-react'
import ViewToggle from '../../components/ViewToggle'
import { useViewPreference } from '../../hooks/useViewPreference'

function getQuickFilterLabel(name: string) {
  const normalized = name.trim().toLowerCase()
  if (normalized === 'all pm services' || normalized === 'pm services') return 'PM'
  if (normalized === 'other services') return 'Other'
  return name
}

export default function ServicesPage() {
  const navigate = useNavigate()
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [viewMode, setViewMode] = useViewPreference('customer-services', 'cards')
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < 640 : false
  )

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

  useEffect(() => {
    if (typeof window === 'undefined') return
    const handleResize = () => setIsMobile(window.innerWidth < 640)
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const activeViewMode = isMobile ? 'list' : viewMode

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

      {/* Filters + View Toggle */}
      {categories && Array.isArray(categories) && categories.length > 0 ? (
        <>
          <div className="sm:hidden overflow-x-auto -mx-4 px-4">
            <div className="flex gap-2 min-w-max">
              <button
                onClick={() => setSelectedCategory(null)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                  selectedCategory === null
                    ? 'bg-amber-500 text-white'
                    : 'bg-white/10 text-white hover:bg-white/20'
                }`}
              >
                All
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
                  {getQuickFilterLabel(cat.name)}
                </button>
              ))}
            </div>
          </div>

          <div className="hidden sm:flex items-center justify-between gap-3">
            <div className="flex-1 overflow-x-auto">
              <div className="flex gap-2 min-w-max">
                <button
                  onClick={() => setSelectedCategory(null)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                    selectedCategory === null
                      ? 'bg-amber-500 text-white'
                      : 'bg-white/10 text-white hover:bg-white/20'
                  }`}
                >
                  All
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
                    {getQuickFilterLabel(cat.name)}
                  </button>
                ))}
              </div>
            </div>
            <ViewToggle value={activeViewMode} onChange={setViewMode} disabled={isMobile} />
          </div>
        </>
      ) : (
        <div className="hidden sm:flex items-center justify-end">
          <ViewToggle value={activeViewMode} onChange={setViewMode} disabled={isMobile} />
        </div>
      )}

      {activeViewMode === 'list' ? (
        <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full divide-y divide-white/10">
              <thead className="bg-white/5">
                <tr>
                  <th className="px-3 sm:px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Service</th>
                  <th className="px-3 sm:px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide hidden md:table-cell">Category</th>
                  <th className="px-3 sm:px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wide">Price & Time</th>
                  <th className="px-3 sm:px-4 py-3 text-right text-xs font-medium text-gray-400 uppercase tracking-wide">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {services && Array.isArray(services) && services.map((service) => {
                  const category = categories?.find((cat) => cat.id === service.category_id)
                  return (
                    <tr key={service.id} className="hover:bg-white/5">
                      <td className="px-3 sm:px-4 py-3 min-w-0">
                        <div className="flex items-start gap-2.5">
                          <span className="text-xl text-amber-200 mt-0.5">
                            {service.icon ? <span>{service.icon}</span> : <Wrench className="w-5 h-5" />}
                          </span>
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-white">{service.name}</div>
                            {service.description && (
                              <div className="text-xs text-gray-500 line-clamp-1">{service.description}</div>
                            )}
                            {service.requires_vehicle && (
                              <div className="text-[11px] text-gray-400 mt-1 inline-flex items-center gap-1">
                                <Truck className="w-3.5 h-3.5" />
                                Vehicle required
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-3 sm:px-4 py-3 text-sm text-gray-400 hidden md:table-cell">
                        {category?.name || 'Uncategorized'}
                      </td>
                      <td className="px-3 sm:px-4 py-3 whitespace-nowrap">
                        <div className="text-sm font-medium text-amber-400">
                          ${parseFloat(service.computed_total_price).toFixed(2)}
                        </div>
                        <div className="text-xs text-gray-400">
                          ~{service.duration_minutes} min
                        </div>
                      </td>
                      <td className="px-3 sm:px-4 py-3 text-right">
                        <button
                          onClick={() => handleBookService(service)}
                          className="px-2.5 sm:px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white text-xs sm:text-sm font-medium rounded-lg transition-colors"
                        >
                          Book
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {services && Array.isArray(services) && services.map((service) => (
            <div
              key={service.id}
              className="bg-white/5 rounded-xl p-5 border border-white/10 hover:border-amber-500/50 transition-all"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="text-3xl text-amber-200">
                  {service.icon ? (
                    <span>{service.icon}</span>
                  ) : (
                    <Wrench className="w-8 h-8" />
                  )}
                </div>
                <div className="text-right">
                  <div className="text-2xl font-bold text-amber-400">
                    ${parseFloat(service.computed_total_price).toFixed(0)}
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
                  <Clock3 className="w-4 h-4" />
                  ~{service.duration_minutes} min
                </span>
                {service.requires_vehicle && (
                  <span className="flex items-center gap-1">
                    <Truck className="w-4 h-4" />
                    Vehicle required
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
      )}

      {services && Array.isArray(services) && services.length === 0 && (
        <div className="text-center py-12">
          <div className="flex justify-center mb-3">
            <ClipboardList className="w-10 h-10 text-gray-400" />
          </div>
          <p className="text-gray-400">No services available at the moment</p>
        </div>
      )}
    </div>
  )
}
