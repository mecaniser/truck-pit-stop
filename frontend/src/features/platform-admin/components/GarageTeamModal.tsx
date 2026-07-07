import { useEffect, useRef, useState } from 'react'
import { Loader2, X, Mail, Phone, Shield, Plus, Pencil, Eye, EyeOff, Crown, MessageSquare } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../../../lib/api'
import { GlassNoirButton, GlassNoirBadge } from '../../../components/ui/GlassNoirCard'
import { getPasswordValidationError } from '../../../lib/passwordPolicy'
import { generateMechanicPassword } from '../../../utils/password'

export interface TenantUser {
  id: string
  email: string
  first_name: string
  last_name: string
  phone: string | null
  role: string
  is_active: boolean
  is_verified: boolean
  is_owner: boolean
  can_access_messaging: boolean
}

// Roles that have the Messages/Communications surface by role; for these the
// grant is implicit (checkbox shown checked + disabled). Fleet managers don't,
// so the checkbox is the way to grant them access.
const MESSAGING_BY_DEFAULT_ROLES = ['garage_owner', 'garage_admin', 'receptionist', 'mechanic']
const roleHasMessagingByDefault = (role: string) => MESSAGING_BY_DEFAULT_ROLES.includes(role)

interface GarageTeamModalProps {
  garageId: string
  garageName: string
  onClose: () => void
}

// Roles the platform admin can assign (mirrors backend ADMIN_MANAGEABLE_ROLES).
const ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: 'garage_owner', label: 'Owner' },
  { value: 'garage_admin', label: 'Admin' },
  { value: 'receptionist', label: 'Receptionist' },
  { value: 'mechanic', label: 'Technician' },
  { value: 'fleet_manager', label: 'Fleet Manager' },
]

const ROLE_LABELS: Record<string, string> = Object.fromEntries(
  ROLE_OPTIONS.map((o) => [o.value, o.label])
)

type FormMode = { kind: 'list' } | { kind: 'create' } | { kind: 'edit'; user: TenantUser }

interface FormState {
  first_name: string
  last_name: string
  email: string
  phone: string
  role: string
  password: string
  can_access_messaging: boolean
}

const emptyForm: FormState = {
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  role: 'mechanic',
  password: '',
  can_access_messaging: false,
}

