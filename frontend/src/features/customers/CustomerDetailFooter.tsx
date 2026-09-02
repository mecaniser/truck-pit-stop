import { Pencil, Trash2, User } from 'lucide-react'

import type { Customer } from '@/types'

/**
 * Delete, Merge and Edit for the customer on screen.
 *
 * This sat in the Customers page's SlidePanel footer prop rather than in the
 * detail body, so extracting the body left it behind: the repair-order
 * workspace could read a carrier and edit their contacts and trucks, but had no
 * way to edit or remove the company itself. Same actions, wherever the record
 * is shown.
 */
export default function CustomerDetailFooter({
  selectedCustomer,
  handleDeleteClick,
  onMerge,
  handleEditFromDetail,
}: {
  selectedCustomer: Customer
  handleDeleteClick: (customer: Customer) => void
  onMerge: () => void
  handleEditFromDetail: () => void
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <button
          onClick={() => handleDeleteClick(selectedCustomer)}
          className="px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors text-sm font-medium flex items-center gap-2"
        >
          <Trash2 className="w-4 h-4" />
          Delete
        </button>
        <button
          onClick={() => onMerge()}
          className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors text-sm font-medium flex items-center gap-2"
        >
          <User className="w-4 h-4" />
          Merge
        </button>
      </div>
      <button
        onClick={handleEditFromDetail}
        className="px-5 py-2.5 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
      >
        <Pencil className="w-4 h-4" />
        Edit Customer
      </button>
    </div>
  )
}
