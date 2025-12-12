import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import { InventoryItem } from '../../types'

export default function InventoryPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchType, setSearchType] = useState<'all' | 'sku' | 'name' | 'category'>('all')
  const [showLowStock, setShowLowStock] = useState(false)

  const { data: inventory, isLoading } = useQuery<InventoryItem[]>({
    queryKey: ['inventory'],
    queryFn: async () => {
      const response = await api.get('/inventory')
      return response.data
    },
  })

  const filteredInventory = useMemo(() => {
    if (!inventory) return inventory

    let filtered = inventory

    // Filter low stock
    if (showLowStock) {
      filtered = filtered.filter((item) => item.stock_quantity <= item.reorder_level)
    }

    // Filter by search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim()
      filtered = filtered.filter((item) => {
        const skuMatch = item.sku.toLowerCase().includes(query)
        const nameMatch = item.name.toLowerCase().includes(query)
        const categoryMatch = item.category?.toLowerCase().includes(query)

        switch (searchType) {
          case 'sku':
            return skuMatch
          case 'name':
            return nameMatch
          case 'category':
            return categoryMatch
          default:
            return skuMatch || nameMatch || categoryMatch
        }
      })
    }

    return filtered
  }, [inventory, searchQuery, searchType, showLowStock])

  if (isLoading) {
    return <div className="text-white">Loading...</div>
  }

  const getStockStatus = (item: InventoryItem) => {
    if (item.stock_quantity === 0) {
      return { label: 'Out of Stock', bg: 'bg-red-100', text: 'text-red-700' }
    }
    if (item.stock_quantity <= item.reorder_level) {
      return { label: 'Low Stock', bg: 'bg-yellow-100', text: 'text-yellow-700' }
    }
    return { label: 'In Stock', bg: 'bg-green-100', text: 'text-green-700' }
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 sm:mb-6">
        <h1 className="text-xl sm:text-2xl font-bold text-white">Inventory</h1>
        <button className="mt-3 sm:mt-0 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg transition-colors">
          + Add Part
        </button>
      </div>

      {/* Search Bar */}
      <div className="mb-6 bg-white/10 backdrop-blur rounded-xl p-4">
        <div className="flex flex-col sm:flex-row gap-3">
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
              placeholder="Search parts..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 bg-white rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>

          <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
            <div className="flex gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
              {[
                { value: 'all', label: 'All' },
                { value: 'sku', label: 'SKU' },
                { value: 'name', label: 'Name' },
                { value: 'category', label: 'Category' },
              ].map((filter) => (
                <button
                  key={filter.value}
                  onClick={() => setSearchType(filter.value as typeof searchType)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                    searchType === filter.value
                      ? 'bg-amber-500 text-white'
                      : 'bg-white/20 text-white hover:bg-white/30 active:bg-white/40'
                  }`}
                >
                  {filter.label}
                </button>
              ))}
              <button
                onClick={() => setShowLowStock(!showLowStock)}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                  showLowStock
                    ? 'bg-red-500 text-white'
                    : 'bg-white/20 text-white hover:bg-white/30 active:bg-white/40'
                }`}
              >
                ⚠️ Low Stock
              </button>
            </div>
          </div>
        </div>

        {(searchQuery || showLowStock) && (
          <div className="mt-3 text-sm text-white/70">
            Found {filteredInventory?.length || 0} item{filteredInventory?.length !== 1 ? 's' : ''}
          </div>
        )}
      </div>
      
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {filteredInventory?.map((item) => {
          const stockStatus = getStockStatus(item)
          return (
            <div 
              key={item.id}
              className="aspect-square bg-gradient-to-br from-yellow-50 via-amber-100 to-yellow-200 p-4 sm:p-5 rounded-xl shadow-lg flex flex-col justify-between hover:shadow-xl transition-shadow cursor-pointer"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-mono text-slate-500 bg-white/50 px-2 py-0.5 rounded">
                    {item.sku}
                  </span>
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${stockStatus.bg} ${stockStatus.text}`}>
                    {stockStatus.label}
                  </span>
                </div>
                <h3 className="text-base font-bold text-slate-800 leading-tight line-clamp-2">
                  {item.name}
                </h3>
                {item.category && (
                  <p className="text-xs text-slate-500 mt-1">{item.category}</p>
                )}
              </div>
              
              <div className="space-y-2">
                <div className="bg-white/50 rounded-lg p-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs text-slate-500">In Stock</div>
                      <div className="text-2xl font-bold text-slate-800">{item.stock_quantity}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-slate-500">Reorder at</div>
                      <div className="text-lg font-semibold text-slate-600">{item.reorder_level}</div>
                    </div>
                  </div>
                </div>
                
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-500">Price</span>
                  <span className="font-bold text-slate-800">
                    ${parseFloat(item.selling_price).toFixed(2)}
                  </span>
                </div>
              </div>

              <div className="pt-3 border-t border-amber-200/50">
                <button className="w-full py-2 text-sm font-medium text-amber-700 hover:text-amber-900 hover:bg-amber-200/50 rounded-lg transition-colors">
                  Manage Stock →
                </button>
              </div>
            </div>
          )
        })}

        {/* Add Part Card */}
        <div 
          className="aspect-square bg-white/20 border-2 border-dashed border-white/40 p-4 sm:p-5 rounded-xl flex flex-col items-center justify-center cursor-pointer hover:bg-white/30 hover:border-white/60 transition-all"
        >
          <div className="w-12 h-12 rounded-full bg-white/30 flex items-center justify-center mb-3">
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
          </div>
          <span className="text-white font-medium">Add Part</span>
        </div>
      </div>

      {filteredInventory?.length === 0 && (searchQuery || showLowStock) && (
        <div className="text-center py-12 text-white/70">
          No parts match your filters. Try adjusting your search.
        </div>
      )}

      {(!inventory || inventory.length === 0) && !searchQuery && !showLowStock && (
        <div className="text-center py-12 text-white/70">
          No inventory found. Add your first part to get started.
        </div>
      )}
    </div>
  )
}