export default function GarageTeamModal({ garageId, garageName, onClose }: GarageTeamModalProps) {
  const [users, setUsers] = useState<TenantUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<FormMode>({ kind: 'list' })
  const [form, setForm] = useState<FormState>(emptyForm)
  const [formError, setFormError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [rowBusyId, setRowBusyId] = useState<string | null>(null)
  const modalRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    fetchUsers()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const fetchUsers = async () => {
    try {
      setLoading(true)
      setError(null)
      const res = await api.get(`/admin/tenants/${garageId}/users`)
      setUsers(res.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load team')
    } finally {
      setLoading(false)
    }
  }

  const openCreate = () => {
    setForm(emptyForm)
    setFormError(null)
    setShowPassword(false)
    setMode({ kind: 'create' })
  }

  const openEdit = (user: TenantUser) => {
    setForm({
      first_name: user.first_name,
      last_name: user.last_name,
      email: user.email,
      phone: user.phone || '',
      role: user.role,
      password: '',
      can_access_messaging: user.can_access_messaging,
    })
    setFormError(null)
    setShowPassword(false)
    setMode({ kind: 'edit', user })
  }

  const backToList = () => {
    setMode({ kind: 'list' })
    setFormError(null)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      if (mode.kind === 'list') {
        onClose()
      } else {
        backToList()
      }
    }
  }

  const validateForm = (isCreate: boolean): string | null => {
    if (!form.first_name.trim()) return 'First name is required'
    if (!form.last_name.trim()) return 'Last name is required'
    if (!form.email.trim()) return 'Email is required'
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) return 'Enter a valid email'
    if (isCreate || form.password) {
      const pwErr = getPasswordValidationError(form.password)
      if (pwErr) return pwErr
    }
    return null
  }

  const handleCreate = async () => {
    const err = validateForm(true)
    if (err) {
      setFormError(err)
      return
    }
    try {
      setSaving(true)
      setFormError(null)
      await api.post(`/admin/tenants/${garageId}/users`, {
        email: form.email.trim(),
        password: form.password,
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        role: form.role,
        phone: form.phone.trim() || undefined,
        can_access_messaging: roleHasMessagingByDefault(form.role) ? true : form.can_access_messaging,
      })
      toast.success('Team member added')
      await fetchUsers()
      backToList()
    } catch (err: any) {
      setFormError(err.response?.data?.detail || 'Failed to add team member')
    } finally {
      setSaving(false)
    }
  }

  const handleUpdate = async () => {
    if (mode.kind !== 'edit') return
    const err = validateForm(false)
    if (err) {
      setFormError(err)
      return
    }
    const payload: Record<string, unknown> = {
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      email: form.email.trim(),
      phone: form.phone.trim() || null,
      role: form.role,
      can_access_messaging: roleHasMessagingByDefault(form.role) ? true : form.can_access_messaging,
    }
    if (form.password) payload.password = form.password
    try {
      setSaving(true)
      setFormError(null)
      await api.patch(`/admin/tenants/${garageId}/users/${mode.user.id}`, payload)
      toast.success(form.password ? 'Saved — password reset' : 'Team member updated')
      await fetchUsers()
      backToList()
    } catch (err: any) {
      setFormError(err.response?.data?.detail || 'Failed to update team member')
    } finally {
      setSaving(false)
    }
  }

  const toggleActive = async (user: TenantUser) => {
    if (rowBusyId) return
    if (user.is_active) {
      const ok = window.confirm(`Deactivate ${user.first_name} ${user.last_name}? They will lose access until reactivated.`)
      if (!ok) return
    }
    try {
      setRowBusyId(user.id)
      await api.patch(`/admin/tenants/${garageId}/users/${user.id}`, { is_active: !user.is_active })
      toast.success(user.is_active ? 'Deactivated' : 'Reactivated')
      await fetchUsers()
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to update status')
    } finally {
      setRowBusyId(null)
    }
  }

  const suggestPassword = () => {
    const suggested = generateMechanicPassword(form.first_name || 'User', form.phone)
    setForm((f) => ({ ...f, password: suggested }))
    setShowPassword(true)
    setFormError(null)
  }

  const updateField = (field: keyof FormState, value: string) => {
    setForm((f) => ({ ...f, [field]: value }))
    if (formError) setFormError(null)
  }

  const inputClass =
    'w-full px-3 py-2 bg-black/40 border border-gold-500/20 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-gold-500 text-sm'

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onKeyDown={handleKeyDown}
      role="dialog"
      aria-modal="true"
      aria-labelledby="team-modal-title"
      tabIndex={-1}
    >
      <div
        ref={modalRef}
        className="bg-noir-800 rounded-xl border border-gold-500/20 w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl shadow-gold-500/10"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gold-500/20 flex-shrink-0">
          <div>
            <h2 id="team-modal-title" className="text-lg font-semibold text-white">
              {mode.kind === 'create' ? 'Add Team Member' : mode.kind === 'edit' ? 'Edit Team Member' : 'Manage Team'}
            </h2>
            <p className="text-sm text-gray-400">{garageName}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gold-500/10 text-gray-400 hover:text-gold-400 transition-colors"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 overflow-y-auto">
          {mode.kind === 'list' && (
            <>
              <div className="flex items-center justify-between mb-4">
                <p className="text-sm text-gray-400">
                  {loading ? 'Loading…' : `${users.length} member${users.length === 1 ? '' : 's'}`}
                </p>
                <GlassNoirButton size="sm" onClick={openCreate}>
                  <span className="inline-flex items-center gap-1.5">
                    <Plus className="w-4 h-4" />
                    Add User
                  </span>
                </GlassNoirButton>
              </div>

              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-8 h-8 animate-spin text-gold-500" />
                </div>
              ) : error ? (
                <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">
                  {error}
                </div>
              ) : users.length === 0 ? (
                <p className="text-center text-gray-500 py-10">No team members yet.</p>
              ) : (
                <div className="space-y-2">
                  {users.map((u) => (
                    <div
                      key={u.id}
                      className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-white/5 px-3 py-2.5"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-white truncate">
                            {u.first_name} {u.last_name}
                          </span>
                          {u.is_owner && (
                            <GlassNoirBadge variant="gold">
                              <span className="inline-flex items-center gap-1 whitespace-nowrap">
                                <Crown className="w-3 h-3" />
                                Owner
                              </span>
                            </GlassNoirBadge>
                          )}
                          {!u.is_active && (
                            <span className="text-[11px] text-gray-500">(inactive)</span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 text-xs text-gray-400 mt-0.5">
                          <span className="inline-flex items-center gap-1 truncate">
                            <Mail className="w-3 h-3 flex-shrink-0" />
                            <span className="truncate">{u.email}</span>
                          </span>
                          <span className="inline-flex items-center gap-1 whitespace-nowrap">
                            <Shield className="w-3 h-3" />
                            {ROLE_LABELS[u.role] || u.role}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <GlassNoirButton variant="ghost" size="sm" onClick={() => openEdit(u)}>
                          <span className="inline-flex items-center gap-1">
                            <Pencil className="w-3.5 h-3.5" />
                            Edit
                          </span>
                        </GlassNoirButton>
                        <GlassNoirButton
                          variant="ghost"
                          size="sm"
                          className={u.is_active ? 'text-red-400 hover:bg-red-500/10' : 'text-green-400 hover:bg-green-500/10'}
                          disabled={Boolean(rowBusyId)}
                          onClick={() => toggleActive(u)}
                        >
                          <span className="inline-flex items-center gap-1">
                            {rowBusyId === u.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                            {u.is_active ? 'Deactivate' : 'Reactivate'}
                          </span>
                        </GlassNoirButton>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {(mode.kind === 'create' || mode.kind === 'edit') && (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                mode.kind === 'create' ? handleCreate() : handleUpdate()
              }}
              className="space-y-4"
            >
              {mode.kind === 'edit' && mode.user.is_owner && (
                <div className="rounded-lg border border-gold-500/30 bg-gold-500/10 px-3 py-2 text-xs text-gold-200">
                  This is the shop owner account. Changes here take effect immediately.
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-300 mb-1">First name</label>
                  <input className={inputClass} value={form.first_name} onChange={(e) => updateField('first_name', e.target.value)} />
                </div>
                <div>
                  <label className="block text-sm text-gray-300 mb-1">Last name</label>
                  <input className={inputClass} value={form.last_name} onChange={(e) => updateField('last_name', e.target.value)} />
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1">
                  <span className="inline-flex items-center gap-1.5"><Mail className="w-3.5 h-3.5" /> Email</span>
                </label>
                <input className={inputClass} type="email" value={form.email} onChange={(e) => updateField('email', e.target.value)} />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-300 mb-1">
                    <span className="inline-flex items-center gap-1.5"><Phone className="w-3.5 h-3.5" /> Phone (optional)</span>
                  </label>
                  <input className={inputClass} value={form.phone} onChange={(e) => updateField('phone', e.target.value)} placeholder="(704) 555-0123" />
                </div>
                <div>
                  <label className="block text-sm text-gray-300 mb-1">
                    <span className="inline-flex items-center gap-1.5"><Shield className="w-3.5 h-3.5" /> Role</span>
                  </label>
                  <select
                    className={inputClass}
                    value={form.role}
                    onChange={(e) => updateField('role', e.target.value)}
                  >
                    {ROLE_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value} className="bg-noir-800">
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2.5">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    className="mt-0.5 w-4 h-4 rounded border-gold-500/50 bg-black/40 text-gold-500 focus:ring-gold-500 focus:ring-offset-0 disabled:opacity-60 cursor-pointer"
                    checked={roleHasMessagingByDefault(form.role) ? true : form.can_access_messaging}
                    disabled={roleHasMessagingByDefault(form.role)}
                    onChange={(e) => setForm((f) => ({ ...f, can_access_messaging: e.target.checked }))}
                  />
                  <span className="text-sm">
                    <span className="inline-flex items-center gap-1.5 text-gray-200 font-medium">
                      <MessageSquare className="w-3.5 h-3.5" /> Communications access
                    </span>
                    <span className="block text-xs text-gray-400 mt-0.5">
                      {roleHasMessagingByDefault(form.role)
                        ? 'This role has the Messages inbox by default.'
                        : 'Grant the Messages inbox (SMS/customer threads). Off by default for fleet managers.'}
                    </span>
                  </span>
                </label>
              </div>

              <div>
                <label className="block text-sm text-gray-300 mb-1">
                  {mode.kind === 'create' ? 'Password' : 'Reset password'}
                </label>
                <div className="relative">
                  <input
                    className={`${inputClass} pr-10`}
                    type={showPassword ? 'text' : 'password'}
                    value={form.password}
                    onChange={(e) => updateField('password', e.target.value)}
                    placeholder={mode.kind === 'edit' ? 'Leave blank to keep current password' : ''}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((s) => !s)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gold-400"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <button type="button" onClick={suggestPassword} className="mt-1.5 text-xs text-gold-400 hover:text-gold-300">
                  Suggest a password
                </button>
              </div>

              {formError && (
                <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">
                  {formError}
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-2">
                <GlassNoirButton type="button" variant="ghost" size="sm" onClick={backToList} disabled={saving}>
                  Cancel
                </GlassNoirButton>
                <GlassNoirButton type="submit" size="sm" disabled={saving}>
                  <span className="inline-flex items-center gap-2">
                    {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                    {mode.kind === 'create' ? 'Add Member' : 'Save Changes'}
                  </span>
                </GlassNoirButton>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
