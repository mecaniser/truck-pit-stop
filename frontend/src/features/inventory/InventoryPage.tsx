import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { InventoryItem } from '../../types'
import { ArrowRight, Plus, LayoutGrid, Rows, X, Loader2 } from 'lucide-react'
import BaseSelect from '../../components/BaseSelect'
import MapboxAddressInput from '@/components/MapboxAddressInput'
import { formatUSPhone } from '../../utils/phone'
type SupplierOption = { name: string; address?: string }

export default function InventoryPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchType, setSearchType] = useState<'all' | 'sku' | 'name' | 'category'>('all')
  const [showLowStock, setShowLowStock] = useState(false)
  const [viewMode, setViewMode] = useState<'cards' | 'list'>('list')
  const [selectedItem, setSelectedItem] = useState<InventoryItem | null>(null)
  const [supplierOptions, setSupplierOptions] = useState<SupplierOption[]>([
    { name: 'Dealership' },
    { name: 'NAPA' },
    { name: 'AutoZone' },
    { name: "O'Reilly Auto Parts" },
    { name: 'Advance Auto Parts' },
    { name: 'CarQuest' },
    { name: 'Pep Boys' },
    { name: 'RockAuto' },
    { name: 'Local Yard' },
  ])
  const [addingSupplier, setAddingSupplier] = useState(false)
  const [newSupplier, setNewSupplier] = useState('')
  const [newSupplierAddress, setNewSupplierAddress] = useState('')
  const [newSupplierPhone, setNewSupplierPhone] = useState('')
  const [manageForm, setManageForm] = useState({
    stock_quantity: '',
    reorder_level: '',
    cost: '',
    selling_price: '',
    supplier_name: '',
    supplier_contact: '',
  })
  const [error, setError] = useState<string | null>(null)

  const mobileToggleClass = (mode: 'cards' | 'list') =>
    `flex items-center gap-1 px-3 py-1 rounded-md text-sm font-medium transition ${
      viewMode === mode ? 'bg-amber-500 text-white' : 'text-white hover:bg-white/20'
    }`

  const desktopToggleClass = (mode: 'cards' | 'list') =>
    `flex items-center gap-1 px-3 py-1.5 rounded-md text-sm font-semibold transition ${
      viewMode === mode ? 'bg-amber-500 text-white shadow' : 'text-gray-700 hover:bg-gray-100'
    }`

  const queryClient = useQueryClient()

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

  useEffect(() => {
    if (selectedItem) {
      setManageForm({
        stock_quantity: String(selectedItem.stock_quantity ?? ''),
        reorder_level: String(selectedItem.reorder_level ?? ''),
        cost: selectedItem.cost ? String(selectedItem.cost) : '',
        selling_price: selectedItem.selling_price ? String(selectedItem.selling_price) : '',
        supplier_name: selectedItem.supplier_name || '',
        supplier_contact: selectedItem.supplier_contact || '',
      })
      setError(null)
    }
  }, [selectedItem])

  const getStockStatus = (item: InventoryItem) => {
    if (item.stock_quantity === 0) {
      return {
        label: 'Out of Stock',
        bg: 'bg-red-100',
        text: 'text-red-700',
        surface: 'bg-red-50',
        border: 'border border-red-100',
      }
    }
    if (item.stock_quantity <= item.reorder_level) {
      return {
        label: 'Low Stock',
        bg: 'bg-yellow-100',
        text: 'text-yellow-700',
        surface: 'bg-yellow-50',
        border: 'border border-yellow-100',
      }
    }
    return {
      label: 'In Stock',
      bg: 'bg-green-100',
      text: 'text-green-700',
      surface: 'bg-green-50',
      border: 'border border-green-100',
    }
  }

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedItem) return
      const payload: Record<string, any> = {}

      const numericFields: Array<keyof typeof manageForm> = ['stock_quantity', 'reorder_level', 'cost', 'selling_price']
      numericFields.forEach((field) => {
        const value = manageForm[field]
        if (value !== '') {
          const num = Number(value)
          if (Number.isFinite(num)) {
            payload[field] = num
          }
        }
      })

      if (manageForm.supplier_name !== '') payload.supplier_name = manageForm.supplier_name
      if (manageForm.supplier_contact !== '') payload.supplier_contact = manageForm.supplier_contact

      return api.put(`/inventory/${selectedItem.id}`, payload)
    },
    onSuccess: () => {
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['inventory'] })
      setSelectedItem(null)
    },
    onError: (err: any) => {
      const message = err?.response?.data?.detail || 'Failed to update inventory'
      setError(Array.isArray(message) ? message.join(', ') : message)
    },
  })

  const openManage = (item: InventoryItem) => {
    setSelectedItem(item)
  }

  const handleManageChange = (field: keyof typeof manageForm, value: string) => {
    setManageForm((prev) => ({ ...prev, [field]: value }))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    updateMutation.mutate()
  }

  if (isLoading) {
    return <div className="text-white">Loading...</div>
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center mb-4 sm:mb-6 gap-2 sm:gap-3">
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <div className="flex items-center gap-1 bg-white/10 border border-white/15 rounded-lg p-1 lg:hidden">
            <button
              type="button"
              onClick={() => setViewMode('cards')}
              className={mobileToggleClass('cards')}
            >
              <LayoutGrid className="w-4 h-4" /> Cards
            </button>
            <button
              type="button"
              onClick={() => setViewMode('list')}
              className={mobileToggleClass('list')}
            >
              <Rows className="w-4 h-4" /> List
            </button>
          </div>
          <button className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg transition-colors lg:hidden">
            + Add Part
          </button>
        </div>
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
      
      {viewMode === 'cards' ? (
        <>
          <div className="hidden lg:flex justify-start mb-3">
            <div className="flex items-center gap-1 bg-white rounded-lg border border-gray-200 p-1 shadow-sm">
              <button
                type="button"
                onClick={() => setViewMode('cards')}
                className={desktopToggleClass('cards')}
              >
                <LayoutGrid className="w-4 h-4" /> Cards
              </button>
              <button
                type="button"
                onClick={() => setViewMode('list')}
                className={desktopToggleClass('list')}
              >
                <Rows className="w-4 h-4" /> List
              </button>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filteredInventory?.map((item) => {
              const stockStatus = getStockStatus(item)
              return (
                <div
                  key={item.id}
                  className={`aspect-square p-4 sm:p-5 rounded-xl shadow-lg flex flex-col justify-between hover:shadow-xl transition-shadow cursor-pointer ${stockStatus.surface} ${stockStatus.border}`}
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
                    <button
                      onClick={() => openManage(item)}
                      className="w-full py-2 text-sm font-medium text-amber-700 hover:text-amber-900 hover:bg-amber-200/50 rounded-lg transition-colors inline-flex items-center justify-center gap-1"
                    >
                      Manage Stock
                      <ArrowRight className="w-4 h-4" />
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
                <Plus className="w-6 h-6 text-white" />
              </div>
              <span className="text-white font-medium">Add Part</span>
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="space-y-2 lg:hidden">
            {filteredInventory?.map((item) => {
              const stockStatus = getStockStatus(item)
              return (
                <div
                  key={item.id}
                  className={`rounded-lg p-3 shadow-sm flex flex-col gap-2 ${stockStatus.surface} ${stockStatus.border}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="space-y-0.5">
                      <div className="text-sm font-semibold text-gray-900 leading-tight line-clamp-2">
                        {item.name}
                      </div>
                      <div className="text-[11px] font-mono text-gray-500">{item.sku}</div>
                      {item.category && (
                        <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-700">
                          {item.category}
                        </span>
                      )}
                    </div>
                    <span
                      className={`px-2 py-1 rounded-full text-[11px] font-semibold ${stockStatus.bg} ${stockStatus.text}`}
                    >
                      {stockStatus.label}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-xs text-gray-600 flex-wrap gap-2">
                    <div className="flex items-center gap-1">
                      <span className="text-gray-500">Stock</span>
                      <span className="font-semibold text-gray-900">{item.stock_quantity}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="text-gray-500">Reorder</span>
                      <span className="font-semibold text-gray-900">{item.reorder_level}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="text-gray-500">Cost</span>
                      <span className="font-semibold text-gray-900">${item.cost}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="text-gray-500">Price</span>
                      <span className="font-semibold text-gray-900">${item.selling_price}</span>
                    </div>
                  </div>

                  <div className="flex justify-end">
                    <button
                      onClick={() => openManage(item)}
                      className="inline-flex items-center gap-1 px-3 py-1 rounded-md text-xs font-semibold text-amber-800 bg-amber-100 hover:bg-amber-200 transition"
                    >
                      Manage
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>

          <div className="hidden lg:block rounded-xl shadow-sm border border-gray-100 bg-white/80 backdrop-blur overflow-hidden">
            <div className="overflow-x-auto overflow-y-auto max-h-[calc(100vh-260px)]">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th colSpan={9} className="px-4 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-1 bg-white rounded-md border border-gray-200 p-0.5 shadow-sm">
                          <button
                            type="button"
                            onClick={() => setViewMode('list')}
                            className={desktopToggleClass('list')}
                          >
                            <Rows className="w-4 h-4" /> List
                          </button>
                          <button
                            type="button"
                            onClick={() => setViewMode('cards')}
                            className={desktopToggleClass('cards')}
                          >
                            <LayoutGrid className="w-4 h-4" /> Cards
                          </button>
                        </div>
                        <button className="inline-flex items-center gap-1 px-3 py-2 rounded-md text-sm font-semibold text-white bg-amber-500 hover:bg-amber-600 transition-colors">
                          <Plus className="w-4 h-4" />
                          Add Part
                        </button>
                      </div>
                    </th>
                  </tr>
                  <tr className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    <th className="px-4 py-3">SKU</th>
                    <th className="px-4 py-3">Name</th>
                    <th className="px-4 py-3">Category</th>
                    <th className="px-4 py-3">Stock</th>
                    <th className="px-4 py-3">Reorder</th>
                    <th className="px-4 py-3">Cost</th>
                    <th className="px-4 py-3">Price</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 text-sm text-gray-800">
                  {filteredInventory?.map((item) => {
                    const stockStatus = getStockStatus(item)
                    return (
                      <tr key={item.id} className={`transition ${stockStatus.surface}`}>
                        <td className="px-4 py-3 font-semibold text-gray-900">{item.sku}</td>
                        <td className="px-4 py-3">
                          <div className="font-semibold text-gray-900">{item.name}</div>
                          {item.description && <div className="text-xs text-gray-500">{item.description}</div>}
                        </td>
                        <td className="px-4 py-3 text-gray-700">{item.category || 'Uncategorized'}</td>
                        <td className="px-4 py-3">{item.stock_quantity}</td>
                        <td className="px-4 py-3">{item.reorder_level}</td>
                        <td className="px-4 py-3">${item.cost}</td>
                        <td className="px-4 py-3">${item.selling_price}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-1 rounded-full text-xs font-semibold ${stockStatus.bg} ${stockStatus.text}`}>
                            {stockStatus.label}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => openManage(item)}
                            className="inline-flex items-center gap-1 px-3 py-1 rounded-md text-xs font-semibold text-amber-800 bg-amber-100 hover:bg-amber-200 transition"
                          >
                            Manage
                            <ArrowRight className="w-3 h-3" />
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

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

      <div
        className={`fixed inset-0 z-50 transition ${selectedItem ? 'pointer-events-auto' : 'pointer-events-none'}`}
        aria-hidden={!selectedItem}
      >
        <div
          className={`absolute inset-0 bg-black/50 transition-opacity ${selectedItem ? 'opacity-100' : 'opacity-0'}`}
          onClick={() => setSelectedItem(null)}
        />
        <aside
          className={`absolute top-0 right-0 h-full w-full sm:w-[520px] bg-white/95 backdrop-blur border-l border-gray-200 shadow-xl transform transition-transform ${
            selectedItem ? 'translate-x-0' : 'translate-x-full'
          }`}
          role="dialog"
          aria-label="Manage inventory"
        >
          <form className="h-full flex flex-col" onSubmit={handleSubmit}>
            <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
              <div>
                <p className="text-xs uppercase text-gray-500 font-semibold">Manage Inventory</p>
                <p className="text-lg font-semibold text-slate-800">
                  {selectedItem?.name || ''}
                </p>
                {selectedItem?.sku && <p className="text-sm text-gray-500">SKU: {selectedItem.sku}</p>}
              </div>
              <button
                type="button"
                onClick={() => setSelectedItem(null)}
                className="p-2 text-gray-500 hover:text-amber-600 rounded-full hover:bg-amber-50"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-5 space-y-4 overflow-y-auto flex-1">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="text-sm text-gray-700 space-y-1">
                  <span>Stock Quantity</span>
                  <input
                    type="number"
                    value={manageForm.stock_quantity}
                    onChange={(e) => handleManageChange('stock_quantity', e.target.value)}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                  />
                </label>
                <label className="text-sm text-gray-700 space-y-1">
                  <span>Reorder Level</span>
                  <input
                    type="number"
                    value={manageForm.reorder_level}
                    onChange={(e) => handleManageChange('reorder_level', e.target.value)}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                  />
                </label>
                <label className="text-sm text-gray-700 space-y-1">
                  <span>Cost</span>
                  <input
                    type="number"
                    step="0.01"
                    value={manageForm.cost}
                    onChange={(e) => handleManageChange('cost', e.target.value)}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                  />
                </label>
                <label className="text-sm text-gray-700 space-y-1">
                  <span>Selling Price</span>
                  <input
                    type="number"
                    step="0.01"
                    value={manageForm.selling_price}
                    onChange={(e) => handleManageChange('selling_price', e.target.value)}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                  />
                </label>
              </div>

              <div className="space-y-2">
                <label className="text-sm text-gray-700 space-y-1 block">
                  <span>Supplier Name</span>
                  <BaseSelect
                    options={supplierOptions.map((opt) => ({
                      value: opt.name,
                      label: opt.name,
                      subLabel: opt.address || 'Address not set',
                    }))}
                    value={manageForm.supplier_name}
                    onChange={(val) => {
                      if (val === 'add_new') return
                      handleManageChange('supplier_name', val)
                    }}
                    placeholder="Select a supplier"
                    allowAddNew
                    addNewLabel="+ Add supplier"
                    onAddNew={() => setAddingSupplier(true)}
                  />
                  <div className="text-[12px] text-amber-700 font-semibold mt-1">
                    <button
                      type="button"
                      onClick={() => setAddingSupplier(true)}
                      className="hover:underline"
                    >
                      + Add supplier
                    </button>
                  </div>
                </label>

                {addingSupplier && (
                  <div className="space-y-2 rounded-lg border border-gray-200 p-3 bg-gray-50">
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={newSupplier}
                        onChange={(e) => setNewSupplier(e.target.value)}
                        className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
                        placeholder="Add supplier name"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          const trimmed = newSupplier.trim()
                          if (!trimmed) return
                          const exists = supplierOptions.some(
                            (s) => s.name.toLowerCase() === trimmed.toLowerCase()
                          )
                          if (!exists) {
                            setSupplierOptions((prev) => [
                              ...prev,
                              { name: trimmed, address: newSupplierAddress.trim() || undefined },
                            ])
                          }
                          handleManageChange('supplier_name', trimmed)
                          const contactParts = [newSupplierAddress.trim(), newSupplierPhone.trim()].filter(Boolean)
                          if (contactParts.length) {
                            handleManageChange('supplier_contact', contactParts.join(' | '))
                          }
                          setNewSupplier('')
                          setNewSupplierAddress('')
                          setNewSupplierPhone('')
                          setAddingSupplier(false)
                        }}
                        className="px-3 py-2 rounded-lg text-sm font-semibold text-white bg-amber-500 hover:bg-amber-600"
                      >
                        Add
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setNewSupplier('')
                          setNewSupplierAddress('')
                          setNewSupplierPhone('')
                          setAddingSupplier(false)
                        }}
                        className="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-100"
                      >
                        Cancel
                      </button>
                    </div>

                    <div className="space-y-1">
                      <span className="text-xs text-gray-600">Supplier address (saved into contact)</span>
                      <MapboxAddressInput
                        value={newSupplierAddress}
                        onChange={(e) => setNewSupplierAddress(e.target.value)}
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
                        placeholder="Search address"
                        onAddressSelect={({ formatted }) => setNewSupplierAddress(formatted || '')}
                      />
                      <input
                        type="text"
                        value={newSupplierPhone}
                        onChange={(e) => setNewSupplierPhone(formatUSPhone(e.target.value))}
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
                        placeholder="Phone (optional)"
                      />
                    </div>
                  </div>
                )}
              </div>

              <label className="text-sm text-gray-700 space-y-1 block">
                <span>Supplier Contact</span>
                <input
                  type="text"
                  value={manageForm.supplier_contact}
                  onChange={(e) => handleManageChange('supplier_contact', e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                  placeholder="Optional"
                />
              </label>

              {error && <div className="text-sm text-red-600">{error}</div>}
            </div>

            <div className="px-5 py-4 border-t border-gray-200 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setSelectedItem(null)}
                className="px-4 py-2 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-100"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!selectedItem || updateMutation.isPending}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-amber-500 hover:bg-amber-600 disabled:opacity-70"
              >
                {updateMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                Save Changes
              </button>
            </div>
          </form>
        </aside>
      </div>
    </div>
  )
}
