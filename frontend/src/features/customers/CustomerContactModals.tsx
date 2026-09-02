import React, { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, X } from 'lucide-react'

import { Spinner } from '@/components/ui'
import { useTheme } from '@/contexts/ThemeContext'
import toast from 'react-hot-toast'

import api from '@/lib/api'
import type { Contact, Customer } from '@/types'

export interface ContactFormData {
  first_name: string
  last_name: string
  role: string
  email: string
  phone: string
  notes: string
  is_primary: boolean
}

const emptyContactForm: ContactFormData = {
  first_name: '',
  last_name: '',
  role: '',
  email: '',
  phone: '',
  notes: '',
  is_primary: false,
}

/**
 * Adding, editing and removing a customer's contacts.
 *
 * The forms, their state and their mutations lived in CustomersPage, so the
 * repair-order workspace could show a carrier's contacts but not change them —
 * an operator who spotted a wrong phone number mid-job had to leave the order
 * to fix it. Hosting this puts the edit where the operator already is.
 *
 * The host owns nothing but the customer: this component keeps its own modal
 * state and invalidates by the shared query keys, so an edit made from either
 * screen refreshes both.
 */
export type CustomerContactModalsHandle = {
  openAdd: () => void
  openEdit: (contact: Contact) => void
  requestDelete: (contact: Contact) => void
}

export default function CustomerContactModals({
  customer,
  controlsRef,
}: {
  customer: Customer
  controlsRef: React.MutableRefObject<CustomerContactModalsHandle | null>
}) {
  const queryClient = useQueryClient()
  const { accentColors } = useTheme()
  const selectedCustomer = customer

  const [isContactModalOpen, setIsContactModalOpen] = useState(false)
  const [editingContact, setEditingContact] = useState<Contact | null>(null)
  const [contactFormData, setContactFormData] = useState<ContactFormData>(emptyContactForm)
  const [deleteConfirmContact, setDeleteConfirmContact] = useState<Contact | null>(null)

const createContactMutation = useMutation({
  mutationFn: async ({ customerId, data }: { customerId: string; data: ContactFormData }) => {
    const payload = {
      first_name: data.first_name || null,
      last_name: data.last_name || null,
      role: data.role || null,
      email: data.email || null,
      phone: data.phone || null,
      notes: data.notes || null,
      is_primary: data.is_primary,
    }
    const response = await api.post(`/customers/${customerId}/contacts`, payload)
    return response.data
  },
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['customerContacts', selectedCustomer?.id] })
    closeContactModal()
    toast.success('Contact added')
  },
  onError: (error: any) => {
    toast.error(error.response?.data?.detail || 'Failed to add contact')
  },
})

const updateContactMutation = useMutation({
  mutationFn: async ({ customerId, contactId, data }: { customerId: string; contactId: string; data: ContactFormData }) => {
    const payload = {
      first_name: data.first_name || null,
      last_name: data.last_name || null,
      role: data.role || null,
      email: data.email || null,
      phone: data.phone || null,
      notes: data.notes || null,
      is_primary: data.is_primary,
    }
    const response = await api.put(`/customers/${customerId}/contacts/${contactId}`, payload)
    return response.data
  },
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['customerContacts', selectedCustomer?.id] })
    closeContactModal()
    toast.success('Contact updated')
  },
  onError: (error: any) => {
    toast.error(error.response?.data?.detail || 'Failed to update contact')
  },
})

const deleteContactMutation = useMutation({
  mutationFn: async ({ customerId, contactId }: { customerId: string; contactId: string }) => {
    await api.delete(`/customers/${customerId}/contacts/${contactId}`)
  },
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['customerContacts', selectedCustomer?.id] })
    setDeleteConfirmContact(null)
    toast.success('Contact deleted')
  },
  onError: (error: any) => {
    toast.error(error.response?.data?.detail || 'Failed to delete contact')
  },
})

const openAddContactModal = () => {
  setEditingContact(null)
  setContactFormData(emptyContactForm)
  setIsContactModalOpen(true)
}

const openEditContactModal = (contact: Contact) => {
  setEditingContact(contact)
  setContactFormData({
    first_name: contact.first_name || '',
    last_name: contact.last_name || '',
    role: contact.role || '',
    email: contact.email || '',
    phone: contact.phone || '',
    notes: contact.notes || '',
    is_primary: contact.is_primary,
  })
  setIsContactModalOpen(true)
}

const closeContactModal = () => {
  setIsContactModalOpen(false)
  setEditingContact(null)
  setContactFormData(emptyContactForm)
}

const handleContactInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
  const { name, value, type } = e.target
  const checked = (e.target as HTMLInputElement).checked
  setContactFormData((prev) => ({ ...prev, [name]: type === 'checkbox' ? checked : value }))
}

const handleContactSubmit = (e: React.FormEvent) => {
  e.preventDefault()
  if (!selectedCustomer) return

  if (!contactFormData.first_name.trim() && !contactFormData.last_name.trim() && !contactFormData.email.trim() && !contactFormData.phone.trim()) {
    toast.error('Enter at least a name, email, or phone')
    return
  }

  if (editingContact) {
    updateContactMutation.mutate({
      customerId: selectedCustomer.id,
      contactId: editingContact.id,
      data: contactFormData,
    })
  } else {
    createContactMutation.mutate({
      customerId: selectedCustomer.id,
      data: contactFormData,
    })
  }
}

