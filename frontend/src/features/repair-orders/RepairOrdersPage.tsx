import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import { RepairOrder } from '../../types'
import { format } from 'date-fns'

export default function RepairOrdersPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')

  const { data: orders, isLoading } = useQuery<RepairOrder[]>({
    queryKey: ['repair-orders'],
    queryFn: async () => {
      const response = await api.get('/repair-orders')
      return response.data
    },
  })

  const filteredOrders = useMemo(() => {
    if (!orders) return orders

    let filtered = orders

    // Filter by status
    if (statusFilter !== 'all') {
      filtered = filtered.filter((order) => order.status === statusFilter)
    }

    // Filter by search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim()
      filtered = filtered.filter((order) => 
        order.order_number.toLowerCase().includes(query) ||
        order.description?.toLowerCase().includes(query)
      )
    }

    return filtered
  }, [orders, searchQuery, statusFilter])

  if (isLoading) {
    return <div className="text-white">Loading...</div>
  }

  const getStatusStyle = (status: string) => {
    const styles: Record<string, { bg: string; text: string; dot: string }> = {
      draft: { bg: 'bg-gray-100', text: 'text-gray-700', dot: 'bg-gray-400' },
      quoted: { bg: 'bg-blue-100', text: 'text-blue-700', dot: 'bg-blue-500' },
      approved: { bg: 'bg-green-100', text: 'text-green-700', dot: 'bg-green-500' },
      in_progress: { bg: 'bg-yellow-100', text: 'text-yellow-700', dot: 'bg-yellow-500' },
      completed: { bg: 'bg-purple-100', text: 'text-purple-700', dot: 'bg-purple-500' },
      invoiced: { bg: 'bg-indigo-100', text: 'text-indigo-700', dot: 'bg-indigo-500' },
      paid: { bg: 'bg-emerald-100', text: 'text-emerald-700', dot: 'bg-emerald-500' },
      cancelled: { bg: 'bg-red-100', text: 'text-red-700', dot: 'bg-red-500' },
    }
    return styles[status] || styles.draft
  }

  const statusOptions = [
    { value: 'all', label: 'All' },
    { value: 'in_progress', label: 'In Progress' },
    { value: 'quoted', label: 'Quoted' },
    { value: 'approved', label: 'Approved' },
    { value: 'completed', label: 'Completed' },
    { value: 'paid', label: 'Paid' },
  ]

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 sm:mb-6">
        <h1 className="text-xl sm:text-2xl font-bold text-white">Repair Orders</h1>
        <button className="mt-3 sm:mt-0 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg transition-colors">
          + New Repair Order
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
              placeholder="Search by order # or description..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 bg-white rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>

          <div className="flex gap-2 flex-wrap">
            {statusOptions.map((option) => (
              <button
                key={option.value}
                onClick={() => setStatusFilter(option.value)}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  statusFilter === option.value
                    ? 'bg-amber-500 text-white'
                    : 'bg-white/20 text-white hover:bg-white/30'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {(searchQuery || statusFilter !== 'all') && (
          <div className="mt-3 text-sm text-white/70">
            Found {filteredOrders?.length || 0} order{filteredOrders?.length !== 1 ? 's' : ''}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {filteredOrders?.map((order) => {
          const statusStyle = getStatusStyle(order.status)
          return (
            <div 
              key={order.id}
              className="aspect-square bg-gradient-to-br from-yellow-50 via-amber-100 to-yellow-200 p-4 sm:p-5 rounded-xl shadow-lg flex flex-col justify-between hover:shadow-xl transition-shadow cursor-pointer"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-mono text-slate-500">
                    {order.order_number}
                  </span>
                  <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${statusStyle.bg} ${statusStyle.text}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${statusStyle.dot}`}></span>
                    {order.status.replace('_', ' ')}
                  </span>
                </div>
                <p className="text-sm text-slate-700 line-clamp-3 leading-relaxed">
                  {order.description}
                </p>
              </div>
              
              <div className="space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-500">
                    {format(new Date(order.created_at), 'MMM d, yyyy')}
                  </span>
                </div>
                
                <div className="bg-white/50 rounded-lg p-3">
                  <div className="text-xs text-slate-500 mb-1">Total Cost</div>
                  <div className="text-xl font-bold text-slate-800">
                    ${parseFloat(order.total_cost).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </div>
                </div>
              </div>

              <div className="pt-3 border-t border-amber-200/50">
                <button className="w-full py-2 text-sm font-medium text-amber-700 hover:text-amber-900 hover:bg-amber-200/50 rounded-lg transition-colors">
                  View Details →
                </button>
              </div>
            </div>
          )
        })}

        <div 
          className="aspect-square bg-white/20 border-2 border-dashed border-white/40 p-4 sm:p-5 rounded-xl flex flex-col items-center justify-center cursor-pointer hover:bg-white/30 hover:border-white/60 transition-all"
        >
          <div className="w-12 h-12 rounded-full bg-white/30 flex items-center justify-center mb-3">
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
          </div>
          <span className="text-white font-medium">New Repair Order</span>
        </div>
      </div>

      {filteredOrders?.length === 0 && (searchQuery || statusFilter !== 'all') && (
        <div className="text-center py-12 text-white/70">
          No repair orders match your filters. Try adjusting your search.
        </div>
      )}

      {(!orders || orders.length === 0) && !searchQuery && statusFilter === 'all' && (
        <div className="text-center py-12 text-white/70">
          No repair orders found. Create your first repair order to get started.
        </div>
      )}
    </div>
  )
}
