import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import { Vehicle } from '../../types'

export default function VehiclesPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchType, setSearchType] = useState<'all' | 'vin' | 'name' | 'plate'>('all')

  const { data: vehicles, isLoading } = useQuery<Vehicle[]>({
    queryKey: ['vehicles'],
    queryFn: async () => {
      const response = await api.get('/vehicles')
      return response.data
    },
  })

  const filteredVehicles = useMemo(() => {
    if (!vehicles || !searchQuery.trim()) return vehicles

    const query = searchQuery.toLowerCase().trim()
    
    return vehicles.filter((vehicle) => {
      const vinMatch = vehicle.vin?.toLowerCase().includes(query)
      const nameMatch = `${vehicle.year} ${vehicle.make} ${vehicle.model}`.toLowerCase().includes(query)
      const plateMatch = vehicle.license_plate?.toLowerCase().includes(query)

      switch (searchType) {
        case 'vin':
          return vinMatch
        case 'name':
          return nameMatch
        case 'plate':
          return plateMatch
        default:
          return vinMatch || nameMatch || plateMatch
      }
    })
  }, [vehicles, searchQuery, searchType])

  if (isLoading) {
    return <div className="text-white">Loading...</div>
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 sm:mb-6">
        <h1 className="text-xl sm:text-2xl font-bold text-white">Vehicles</h1>
        <button className="mt-3 sm:mt-0 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg transition-colors">
          + Add Vehicle
        </button>
      </div>

      {/* Search Bar */}
      <div className="mb-6 bg-white/10 backdrop-blur rounded-xl p-4">
        <div className="flex flex-col sm:flex-row gap-3">
          {/* Search Input */}
          <div className="flex-1 relative">
            <svg 
              className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" 
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search vehicles..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 bg-white rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>

          {/* Filter Buttons */}
          <div className="flex gap-2 flex-wrap sm:flex-nowrap">
            {[
              { value: 'all', label: 'All' },
              { value: 'name', label: 'Name' },
              { value: 'vin', label: 'VIN' },
              { value: 'plate', label: 'Plate' },
            ].map((filter) => (
              <button
                key={filter.value}
                onClick={() => setSearchType(filter.value as typeof searchType)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  searchType === filter.value
                    ? 'bg-amber-500 text-white'
                    : 'bg-white/20 text-white hover:bg-white/30'
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>

        {/* Search Results Count */}
        {searchQuery && (
          <div className="mt-3 text-sm text-white/70">
            Found {filteredVehicles?.length || 0} vehicle{filteredVehicles?.length !== 1 ? 's' : ''}
            {searchType !== 'all' && ` matching ${searchType.toUpperCase()}`}
          </div>
        )}
      </div>
      
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {filteredVehicles?.map((vehicle) => (
          <div 
            key={vehicle.id}
            className="aspect-square bg-gradient-to-br from-yellow-50 via-amber-100 to-yellow-200 p-4 sm:p-5 rounded-xl shadow-lg flex flex-col justify-between hover:shadow-xl transition-shadow cursor-pointer"
          >
            <div>
              <div className="text-xs font-medium text-amber-600 uppercase tracking-wide mb-1">
                {vehicle.year}
              </div>
              <h3 className="text-lg font-bold text-slate-800 leading-tight">
                {vehicle.make}
              </h3>
              <p className="text-slate-600 font-medium">{vehicle.model}</p>
            </div>
            
            <div className="space-y-2 text-sm">
              {vehicle.license_plate && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Plate</span>
                  <span className="font-semibold text-slate-700">{vehicle.license_plate}</span>
                </div>
              )}
              {vehicle.mileage && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Mileage</span>
                  <span className="font-semibold text-slate-700">{vehicle.mileage.toLocaleString()} mi</span>
                </div>
              )}
              {vehicle.color && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Color</span>
                  <span className="font-semibold text-slate-700">{vehicle.color}</span>
                </div>
              )}
              {vehicle.vin && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">VIN</span>
                  <span className="font-mono text-xs text-slate-600 truncate max-w-24">{vehicle.vin}</span>
                </div>
              )}
            </div>

            <div className="pt-3 border-t border-amber-200/50">
              <button className="w-full py-2 text-sm font-medium text-amber-700 hover:text-amber-900 hover:bg-amber-200/50 rounded-lg transition-colors">
                View Details →
              </button>
            </div>
          </div>
        ))}

        {/* Add Vehicle Card */}
        <div 
          className="aspect-square bg-white/20 border-2 border-dashed border-white/40 p-4 sm:p-5 rounded-xl flex flex-col items-center justify-center cursor-pointer hover:bg-white/30 hover:border-white/60 transition-all"
        >
          <div className="w-12 h-12 rounded-full bg-white/30 flex items-center justify-center mb-3">
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
          </div>
          <span className="text-white font-medium">Add Vehicle</span>
        </div>
      </div>

      {filteredVehicles?.length === 0 && searchQuery && (
        <div className="text-center py-12 text-white/70">
          No vehicles match your search. Try a different term.
        </div>
      )}

      {(!vehicles || vehicles.length === 0) && !searchQuery && (
        <div className="text-center py-12 text-white/70">
          No vehicles found. Add your first vehicle to get started.
        </div>
      )}
    </div>
  )
}
