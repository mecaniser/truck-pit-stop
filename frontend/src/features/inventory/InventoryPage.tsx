import { useState, useMemo, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import api from '../../lib/api'
import { InventoryItem, Supplier } from '../../types'
import { ArrowRight, Download, PackageCheck, Pencil, Plus, Settings, Trash2 } from 'lucide-react'
import SlidePanelForm from '@/components/SlidePanelForm'
import BaseSelect from '../../components/BaseSelect'
import CurrencyInput from '../../components/CurrencyInput'
import MapboxAddressInput from '@/components/MapboxAddressInput'
import SearchAddBar from '@/components/SearchAddBar'
import ViewToggle from '@/components/ViewToggle'
import { formatUSPhone } from '../../utils/phone'
import { useViewPreference } from '@/hooks/useViewPreference'
import { useTheme } from '../../contexts/ThemeContext'

export default function InventoryPage() {
  const { accentColors } = useTheme()
  const [searchParams, setSearchParams] = useSearchParams()
  const [searchQuery, setSearchQuery] = useState('')
  const [searchType, setSearchType] = useState<'all' | 'sku' | 'name' | 'category'>('all')
  const [showLowStock, setShowLowStock] = useState(false)
  const [stockSort, setStockSort] = useState<'none' | 'low-high' | 'high-low'>('none')
  const [viewMode, setViewMode] = useViewPreference('inventory')
  const [selectedItem, setSelectedItem] = useState<InventoryItem | null>(null)
  const [isAddingPart, setIsAddingPart] = useState(false)
  const [addForm, setAddForm] = useState({
    sku: '',
    name: '',
    description: '',
    category: '',
    stock_quantity: '',
    reorder_level: '',
    cost: '',
    selling_price: '',
    supplier_name: '',
    supplier_contact: '',
  })
  const [addError, setAddError] = useState<string | null>(null)
  const [addingSupplierInManage, setAddingSupplierInManage] = useState(false)
  const [addingSupplierInAdd, setAddingSupplierInAdd] = useState(false)
  const [newSupplierForm, setNewSupplierForm] = useState({
    name: '',
    address: '',
    phone: '',
    contact_name: '',
  })
  const [manageForm, setManageForm] = useState({
    sku: '',
    name: '',
    category: '',
    description: '',
    stock_quantity: '',
    on_order_quantity: '',
    reorder_level: '',
    cost: '',
    selling_price: '',
    supplier_name: '',
    supplier_contact: '',
  })
  const [editingIdentity, setEditingIdentity] = useState(false)
  const [receiveQty, setReceiveQty] = useState('')
  const [receiveMessage, setReceiveMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const [showMenu, setShowMenu] = useState(false)
  const [catalogMessage, setCatalogMessage] = useState<string | null>(null)
  const mobileMenuRef = useRef<HTMLDivElement>(null)
  const desktopMenuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!showMenu) return
    const handler = (e: MouseEvent) => {
      const target = e.target as Node
      if (
        (mobileMenuRef.current?.contains(target)) ||
        (desktopMenuRef.current?.contains(target))
      ) return
      setShowMenu(false)
      setShowClearConfirm(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showMenu])

  const queryClient = useQueryClient()

  const { data: inventory, isLoading } = useQuery<InventoryItem[]>({
    queryKey: ['inventory'],
    queryFn: async () => {
      const response = await api.get('/inventory')
      return response.data
    },
  })

  const { data: suppliers } = useQuery<Supplier[]>({
    queryKey: ['suppliers'],
    queryFn: async () => {
      const response = await api.get('/suppliers')
      return response.data
    },
  })

  // Handle ?selected= query param to auto-open an inventory item
  useEffect(() => {
    const selectedId = searchParams.get('selected')
    if (selectedId && inventory) {
      const item = inventory.find(i => i.id === selectedId)
      if (item) {
        setSelectedItem(item)
        // Clear the query param after opening
        setSearchParams({}, { replace: true })
      }
    }
  }, [searchParams, inventory, setSearchParams])

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

    // Sort by stock
    if (stockSort !== 'none') {
      filtered = [...filtered].sort((a, b) => {
        // Get stock status priority: out of stock (0) < low stock (1) < in stock (2)
        const getStatusPriority = (item: InventoryItem) => {
          if (item.stock_quantity === 0) return 0
          if (item.stock_quantity <= item.reorder_level) return 1
          return 2
        }

        const aPriority = getStatusPriority(a)
        const bPriority = getStatusPriority(b)

        if (stockSort === 'low-high') {
          // First by status (out → low → in), then by quantity within status
          if (aPriority !== bPriority) return aPriority - bPriority
          return a.stock_quantity - b.stock_quantity
        }
        // high-low: reverse
        if (aPriority !== bPriority) return bPriority - aPriority
        return b.stock_quantity - a.stock_quantity
      })
    }

    return filtered
  }, [inventory, searchQuery, searchType, showLowStock, stockSort])

  const searchFilters = [
    { value: 'all', label: 'All' },
    { value: 'sku', label: 'SKU' },
    { value: 'name', label: 'Name' },
    { value: 'category', label: 'Category' },
  ] as const

  useEffect(() => {
    if (selectedItem) {
      setManageForm({
        sku: selectedItem.sku || '',
        name: selectedItem.name || '',
        category: selectedItem.category || '',
        description: selectedItem.description || '',
        stock_quantity: String(selectedItem.stock_quantity ?? ''),
        on_order_quantity: String(selectedItem.on_order_quantity ?? ''),
        reorder_level: String(selectedItem.reorder_level ?? ''),
        cost: selectedItem.cost ? String(selectedItem.cost) : '',
        selling_price: selectedItem.selling_price ? String(selectedItem.selling_price) : '',
        supplier_name: selectedItem.supplier_name || '',
        supplier_contact: selectedItem.supplier_contact || '',
      })
      setEditingIdentity(false)
      setReceiveQty('')
      setReceiveMessage(null)
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

      // Quantity fields: an empty input means "set to 0" so users can clear stock back to none.
      // Money fields: an empty input means "leave as-is" to avoid accidentally zeroing prices.
      const quantityFields: Array<keyof typeof manageForm> = ['stock_quantity', 'on_order_quantity', 'reorder_level']
      const moneyFields: Array<keyof typeof manageForm> = ['cost', 'selling_price']
      quantityFields.forEach((field) => {
        const raw = manageForm[field]
        const num = raw === '' ? 0 : Number(raw)
        if (Number.isFinite(num)) {
          payload[field] = num
        }
      })
      moneyFields.forEach((field) => {
        const raw = manageForm[field]
        if (raw !== '') {
          const num = Number(raw)
          if (Number.isFinite(num)) {
            payload[field] = num
          }
        }
      })

      if (editingIdentity) {
        const trimmedSku = manageForm.sku.trim()
        const trimmedName = manageForm.name.trim()
        if (!trimmedSku) throw new Error('SKU cannot be empty')
        if (!trimmedName) throw new Error('Name cannot be empty')
        if (trimmedSku !== selectedItem.sku) payload.sku = trimmedSku
        if (trimmedName !== selectedItem.name) payload.name = trimmedName
        const trimmedCategory = manageForm.category.trim()
        if (trimmedCategory !== (selectedItem.category || '')) {
          payload.category = trimmedCategory || null
        }
        const trimmedDescription = manageForm.description.trim()
        if (trimmedDescription !== (selectedItem.description || '')) {
          payload.description = trimmedDescription || null
        }
      }

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
      const message = err?.message || err?.response?.data?.detail || 'Failed to update inventory'
      setError(Array.isArray(message) ? message.join(', ') : message)
    },
  })

  const receiveShipmentMutation = useMutation({
    mutationFn: async () => {
      if (!selectedItem) return
      const qty = Number(receiveQty)
      if (!Number.isFinite(qty) || qty <= 0) {
        throw new Error('Enter a quantity greater than zero')
      }
      const response = await api.post(`/inventory/${selectedItem.id}/receive`, { quantity: qty })
      return response.data as InventoryItem
    },
    onSuccess: (updated) => {
      if (!updated) return
      queryClient.invalidateQueries({ queryKey: ['inventory'] })
      setSelectedItem(updated)
      setManageForm((prev) => ({
        ...prev,
        stock_quantity: String(updated.stock_quantity ?? ''),
        on_order_quantity: String(updated.on_order_quantity ?? ''),
      }))
      setReceiveMessage(`Received ${receiveQty} into stock`)
      setReceiveQty('')
      setTimeout(() => setReceiveMessage(null), 3000)
    },
    onError: (err: any) => {
      const message = err?.message || err?.response?.data?.detail || 'Failed to receive shipment'
      setError(Array.isArray(message) ? message.join(', ') : message)
    },
  })

  const createMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, any> = {
        sku: addForm.sku.trim(),
        name: addForm.name.trim(),
        cost: Number(addForm.cost) || 0,
        selling_price: Number(addForm.selling_price) || 0,
      }

      if (addForm.description.trim()) payload.description = addForm.description.trim()
      if (addForm.category.trim()) payload.category = addForm.category.trim()
      if (addForm.stock_quantity !== '') payload.stock_quantity = Number(addForm.stock_quantity)
      if (addForm.reorder_level !== '') payload.reorder_level = Number(addForm.reorder_level)
      if (addForm.supplier_name.trim()) payload.supplier_name = addForm.supplier_name.trim()
      if (addForm.supplier_contact.trim()) payload.supplier_contact = addForm.supplier_contact.trim()

      return api.post('/inventory', payload)
    },
    onSuccess: () => {
      setAddError(null)
      queryClient.invalidateQueries({ queryKey: ['inventory'] })
      setIsAddingPart(false)
      setAddForm({
        sku: '',
        name: '',
        description: '',
        category: '',
        stock_quantity: '',
        reorder_level: '',
        cost: '',
        selling_price: '',
        supplier_name: '',
        supplier_contact: '',
      })
    },
    onError: (err: any) => {
      const message = err?.response?.data?.detail || 'Failed to add part'
      setAddError(Array.isArray(message) ? message.join(', ') : message)
    },
  })

  const createSupplierMutation = useMutation({
    mutationFn: async (target: 'manage' | 'add') => {
      const payload = {
        name: newSupplierForm.name.trim(),
        address: newSupplierForm.address.trim() || undefined,
        phone: newSupplierForm.phone.trim() || undefined,
        contact_name: newSupplierForm.contact_name.trim() || undefined,
      }
      const response = await api.post('/suppliers', payload)
      return { supplier: response.data as Supplier, target }
    },
    onSuccess: ({ supplier, target }) => {
      queryClient.invalidateQueries({ queryKey: ['suppliers'] })
      // Auto-select the new supplier and populate contact
      const contactParts = [supplier.phone, supplier.address].filter(Boolean)
      if (target === 'manage') {
        handleManageChange('supplier_name', supplier.name)
        if (contactParts.length) handleManageChange('supplier_contact', contactParts.join(' | '))
        setAddingSupplierInManage(false)
      } else {
        handleAddFormChange('supplier_name', supplier.name)
        if (contactParts.length) handleAddFormChange('supplier_contact', contactParts.join(' | '))
        setAddingSupplierInAdd(false)
      }
      setNewSupplierForm({ name: '', address: '', phone: '', contact_name: '' })
    },
    onError: (err: any) => {
      const message = err?.response?.data?.detail || 'Failed to add supplier'
      // Show error in the appropriate form
      if (err.target === 'manage') {
        setError(Array.isArray(message) ? message.join(', ') : message)
      } else {
        setAddError(Array.isArray(message) ? message.join(', ') : message)
      }
    },
  })

  const preloadInventoryMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/inventory/preload')
      return response.data as { items_added: number }
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['inventory'] })
      const msg = data.items_added === 0
        ? 'Already up to date — no new parts added'
        : `Added ${data.items_added} part${data.items_added !== 1 ? 's' : ''} to inventory`
      setCatalogMessage(msg)
      setTimeout(() => setCatalogMessage(null), 4000)
    },
  })

  const clearInventoryMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/inventory/clear')
      return response.data as { items_deleted: number }
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['inventory'] })
      setShowClearConfirm(false)
      setCatalogMessage(`Cleared ${data.items_deleted} part${data.items_deleted !== 1 ? 's' : ''}`)
      setTimeout(() => setCatalogMessage(null), 4000)
    },
  })

  const handleNewSupplierChange = (field: keyof typeof newSupplierForm, value: string) => {
    setNewSupplierForm((prev) => ({ ...prev, [field]: value }))
  }

  const handleSelectSupplier = (supplierId: string, target: 'manage' | 'add') => {
    const supplier = suppliers?.find((s) => s.id === supplierId)
    if (!supplier) return
    const contactParts = [supplier.phone, supplier.address].filter(Boolean)
    if (target === 'manage') {
      handleManageChange('supplier_name', supplier.name)
      if (contactParts.length) handleManageChange('supplier_contact', contactParts.join(' | '))
    } else {
      handleAddFormChange('supplier_name', supplier.name)
      if (contactParts.length) handleAddFormChange('supplier_contact', contactParts.join(' | '))
    }
  }

  const openManage = (item: InventoryItem) => {
    setSelectedItem(item)
    setAddingSupplierInManage(false)
  }

  const openAddPart = () => {
    setAddForm({
      sku: '',
      name: '',
      description: '',
      category: '',
      stock_quantity: '',
      reorder_level: '',
      cost: '',
      selling_price: '',
      supplier_name: '',
      supplier_contact: '',
    })
    setAddError(null)
    setIsAddingPart(true)
  }

  const handleAddFormChange = (field: keyof typeof addForm, value: string) => {
    setAddForm((prev) => ({ ...prev, [field]: value }))
  }

  // Generate SKU suggestion from category + name
  const generateSkuSuggestion = (name: string, category: string): string => {
    const catTrimmed = category.trim()
    const catPrefix = catTrimmed ? catTrimmed.substring(0, 3).toUpperCase() : 'GEN'
    const catLower = catTrimmed.toLowerCase()
    
    // Extract meaningful words (letters/numbers), skip hyphens
    const words = name
      .trim()
      .split(/[\s\-_]+/)
      .filter((word) => word.length > 0)
      .map((word) => word.replace(/[^a-zA-Z0-9]/g, '')) // remove special chars
      .filter((word) => word.length > 0)
      // Filter out words that are redundant with category (e.g., "Brake" when category is "Brakes")
      .filter((word) => {
        if (!catTrimmed) return true
        const wordLower = word.toLowerCase()
        // Skip if word matches category or vice versa
        return !(catLower.startsWith(wordLower) || wordLower.startsWith(catLower.substring(0, Math.min(4, catLower.length))))
      })
    
    if (words.length === 0) return ''
    
    // Take first 3 chars of up to 3 significant words
    const nameAbbrev = words
      .slice(0, 3)
      .map((word) => {
        // If it's a number, keep it as-is (up to 3 digits)
        if (/^\d+$/.test(word)) return word.substring(0, 3)
        // Otherwise take first 3 letters
        return word.substring(0, 3).toUpperCase()
      })
      .join('-')
    
    if (!nameAbbrev) return ''
    
    // Find next sequence number for this prefix pattern
    const basePattern = `${catPrefix}-${nameAbbrev}`
    const existingWithPattern = inventory?.filter((item) =>
      item.sku.toUpperCase().startsWith(basePattern.toUpperCase())
    ) || []
    const nextNum = existingWithPattern.length + 1
    const seq = String(nextNum).padStart(3, '0')
    
    return `${basePattern}-${seq}`
  }

  // Get name suggestions from existing inventory
  const nameSuggestions = useMemo(() => {
    if (!addForm.name.trim() || addForm.name.length < 2) return []
    const query = addForm.name.toLowerCase()
    const matches = inventory?.filter((item) =>
      item.name.toLowerCase().includes(query)
    ) || []
    // Return unique names, max 5
    const uniqueNames = [...new Set(matches.map((m) => m.name))]
    return uniqueNames.slice(0, 5)
  }, [addForm.name, inventory])

  // Auto-update SKU suggestion when name or category changes
  const skuSuggestion = useMemo(() => {
    if (addForm.sku) return '' // Don't suggest if user already entered something
    return generateSkuSuggestion(addForm.name, addForm.category)
  }, [addForm.name, addForm.category, addForm.sku, inventory])

  const handleAddSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setAddError(null)
    if (!addForm.sku.trim()) {
      setAddError('SKU is required')
      return
    }
    if (!addForm.name.trim()) {
      setAddError('Name is required')
      return
    }
    if (!addForm.cost || Number(addForm.cost) < 0) {
      setAddError('Cost is required')
      return
    }
    if (!addForm.selling_price || Number(addForm.selling_price) < 0) {
      setAddError('Selling price is required')
      return
    }
    createMutation.mutate()
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
    <div className="flex flex-col gap-3 lg:h-full lg:min-h-0">
      {/* Mobile Search Bar */}
      <SearchAddBar
        value={searchQuery}
        onChange={setSearchQuery}
        placeholder="Search parts by SKU, name, or category..."
        onAdd={openAddPart}
        addLabel="Add part"
        addLabelMobile="Add"
        className="mb-1 lg:hidden"
        inputWidthClass="sm:min-w-[320px] md:max-w-xl"
      />

      {/* Catalog message (success/info) */}
      {catalogMessage && (
        <div className="flex items-center gap-2 bg-green-500/20 border border-green-500/30 text-green-400 px-4 py-2.5 rounded-lg text-sm">
          <Download className="w-4 h-4 shrink-0" />
          {catalogMessage}
        </div>
      )}

      {/* Mobile: Catalog gear menu */}
      <div className="relative lg:hidden" ref={mobileMenuRef}>
        <button
          onClick={() => setShowMenu(v => !v)}
          className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-gray-400 hover:text-gray-200 border border-white/15 transition-colors"
          title="Catalog options"
        >
          <Settings className="w-4 h-4" />
        </button>
        {showMenu && (
          <div className="absolute left-0 top-full mt-1 w-44 bg-[#1a2030] border border-white/15 rounded-lg shadow-xl z-50 overflow-hidden">
            {showClearConfirm ? (
              <div className="p-2 space-y-1">
                <p className="text-xs text-gray-400 px-2 py-1">Clear all parts?</p>
                <button
                  onClick={() => clearInventoryMutation.mutate()}
                  disabled={clearInventoryMutation.isPending}
                  className="w-full text-left px-3 py-2 text-sm text-red-400 hover:bg-white/10 rounded-md disabled:opacity-50"
                >
                  {clearInventoryMutation.isPending ? 'Clearing…' : 'Yes, clear all'}
                </button>
                <button
                  onClick={() => setShowClearConfirm(false)}
                  className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-white/10 rounded-md"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <>
                <button
                  onClick={() => { preloadInventoryMutation.mutate(); setShowMenu(false) }}
                  disabled={preloadInventoryMutation.isPending}
                  className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-gray-200 hover:bg-white/10 disabled:opacity-50"
                >
                  <Download className="w-3.5 h-3.5 shrink-0" />
                  {preloadInventoryMutation.isPending ? 'Loading…' : 'Load defaults'}
                </button>
                <button
                  onClick={() => setShowClearConfirm(true)}
                  className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-red-400 hover:bg-white/10"
                >
                  <Trash2 className="w-3.5 h-3.5 shrink-0" />
                  Clear all
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {/* Desktop Search Toolbar */}
      <div className="hidden lg:flex items-center gap-4">
        <div className="min-w-0 flex flex-1 flex-wrap items-center gap-3 xl:flex-nowrap">
          <SearchAddBar
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder="Search parts by SKU, name, or category..."
            onAdd={openAddPart}
            className="mb-0 min-w-[18rem] flex-1"
            inputWidthClass=""
            showAddButton={false}
          />

          <div className="flex shrink-0 items-center">
            <div className="inline-flex h-[42px] items-center rounded-lg border border-white/15 bg-white/10">
              {searchFilters.map((filter) => (
                <button
                  key={filter.value}
                  onClick={() => setSearchType(filter.value)}
                  className={`h-full px-4 text-sm font-medium transition-colors whitespace-nowrap ${
                    searchType === filter.value
                      ? 'text-white'
                      : 'text-white hover:bg-white/20'
                  } ${filter.value === 'all' ? 'rounded-l-lg' : ''} ${filter.value === 'category' ? 'rounded-r-lg' : ''}`}
                  style={searchType === filter.value ? { backgroundColor: accentColors[500] } : undefined}
                >
                  {filter.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={openAddPart}
          className="inline-flex h-[42px] shrink-0 items-center gap-2 rounded-lg px-4 text-sm font-semibold text-white transition-colors"
          style={{ backgroundColor: accentColors[600] }}
        >
          <Plus className="w-4 h-4" />
          Add part
        </button>

        {/* Catalog gear menu */}
        <div className="relative shrink-0" ref={desktopMenuRef}>
          <button
            onClick={() => setShowMenu(v => !v)}
            className="inline-flex h-[42px] w-[42px] items-center justify-center rounded-lg bg-white/10 hover:bg-white/20 text-gray-400 hover:text-gray-200 border border-white/15 transition-colors"
            title="Catalog options"
          >
            <Settings className="w-4 h-4" />
          </button>
          {showMenu && (
            <div className="absolute right-0 top-full mt-1 w-44 bg-[#1a2030] border border-white/15 rounded-lg shadow-xl z-50 overflow-hidden">
              {showClearConfirm ? (
                <div className="p-2 space-y-1">
                  <p className="text-xs text-gray-400 px-2 py-1">Clear all parts?</p>
                  <button
                    onClick={() => clearInventoryMutation.mutate()}
                    disabled={clearInventoryMutation.isPending}
                    className="w-full text-left px-3 py-2 text-sm text-red-400 hover:bg-white/10 rounded-md disabled:opacity-50"
                  >
                    {clearInventoryMutation.isPending ? 'Clearing…' : 'Yes, clear all'}
                  </button>
                  <button
                    onClick={() => setShowClearConfirm(false)}
                    className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-white/10 rounded-md"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <>
                  <button
                    onClick={() => { preloadInventoryMutation.mutate(); setShowMenu(false) }}
                    disabled={preloadInventoryMutation.isPending}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-gray-200 hover:bg-white/10 disabled:opacity-50"
                  >
                    <Download className="w-3.5 h-3.5 shrink-0" />
                    {preloadInventoryMutation.isPending ? 'Loading…' : 'Load defaults'}
                  </button>
                  <button
                    onClick={() => setShowClearConfirm(true)}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-red-400 hover:bg-white/10"
                  >
                    <Trash2 className="w-3.5 h-3.5 shrink-0" />
                    Clear all
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Mobile: Sort + Low stock filter */}
      <div className="flex items-center gap-2 mb-3 lg:hidden">
        <span className="text-xs text-gray-400 font-medium">Sort:</span>
        <div className="inline-flex items-center bg-white/10 border border-white/15 rounded-lg p-0.5">
          <button
            onClick={() => setStockSort('none')}
            className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
              stockSort === 'none' ? 'text-white' : 'text-white'
            }`}
            style={stockSort === 'none' ? { backgroundColor: accentColors[500] } : undefined}
          >
            Default
          </button>
          <button
            onClick={() => setStockSort('low-high')}
            className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
              stockSort === 'low-high' ? 'text-white' : 'text-white'
            }`}
            style={stockSort === 'low-high' ? { backgroundColor: accentColors[500] } : undefined}
          >
            Stock ↑
          </button>
          <button
            onClick={() => setStockSort('high-low')}
            className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
              stockSort === 'high-low' ? 'text-white' : 'text-white'
            }`}
            style={stockSort === 'high-low' ? { backgroundColor: accentColors[500] } : undefined}
          >
            Stock ↓
          </button>
        </div>
        <button
          onClick={() => setShowLowStock(!showLowStock)}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors whitespace-nowrap border ${
            showLowStock
              ? 'bg-red-500/20 text-red-300 border-red-500/40'
              : 'bg-white/10 text-white border-white/15'
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${showLowStock ? 'bg-red-400' : 'bg-yellow-400'}`} />
          Low stock
          {showLowStock && inventory && (
            <span className="ml-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-500/30 text-red-200">
              {inventory.filter((item) => item.stock_quantity <= item.reorder_level).length}
            </span>
          )}
        </button>
      </div>

      {/* Mobile/Tablet: Always cards */}
      <div className="space-y-2 lg:hidden">
        {filteredInventory?.map((item) => {
          const stockStatus = getStockStatus(item)
          return (
            <div
              key={item.id}
              className="rounded-lg p-3 flex flex-col gap-3 bg-white/10 border border-white/15 text-white"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="space-y-0.5">
                  <div className="text-sm font-semibold leading-tight line-clamp-2">
                    {item.name}
                  </div>
                  <div className="text-[11px] font-mono text-gray-300 bg-white/10 px-2 py-0.5 rounded border border-white/20 inline-flex">
                    {item.sku}
                  </div>
                  {item.category && (
                    <span className="inline-flex items-center rounded-full bg-white/10 border border-white/20 px-2 py-0.5 text-[11px] text-gray-200">
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

              <div className="flex items-center justify-between text-xs text-gray-200 flex-wrap gap-2">
                <div className="flex items-center gap-1">
                  <span className="text-gray-400">Stock</span>
                  <span className="font-semibold text-white">{item.stock_quantity}</span>
                </div>
                {item.on_order_quantity > 0 && (
                  <div className="flex items-center gap-1">
                    <span className="text-gray-400">On Order</span>
                    <span className="font-semibold text-blue-300">{item.on_order_quantity}</span>
                  </div>
                )}
                <div className="flex items-center gap-1">
                  <span className="text-gray-400">Reorder</span>
                  <span className="font-semibold text-white">{item.reorder_level}</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-gray-400">Cost</span>
                  <span className="font-semibold text-white">${item.cost}</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-gray-400">Price</span>
                  <span className="font-semibold text-white">${item.selling_price}</span>
                </div>
              </div>

              <div className="flex justify-end">
                <button
                  onClick={() => openManage(item)}
                  className="inline-flex items-center gap-1 px-3 py-1 rounded-md text-xs font-semibold transition"
                    style={{
                      color: accentColors[400],
                    backgroundColor: `${accentColors[500]}1a`,
                    borderWidth: 1,
                    borderColor: `${accentColors[400]}66`
                  }}
                >
                  Manage
                  <ArrowRight className="w-3 h-3" />
                </button>
              </div>
            </div>
          )
        })}
      </div>

      <div className="hidden lg:flex min-h-0 flex-1 flex-col rounded-xl border border-white/10 bg-white/5 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-white/10">
          <ViewToggle value={viewMode} onChange={setViewMode} />
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 font-medium">Sort:</span>
            <div className="inline-flex items-center bg-white/10 border border-white/15 rounded-lg p-0.5">
              <button
                onClick={() => setStockSort('none')}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
                  stockSort === 'none' ? 'text-white' : 'text-white hover:bg-white/20'
                }`}
                style={stockSort === 'none' ? { backgroundColor: accentColors[500] } : undefined}
              >
                Default
              </button>
              <button
                onClick={() => setStockSort('low-high')}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
                  stockSort === 'low-high' ? 'text-white' : 'text-white hover:bg-white/20'
                }`}
                style={stockSort === 'low-high' ? { backgroundColor: accentColors[500] } : undefined}
              >
                Stock ↑
              </button>
              <button
                onClick={() => setStockSort('high-low')}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
                  stockSort === 'high-low' ? 'text-white' : 'text-white hover:bg-white/20'
                }`}
                style={stockSort === 'high-low' ? { backgroundColor: accentColors[500] } : undefined}
              >
                Stock ↓
              </button>
            </div>
          </div>
          <button
            onClick={() => setShowLowStock(!showLowStock)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors whitespace-nowrap border ${
              showLowStock
                ? 'bg-red-500/20 text-red-300 border-red-500/40'
                : 'bg-white/10 text-white border-white/15 hover:bg-white/20'
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${showLowStock ? 'bg-red-400' : 'bg-yellow-400'}`} />
            Low stock only
            {showLowStock && inventory && (
              <span className="ml-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-500/30 text-red-200">
                {inventory.filter((item) => item.stock_quantity <= item.reorder_level).length}
              </span>
            )}
          </button>
        </div>
        {viewMode === 'cards' ? (
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {filteredInventory?.map((item) => {
                const stockStatus = getStockStatus(item)
                return (
            <div
                    key={item.id}
                    className="bg-white/10 border border-white/15 rounded-xl p-4 sm:p-5 space-y-3 hover:border-amber-400/40 hover:bg-white/10 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-1">
                        <div className="text-xs uppercase text-gray-400">Inventory</div>
                        <h3 className="text-lg font-semibold text-white leading-tight line-clamp-2 flex items-center gap-2">
                          <span className="text-xs font-mono text-gray-200 bg-white/10 px-2 py-0.5 rounded border border-white/20">
                            {item.sku}
                          </span>
                          {item.name}
                        </h3>
                        <p className="text-xs text-gray-400 line-clamp-2">
                          {item.description || item.category || 'No description'}
                        </p>
                      </div>
                      <span className={`px-3 py-1 rounded-full text-xs font-semibold text-center min-w-[88px] ${stockStatus.bg} ${stockStatus.text}`}>
                        {stockStatus.label}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-3 text-sm text-gray-200">
                      <div>
                        <p className="text-gray-400 text-xs">In stock</p>
                        <p className="font-semibold">{item.stock_quantity}</p>
                      </div>
                      <div>
                        <p className="text-gray-400 text-xs">On order</p>
                        <p className={`font-semibold ${item.on_order_quantity > 0 ? 'text-blue-300' : ''}`}>{item.on_order_quantity}</p>
                      </div>
                      <div>
                        <p className="text-gray-400 text-xs">Reorder</p>
                        <p className="font-semibold">{item.reorder_level}</p>
                      </div>
                      <div>
                        <p className="text-gray-400 text-xs">Cost</p>
                        <p className="font-semibold">${parseFloat(item.cost).toFixed(2)}</p>
                      </div>
                      <div>
                        <p className="text-gray-400 text-xs">Price</p>
                        <p className="font-semibold">${parseFloat(item.selling_price).toFixed(2)}</p>
                      </div>
                    </div>

                    <button
                      onClick={() => openManage(item)}
                      className="w-full px-3 py-2 text-sm font-medium rounded-lg transition inline-flex items-center justify-center gap-1"
                      style={{
                        color: accentColors[400],
                        backgroundColor: `${accentColors[500]}1a`,
                        borderWidth: 1,
                        borderColor: `${accentColors[400]}66`
                      }}
                    >
                      Manage Stock
                      <ArrowRight className="w-4 h-4" />
                    </button>
                  </div>
                )
              })}

              <div
                className="aspect-square bg-white/20 border-2 border-dashed border-white/40 p-4 sm:p-5 rounded-xl flex flex-col items-center justify-center cursor-pointer hover:bg-white/30 hover:border-white/60 transition-all"
              >
                <div className="w-12 h-12 rounded-full bg-white/30 flex items-center justify-center mb-3">
                  <Plus className="w-6 h-6 text-white" />
                </div>
                <span className="text-white font-medium">Add Part</span>
              </div>
            </div>
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-auto">
            <table className="min-w-full divide-y divide-white/10">
              <thead className="bg-white/5 border-b border-white/10">
                <tr className="text-left text-xs font-medium text-gray-400 uppercase tracking-wide bg-white/5 border-b border-white/10">
                  <th className="px-4 py-3">SKU</th>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Category</th>
                  <th className="px-4 py-3">Stock</th>
                  <th className="px-4 py-3">On Order</th>
                  <th className="px-4 py-3">Reorder</th>
                  <th className="px-4 py-3">Cost</th>
                  <th className="px-4 py-3">Price</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-sm text-gray-100">
                {filteredInventory?.map((item) => {
                  const stockStatus = getStockStatus(item)
                  return (
                    <tr key={item.id} className="hover:bg-white/5 transition-colors">
                      <td className="px-4 py-3 font-semibold text-white">{item.sku}</td>
                      <td className="px-4 py-3">
                        <div className="font-semibold text-white">{item.name}</div>
                        {item.description && <div className="text-xs text-gray-400">{item.description}</div>}
                      </td>
                      <td className="px-4 py-3 text-gray-300">
                        <div className="space-y-1 text-center">
                          <div className="text-sm">{item.category || 'Uncategorized'}</div>
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap ${stockStatus.bg} ${stockStatus.text}`}>
                            {stockStatus.label}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-gray-200">{item.stock_quantity}</td>
                      <td className={`px-4 py-3 ${item.on_order_quantity > 0 ? 'text-blue-300 font-semibold' : 'text-gray-200'}`}>{item.on_order_quantity}</td>
                      <td className="px-4 py-3 text-gray-200">{item.reorder_level}</td>
                      <td className="px-4 py-3 text-gray-200">${item.cost}</td>
                      <td className="px-4 py-3 text-gray-200">${item.selling_price}</td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => openManage(item)}
                          className="inline-flex items-center gap-1 px-3 py-1 rounded-md text-xs font-semibold transition"
                          style={{ 
                            color: accentColors[400], 
                            backgroundColor: `${accentColors[500]}1a`,
                            borderWidth: 1,
                            borderColor: `${accentColors[400]}66`
                          }}
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
        )}
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

      <SlidePanelForm
        isOpen={!!selectedItem}
        onClose={() => setSelectedItem(null)}
        category="Manage Inventory"
        title={selectedItem?.name || ''}
        subtitle={selectedItem?.sku ? `SKU: ${selectedItem.sku}` : undefined}
        onSubmit={handleSubmit}
        submitLabel="Save Changes"
        isSubmitting={updateMutation.isPending}
        submitDisabled={!selectedItem}
        ariaLabel="Manage inventory"
        headerAction={
          <button
            type="button"
            onClick={() => setEditingIdentity((v) => !v)}
            className={`p-2 rounded-full transition-colors ${
              editingIdentity
                ? 'bg-amber-100 text-amber-700 hover:bg-amber-200'
                : 'text-gray-400 hover:text-gray-700 hover:bg-gray-100'
            }`}
            aria-label="Edit part details"
            title={editingIdentity ? 'Close part details editor' : 'Edit name, SKU, category, description'}
          >
            <Pencil className="w-4 h-4" />
          </button>
        }
      >
        {/* Part details editor — only visible when pencil toggled */}
        {editingIdentity && (
          <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-3 space-y-2">
            <p className="text-[11px] uppercase tracking-wide text-amber-800 font-semibold">Edit part details</p>
            <label className="text-sm text-gray-700 space-y-1 block">
              <span>Name</span>
              <input
                type="text"
                value={manageForm.name}
                onChange={(e) => handleManageChange('name', e.target.value)}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
              />
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <label className="text-sm text-gray-700 space-y-1 block">
                <span>SKU</span>
                <input
                  type="text"
                  value={manageForm.sku}
                  onChange={(e) => handleManageChange('sku', e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
                />
              </label>
              <label className="text-sm text-gray-700 space-y-1 block">
                <span>Category</span>
                <input
                  type="text"
                  value={manageForm.category}
                  onChange={(e) => handleManageChange('category', e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
                  placeholder="e.g. Electrical"
                />
              </label>
            </div>
            <label className="text-sm text-gray-700 space-y-1 block">
              <span>Description</span>
              <textarea
                value={manageForm.description}
                onChange={(e) => handleManageChange('description', e.target.value)}
                rows={2}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white resize-none"
                placeholder="Optional description"
              />
            </label>
          </div>
        )}

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
            <span>On Order</span>
            <input
              type="number"
              value={manageForm.on_order_quantity}
              onChange={(e) => handleManageChange('on_order_quantity', e.target.value)}
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
            <span>Cost <span className="text-gray-400 font-normal">(per unit)</span></span>
            <CurrencyInput
              value={manageForm.cost}
              onChange={(val) => handleManageChange('cost', val)}
            />
          </label>
          <label className="text-sm text-gray-700 space-y-1">
            <span>Selling Price <span className="text-gray-400 font-normal">(per unit)</span></span>
            <CurrencyInput
              value={manageForm.selling_price}
              onChange={(val) => handleManageChange('selling_price', val)}
            />
          </label>
        </div>

        {/* Receive Shipment */}
        {selectedItem && (selectedItem.on_order_quantity > 0 || receiveQty) && (
          <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-3 space-y-2">
            <div className="flex items-center gap-2">
              <PackageCheck className="w-4 h-4 text-blue-700" />
              <p className="text-sm font-semibold text-blue-900">Receive Shipment</p>
              {selectedItem.on_order_quantity > 0 && (
                <span className="ml-auto text-[11px] font-semibold text-blue-700 bg-blue-100 px-2 py-0.5 rounded-full">
                  {selectedItem.on_order_quantity} on order
                </span>
              )}
            </div>
            <p className="text-xs text-gray-600">Moves units from On Order into Stock.</p>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min="1"
                value={receiveQty}
                onChange={(e) => setReceiveQty(e.target.value)}
                placeholder="Qty"
                className="w-24 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
              />
              <button
                type="button"
                onClick={() => receiveShipmentMutation.mutate()}
                disabled={!receiveQty || receiveShipmentMutation.isPending}
                className="px-3 py-2 rounded-lg text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50"
              >
                {receiveShipmentMutation.isPending ? 'Receiving…' : 'Receive into stock'}
              </button>
              {selectedItem.on_order_quantity > 0 && (
                <button
                  type="button"
                  onClick={() => setReceiveQty(String(selectedItem.on_order_quantity))}
                  className="px-2 py-2 rounded-lg text-xs font-medium text-blue-700 hover:bg-blue-100"
                >
                  Receive all
                </button>
              )}
            </div>
            {receiveMessage && <p className="text-xs text-green-700 font-medium">{receiveMessage}</p>}
          </div>
        )}

        <div className="space-y-2">
          <label className="text-sm text-gray-700 space-y-1 block">
            <span>Supplier</span>
            <BaseSelect
              options={(suppliers || []).map((s) => ({
                value: s.id,
                label: s.name,
                subLabel: s.address || s.phone || 'No contact info',
              }))}
              value={suppliers?.find((s) => s.name === manageForm.supplier_name)?.id || ''}
              onChange={(val) => handleSelectSupplier(val, 'manage')}
              placeholder="Select a supplier"
              allowAddNew
              addNewLabel="+ Add new supplier"
              onAddNew={() => setAddingSupplierInManage(true)}
            />
          </label>

          {addingSupplierInManage && (
            <div className="space-y-3 rounded-lg border border-gray-200 p-3 bg-gray-50">
              <p className="text-xs font-semibold text-gray-600 uppercase">New Supplier</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <input
                  type="text"
                  value={newSupplierForm.name}
                  onChange={(e) => handleNewSupplierChange('name', e.target.value)}
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
                  placeholder="Supplier name *"
                />
                <input
                  type="text"
                  value={newSupplierForm.contact_name}
                  onChange={(e) => handleNewSupplierChange('contact_name', e.target.value)}
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
                  placeholder="Contact name"
                />
              </div>
              <input
                type="text"
                value={newSupplierForm.phone}
                onChange={(e) => handleNewSupplierChange('phone', formatUSPhone(e.target.value))}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
                placeholder="Phone"
              />
              <MapboxAddressInput
                value={newSupplierForm.address}
                onChange={(e) => handleNewSupplierChange('address', e.target.value)}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
                placeholder="Address"
                onAddressSelect={({ formatted }) => handleNewSupplierChange('address', formatted || '')}
              />
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (!newSupplierForm.name.trim()) return
                    createSupplierMutation.mutate('manage')
                  }}
                  disabled={!newSupplierForm.name.trim() || createSupplierMutation.isPending}
                  className="px-3 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-50"
                  style={{ backgroundColor: accentColors[500] }}
                >
                  {createSupplierMutation.isPending ? 'Adding...' : 'Add Supplier'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setNewSupplierForm({ name: '', address: '', phone: '', contact_name: '' })
                    setAddingSupplierInManage(false)
                  }}
                  className="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-100"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          <label className="text-sm text-gray-700 space-y-1 block">
            <span>Supplier Contact</span>
            <input
              type="text"
              value={manageForm.supplier_contact}
              onChange={(e) => handleManageChange('supplier_contact', e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              placeholder="Auto-filled from supplier, or enter manually"
            />
          </label>
        </div>

        {error && <div className="text-sm text-red-600">{error}</div>}
      </SlidePanelForm>

      {/* Add Part Drawer */}
      <SlidePanelForm
        isOpen={isAddingPart}
        onClose={() => setIsAddingPart(false)}
        category="Inventory"
        title="Add New Part"
        onSubmit={handleAddSubmit}
        submitLabel="Add Part"
        isSubmitting={createMutation.isPending}
        ariaLabel="Add part"
      >
        {/* Name field with suggestions */}
        <div className="space-y-1">
          <label className="text-sm text-gray-700 space-y-1 block">
            <span>Name *</span>
            <input
              type="text"
              value={addForm.name}
              onChange={(e) => handleAddFormChange('name', e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              placeholder="e.g. Brake Pads - Front"
            />
          </label>
          {nameSuggestions.length > 0 && (
            <div className="flex flex-wrap gap-1">
              <span className="text-[10px] text-gray-400">Similar:</span>
              {nameSuggestions.map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => {
                    const existing = inventory?.find((i) => i.name === name)
                    if (existing) {
                      handleAddFormChange('name', existing.name)
                      handleAddFormChange('category', existing.category || '')
                      handleAddFormChange('description', existing.description || '')
                    }
                  }}
                  className="text-[11px] px-2 py-0.5 rounded bg-amber-100 text-amber-700 hover:bg-amber-200 transition"
                >
                  {name}
                </button>
              ))}
            </div>
          )}
        </div>

        <label className="text-sm text-gray-700 space-y-1 block">
          <span>Category</span>
          <input
            type="text"
            value={addForm.category}
            onChange={(e) => handleAddFormChange('category', e.target.value)}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
            placeholder="e.g. Brakes, Filters, Engine"
          />
        </label>

        {/* SKU field with auto-suggestion */}
        <div className="space-y-1">
          <label className="text-sm text-gray-700 space-y-1 block">
            <span>SKU *</span>
            <input
              type="text"
              value={addForm.sku}
              onChange={(e) => handleAddFormChange('sku', e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              placeholder="Auto-generated or enter custom"
            />
          </label>
          {skuSuggestion && (
            <button
              type="button"
              onClick={() => handleAddFormChange('sku', skuSuggestion)}
              className="text-[11px] px-2 py-1 rounded bg-blue-50 text-blue-700 hover:bg-blue-100 transition"
            >
              Use suggested: <span className="font-mono font-semibold">{skuSuggestion}</span>
            </button>
          )}
        </div>

        <label className="text-sm text-gray-700 space-y-1 block">
          <span>Description</span>
          <textarea
            value={addForm.description}
            onChange={(e) => handleAddFormChange('description', e.target.value)}
            rows={2}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 resize-none"
            placeholder="Optional description..."
          />
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="text-sm text-gray-700 space-y-1">
            <span>Stock Quantity</span>
            <input
              type="number"
              value={addForm.stock_quantity}
              onChange={(e) => handleAddFormChange('stock_quantity', e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              placeholder="0"
            />
          </label>
          <label className="text-sm text-gray-700 space-y-1">
            <span>Reorder Level</span>
            <input
              type="number"
              value={addForm.reorder_level}
              onChange={(e) => handleAddFormChange('reorder_level', e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              placeholder="0"
            />
          </label>
          <label className="text-sm text-gray-700 space-y-1">
            <span>Cost <span className="text-gray-400 font-normal">(per unit)</span> *</span>
            <CurrencyInput
              value={addForm.cost}
              onChange={(val) => handleAddFormChange('cost', val)}
            />
          </label>
          <label className="text-sm text-gray-700 space-y-1">
            <span>Selling Price <span className="text-gray-400 font-normal">(per unit)</span> *</span>
            <CurrencyInput
              value={addForm.selling_price}
              onChange={(val) => handleAddFormChange('selling_price', val)}
            />
          </label>
        </div>

        <div className="space-y-2">
          <label className="text-sm text-gray-700 space-y-1 block">
            <span>Supplier</span>
            <BaseSelect
              options={(suppliers || []).map((s) => ({
                value: s.id,
                label: s.name,
                subLabel: s.address || s.phone || 'No contact info',
              }))}
              value={suppliers?.find((s) => s.name === addForm.supplier_name)?.id || ''}
              onChange={(val) => handleSelectSupplier(val, 'add')}
              placeholder="Select a supplier"
              allowAddNew
              addNewLabel="+ Add new supplier"
              onAddNew={() => setAddingSupplierInAdd(true)}
            />
          </label>

          {addingSupplierInAdd && (
            <div className="space-y-3 rounded-lg border border-gray-200 p-3 bg-gray-50">
              <p className="text-xs font-semibold text-gray-600 uppercase">New Supplier</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <input
                  type="text"
                  value={newSupplierForm.name}
                  onChange={(e) => handleNewSupplierChange('name', e.target.value)}
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
                  placeholder="Supplier name *"
                />
                <input
                  type="text"
                  value={newSupplierForm.contact_name}
                  onChange={(e) => handleNewSupplierChange('contact_name', e.target.value)}
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
                  placeholder="Contact name"
                />
              </div>
              <input
                type="text"
                value={newSupplierForm.phone}
                onChange={(e) => handleNewSupplierChange('phone', formatUSPhone(e.target.value))}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
                placeholder="Phone"
              />
              <MapboxAddressInput
                value={newSupplierForm.address}
                onChange={(e) => handleNewSupplierChange('address', e.target.value)}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
                placeholder="Address"
                onAddressSelect={({ formatted }) => handleNewSupplierChange('address', formatted || '')}
              />
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (!newSupplierForm.name.trim()) return
                    createSupplierMutation.mutate('add')
                  }}
                  disabled={!newSupplierForm.name.trim() || createSupplierMutation.isPending}
                  className="px-3 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-50"
                  style={{ backgroundColor: accentColors[500] }}
                >
                  {createSupplierMutation.isPending ? 'Adding...' : 'Add Supplier'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setNewSupplierForm({ name: '', address: '', phone: '', contact_name: '' })
                    setAddingSupplierInAdd(false)
                  }}
                  className="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-100"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          <label className="text-sm text-gray-700 space-y-1 block">
            <span>Supplier Contact</span>
            <input
              type="text"
              value={addForm.supplier_contact}
              onChange={(e) => handleAddFormChange('supplier_contact', e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              placeholder="Auto-filled from supplier, or enter manually"
            />
          </label>
        </div>

        {addError && <div className="text-sm text-red-600">{addError}</div>}
      </SlidePanelForm>
    </div>
  )
}