const handleDeleteContactClick = (contact: Contact) => {
  setDeleteConfirmContact(contact)
}

const confirmDeleteContact = () => {
  if (deleteConfirmContact && selectedCustomer) {
    deleteContactMutation.mutate({
      customerId: selectedCustomer.id,
      contactId: deleteConfirmContact.id,
    })
  }
}

  controlsRef.current = {
    openAdd: openAddContactModal,
    openEdit: openEditContactModal,
    requestDelete: handleDeleteContactClick,
  }

const renderContactForm = () => (
  <form onSubmit={handleContactSubmit} className="p-6 space-y-4">
    {/* First & Last Name */}
    <div className="grid grid-cols-2 gap-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">First Name</label>
        <input
          type="text"
          name="first_name"
          value={contactFormData.first_name}
          onChange={handleContactInputChange}
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
          placeholder="John"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Last Name</label>
        <input
          type="text"
          name="last_name"
          value={contactFormData.last_name}
          onChange={handleContactInputChange}
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
          placeholder="Doe"
        />
      </div>
    </div>

    {/* Role */}
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
      <input
        type="text"
        name="role"
        value={contactFormData.role}
        onChange={handleContactInputChange}
        className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
        placeholder="Dispatcher, Owner, Driver..."
      />
    </div>

    {/* Email & Phone */}
    <div className="grid grid-cols-2 gap-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
        <input
          type="email"
          name="email"
          value={contactFormData.email}
          onChange={handleContactInputChange}
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
          placeholder="john@example.com"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
        <input
          type="tel"
          name="phone"
          value={contactFormData.phone}
          onChange={handleContactInputChange}
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
          placeholder="(555) 123-4567"
        />
      </div>
    </div>

    {/* Notes */}
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
      <textarea
        name="notes"
        value={contactFormData.notes}
        onChange={handleContactInputChange}
        rows={2}
        className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors resize-none"
        placeholder="Any additional notes..."
      />
    </div>

    {/* Primary toggle */}
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <input
        type="checkbox"
        name="is_primary"
        checked={contactFormData.is_primary}
        onChange={handleContactInputChange}
        className="w-4 h-4 rounded border-gray-300 text-amber-600 focus:ring-amber-500"
      />
      <span className="text-sm font-medium text-gray-700">Set as primary contact</span>
    </label>

    {/* Actions */}
    <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-200">
      <button
        type="button"
        onClick={closeContactModal}
        className="px-5 py-2.5 text-gray-700 font-medium hover:bg-gray-100 rounded-lg transition-colors"
      >
        Cancel
      </button>
      <button
        type="submit"
        disabled={createContactMutation.isPending || updateContactMutation.isPending}
        className="px-5 py-2.5 disabled:opacity-50 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
        style={{ backgroundColor: accentColors[500] }}
      >
        {(createContactMutation.isPending || updateContactMutation.isPending) && (
          <Spinner size="xs" className="border-white/40 border-t-white" />
        )}
        {editingContact ? 'Save Changes' : 'Add Contact'}
      </button>
    </div>
  </form>
)

  return (
    <>
      {isContactModalOpen && selectedCustomer && (
        <div className="fixed inset-0 z-[80] overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            {/* Backdrop */}
            <div
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={closeContactModal}
            />

            {/* Modal */}
            <div className="db-customer-modal relative bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
              {/* Header */}
              <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 rounded-t-2xl">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold text-gray-900">
                      {editingContact ? 'Edit Contact' : 'Add Contact'}
                    </h2>
                    <p className="text-sm text-gray-500">
                      for {selectedCustomer.company_name || `${selectedCustomer.first_name} ${selectedCustomer.last_name}`}
                    </p>
                  </div>
                  <button
                    onClick={closeContactModal}
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    <X className="w-5 h-5 text-gray-500" />
                  </button>
                </div>
              </div>

              {/* Form */}
              {renderContactForm()}
            </div>
          </div>
        </div>
      )}
      {deleteConfirmContact && selectedCustomer && (
        <div className="fixed inset-0 z-[80] overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            {/* Backdrop */}
            <div
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => setDeleteConfirmContact(null)}
            />

            {/* Modal */}
            <div className="db-customer-modal relative bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
              <div className="flex items-center gap-4 mb-4">
                <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                  <AlertTriangle className="w-6 h-6 text-red-600" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-gray-900">Delete Contact</h3>
                  <p className="text-sm text-gray-500">This action cannot be undone</p>
                </div>
              </div>

              <p className="text-gray-700 mb-6">
                Are you sure you want to delete{' '}
                <span className="font-semibold">
                  {[deleteConfirmContact.first_name, deleteConfirmContact.last_name].filter(Boolean).join(' ') || 'this contact'}
                </span>
                ?
              </p>

              <div className="flex items-center justify-end gap-3">
                <button
                  onClick={() => setDeleteConfirmContact(null)}
                  className="px-4 py-2 text-gray-700 font-medium hover:bg-gray-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmDeleteContact}
                  disabled={deleteContactMutation.isPending}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
                >
                  {deleteContactMutation.isPending && (
                    <Spinner size="xs" className="border-white/40 border-t-white" />
                  )}
                  Delete Contact
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
