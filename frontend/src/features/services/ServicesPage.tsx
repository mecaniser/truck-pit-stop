import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Wrench } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { Spinner } from '@/components/ui'
import api from '@/lib/api'
import type { Service, ServiceCategory, Vehicle } from '@/types'
import { formatMoney, Pill, vehicleName } from '@/features/customer-portal/portal-ui'

const categoryColors = ['#8b7cf7', '#ff6b6e', '#3ecf6f', '#f0b959', '#2dd4bf']

function shortCategoryName(value: string) {
  const normalized = value.trim().toLowerCase()
  if (normalized === 'all pm services') return 'PM Services'
  if (normalized === 'other services') return 'Other services'
  return value
}

export default function ServicesPage() {
  const navigate = useNavigate()
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const { data: categories = [] } = useQuery<ServiceCategory[]>({
    queryKey: ['service-categories'],
    queryFn: async () => (await api.get('/services/categories')).data,
  })
  const { data: services = [], isLoading } = useQuery<Service[]>({
    queryKey: ['services', 'portal-all'],
    queryFn: async () => (await api.get('/services')).data,
  })
  const { data: vehicles = [] } = useQuery<Vehicle[]>({
    queryKey: ['vehicles'],
    queryFn: async () => {
      const response = await api.get('/vehicles', { params: { paginated: true, skip: 0, limit: 100 } })
      return Array.isArray(response.data) ? response.data : response.data.items
    },
  })

  const categoryMap = useMemo(
    () => new Map(categories.map((category, index) => [category.id, { ...category, color: categoryColors[index % categoryColors.length] }])),
    [categories],
  )

  const visibleServices = useMemo(() => {
    const query = search.trim().toLowerCase()
    return services.filter(service => {
      if (selectedCategory && service.category_id !== selectedCategory) return false
      if (!query) return true
      return `${service.name} ${service.description || ''}`.toLowerCase().includes(query)
    })
  }, [search, selectedCategory, services])

  const groups = useMemo(() => {
    const grouped = new Map<string, Service[]>()
    visibleServices.forEach(service => {
      const key = service.category_id || 'other'
      grouped.set(key, [...(grouped.get(key) || []), service])
    })
    return [...grouped.entries()]
      .map(([categoryId, items], index) => {
        const category = categoryMap.get(categoryId)
        const sorted = [...items].sort((a, b) => Number(a.computed_total_price) - Number(b.computed_total_price))
        const prices = sorted.map(item => Number(item.computed_total_price || 0))
        return {
          id: categoryId,
          name: shortCategoryName(category?.name || 'Other services'),
          color: category?.color || categoryColors[index % categoryColors.length],
          items: sorted,
          min: Math.min(...prices),
          max: Math.max(...prices),
        }
      })
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [categoryMap, visibleServices])

  if (isLoading) return <div className="flex min-h-[420px] items-center justify-center"><Spinner size="xl" /></div>

  const vehicle = vehicles[0]

  return (
    <div className="space-y-4">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-extrabold tracking-[-0.01em]">Book a service</h1>
          <p className="mt-1 max-w-3xl text-[13px] leading-5 text-[#8b92a5]">
            {vehicles.length === 1 ? (
              <>All services are performed on <span className="font-semibold text-[#d9a521]">{vehicleName(vehicle)}{vehicle?.unit_number ? ` · Unit #${vehicle.unit_number}` : ''}</span> — no need to pick a vehicle.</>
            ) : vehicles.length > 1 ? (
              'Choose the vehicle during scheduling.'
            ) : (
              'Choose a service now; you can add a vehicle during scheduling.'
            )}
          </p>
        </div>
        <label className="relative block w-full lg:w-[250px]">
          <span className="sr-only">Search services</span>
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[#5c6375]" />
          <input
            value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder={`Search ${services.length} services…`}
            className="h-11 w-full rounded-[10px] border border-[#272d3d] bg-[#161a26] pl-10 pr-3 text-base text-[#eceef4] outline-none placeholder:text-[#5c6375] focus:border-[#8b7cf7] focus:ring-2 focus:ring-[#8b7cf7]/35 lg:h-10 lg:text-[13px]"
          />
        </label>
      </header>

      <div className="-mx-4 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
        <div className="flex min-w-max gap-2">
          <Pill active={selectedCategory === null} onClick={() => setSelectedCategory(null)}>All {services.length}</Pill>
          {categories.map(category => {
            const count = services.filter(service => service.category_id === category.id).length
            if (!count) return null
            return (
              <Pill key={category.id} active={selectedCategory === category.id} onClick={() => setSelectedCategory(category.id)}>
                {shortCategoryName(category.name)} {count}
              </Pill>
            )
          })}
        </div>
      </div>

      <div className="space-y-4">
        {groups.map(group => (
          <section key={group.id}>
            <div className="mb-2 flex items-center gap-2.5">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: group.color }} />
              <h2 className="text-[11px] font-extrabold uppercase tracking-[0.1em]">{group.name}</h2>
              <span className="text-[11px] text-[#5c6375]">
                {formatMoney(group.min)}{group.max !== group.min ? ` – ${formatMoney(group.max)}` : ''}
              </span>
            </div>
            <div className="grid gap-2 lg:grid-cols-2">
              {group.items.map(service => (
                <article key={service.id} className="flex items-center gap-3 rounded-xl border border-[#232939] bg-[#161a26] p-3 hover:border-[#343b52] sm:gap-3.5 sm:px-3.5">
                  <div className="min-w-0 flex-1">
                    <h3 className="truncate text-[13px] font-bold">{service.name}</h3>
                    <p className="mt-1 truncate text-[11px] text-[#8b92a5]">{service.description || 'Professional heavy-duty service'}</p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-sm font-extrabold tabular-nums">{formatMoney(service.computed_total_price)}</p>
                    <p className="mt-0.5 text-[11px] text-[#5c6375]">{service.duration_minutes} min</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => navigate(`/portal/book/${service.id}`)}
                    className="h-[38px] shrink-0 rounded-lg border border-[#8b7cf7] bg-[#8b7cf7]/10 px-3.5 text-xs font-extrabold text-[#c9bfff] hover:bg-[#8b7cf7]/15 sm:h-[34px]"
                  >
                    Book
                  </button>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>

      {groups.length === 0 && (
        <div className="rounded-2xl border border-[#232939] bg-[#161a26] py-12 text-center">
          <Wrench className="mx-auto h-9 w-9 text-[#5c6375]" />
          <h2 className="mt-3 font-extrabold">No services found</h2>
          <p className="mt-1 text-sm text-[#8b92a5]">Try a different search or category.</p>
        </div>
      )}
    </div>
  )
}
