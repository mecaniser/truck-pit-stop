import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Spinner } from '@/components/ui'
import { useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type {
  CursorPageMessageThreads,
  CursorPageSmsMessages,
  Customer,
  MessageThread,
  MessagesUnreadSummary,
  SmsMessage,
} from '@/types'
import { useTheme } from '@/contexts/ThemeContext'
import { formatUSPhone } from '@/utils/phone'
import { useAuthStore } from '@/stores/authStore'
import CustomerSelect from '@/components/CustomerSelect'
import { useWebSocket } from '@/hooks/useWebSocket'
import toast from 'react-hot-toast'
import {
  AlertCircle,
  Archive,
  ArchiveRestore,
  CheckCheck,
  Clock,
  Inbox,
  MessageSquare,
  Pencil,
  Send,
  Trash2,
} from 'lucide-react'

interface PaginatedCustomersResponse {
  items: Customer[]
  total: number
  skip: number
  limit: number
  has_more: boolean
}

interface SmsRealtimeEvent {
  type: 'sms_message_created' | 'sms_thread_updated'
  thread_id?: string
  action?: string
  unread_count_staff?: number
  last_message_at?: string | null
  last_message_preview?: string | null
  customer_id?: string
}

type InboxTab = 'inbox' | 'archived'

const sortThreads = (rows: MessageThread[]) =>
  [...rows].sort((a, b) => {
    const aTs = a.last_message_at ? new Date(a.last_message_at).getTime() : 0
    const bTs = b.last_message_at ? new Date(b.last_message_at).getTime() : 0
    return bTs - aTs
  })

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  if (diff < 60_000) return 'now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h`
  if (diff < 604_800_000) return `${Math.floor(diff / 86_400_000)}d`
  return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric' })
}

function customerInitials(first: string, last: string): string {
  return `${first?.[0] || ''}${last?.[0] || ''}`.toUpperCase()
}

function formatMessageTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function DeliveryIcon({ status }: { status: string }) {
  if (status === 'delivered') return <CheckCheck className="w-3 h-3" />
  if (status === 'failed' || status === 'undelivered') return <AlertCircle className="w-3 h-3 text-rose-300" />
  return <Clock className="w-3 h-3 opacity-50" />
}

export default function MessagesInboxPage() {
  const { accentColors } = useTheme()
  const queryClient = useQueryClient()
  const { user } = useAuthStore()
  useWebSocket()

  const [activeTab, setActiveTab] = useState<InboxTab>('inbox')
  const [showCompose, setShowCompose] = useState(false)

  const [threads, setThreads] = useState<MessageThread[]>([])
  const [threadsCursor, setThreadsCursor] = useState<string | null>(null)
  const [threadsHasMore, setThreadsHasMore] = useState(false)
  const [threadsLoading, setThreadsLoading] = useState(true)

  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null)
  const [messages, setMessages] = useState<SmsMessage[]>([])
  const [messagesCursor, setMessagesCursor] = useState<string | null>(null)
  const [messagesHasMore, setMessagesHasMore] = useState(false)
  const [messagesLoading, setMessagesLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [threadActionBusy, setThreadActionBusy] = useState(false)

  const includeArchived = activeTab === 'archived'

  const [customers, setCustomers] = useState<Customer[]>([])
  const [newCustomerId, setNewCustomerId] = useState('')
  const [newThreadBody, setNewThreadBody] = useState('')
  const [newCustomerPhone, setNewCustomerPhone] = useState('')
  const [replyBody, setReplyBody] = useState('')
  const smsEventQueueRef = useRef<Promise<void>>(Promise.resolve())
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const replyRef = useRef<HTMLTextAreaElement>(null)

  const selectedThread = useMemo(
    () => threads.find((t) => t.id === selectedThreadId) || null,
    [threads, selectedThreadId],
  )
  const canHardDeleteThread = user?.role === 'garage_owner' || user?.role === 'garage_admin'

  const selectedNewCustomer = useMemo(
    () => customers.find((c) => c.id === newCustomerId) || null,
    [customers, newCustomerId],
  )

  const displayedThreads = useMemo(() => {
    if (activeTab === 'archived') return threads.filter((t) => !!t.archived_at)
    return threads.filter((t) => !t.archived_at)
  }, [threads, activeTab])

  const inboxUnread = useMemo(
    () => threads.filter((t) => !t.archived_at).reduce((sum, t) => sum + (t.unread_count_staff || 0), 0),
    [threads],
  )

  const loadThreads = useCallback(
    async (cursor: string | null = null, append = false) => {
      try {
        if (!append) setThreadsLoading(true)
        const { data } = await api.get<CursorPageMessageThreads>('/messages/threads', {
          params: { limit: 20, cursor: cursor || undefined, include_archived: includeArchived || undefined },
        })
        setThreads((prev) => (append ? [...prev, ...data.items] : data.items))
        setThreadsCursor(data.next_cursor)
        setThreadsHasMore(data.has_more)
        if (data.items.length > 0) {
          setSelectedThreadId((prev) => prev || data.items[0].id)
        }
      } catch (error: any) {
        toast.error(error?.response?.data?.detail || 'Failed to load message threads')
      } finally {
        setThreadsLoading(false)
      }
    },
    [includeArchived],
  )

  const loadMessages = useCallback(
    async (threadId: string, cursor: string | null = null, appendOlder = false) => {
      try {
        setMessagesLoading(true)
        const { data } = await api.get<CursorPageSmsMessages>(`/messages/threads/${threadId}/messages`, {
          params: { limit: 50, cursor: cursor || undefined },
        })
        setMessages((prev) => (appendOlder ? [...data.items, ...prev] : data.items))
        setMessagesCursor(data.next_cursor)
        setMessagesHasMore(data.has_more)
        if (!appendOlder) {
          let clearedUnread = 0
          setThreads((prev) =>
            prev.map((thread) => {
              if (thread.id !== threadId) return thread
              clearedUnread = thread.unread_count_staff || 0
              return thread.unread_count_staff > 0 ? { ...thread, unread_count_staff: 0 } : thread
            }),
          )
          if (clearedUnread > 0) {
            queryClient.setQueryData<MessagesUnreadSummary>(['messages-unread-summary'], (prev) => ({
              unread_count_staff: Math.max(0, (prev?.unread_count_staff || 0) - clearedUnread),
            }))
          }
        }
      } catch (error: any) {
        toast.error(error?.response?.data?.detail || 'Failed to load messages')
      } finally {
        setMessagesLoading(false)
      }
    },
    [queryClient],
  )

  const loadCustomers = useCallback(async () => {
    try {
      const pageSize = 100
      let skip = 0
      const allCustomers: Customer[] = []
      for (let page = 0; page < 20; page += 1) {
        const { data } = await api.get<PaginatedCustomersResponse>('/customers', {
          params: { paginated: true, limit: pageSize, skip },
        })
        allCustomers.push(...data.items)
        if (!data.has_more || data.items.length === 0) break
        skip = data.skip + data.limit
      }
      setCustomers(allCustomers)
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Failed to load customers')
      setCustomers([])
    }
  }, [])

  const enqueueSmsRefresh = useCallback((task: () => Promise<void>) => {
    smsEventQueueRef.current = smsEventQueueRef.current.then(task).catch(() => {})
  }, [])

  const sendReply = async () => {
    if (!selectedThread || !replyBody.trim()) return
    setSending(true)
    try {
      await api.post('/messages/send', {
        customer_id: selectedThread.customer_id,
        thread_id: selectedThread.id,
        body: replyBody.trim(),
      })
      setReplyBody('')
      await loadMessages(selectedThread.id)
      await loadThreads()
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Failed to send message')
    } finally {
      setSending(false)
    }
  }

  const startNewThread = async () => {
    if (!newCustomerId || !newThreadBody.trim()) return
    const selectedCustomer = customers.find((c) => c.id === newCustomerId)
    if (!selectedCustomer?.phone && !newCustomerPhone.trim()) return
    setSending(true)
    try {
      if (!selectedCustomer?.phone && newCustomerPhone.trim()) {
        await api.patch(`/customers/${newCustomerId}`, { phone: newCustomerPhone.trim() })
        setCustomers((prev) =>
          prev.map((c) => (c.id === newCustomerId ? { ...c, phone: newCustomerPhone.trim() } : c)),
        )
      }
      await api.post('/messages/threads/new', {
        customer_id: newCustomerId,
        body: newThreadBody.trim(),
      })
      setNewThreadBody('')
      setNewCustomerId('')
      setNewCustomerPhone('')
      setShowCompose(false)
      await loadThreads()
      toast.success('Message sent')
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Failed to send new message')
    } finally {
      setSending(false)
    }
  }

  const archiveSelectedThread = async () => {
    if (!selectedThread) return
    setThreadActionBusy(true)
    try {
      await api.post(`/messages/threads/${selectedThread.id}/archive`)
      toast.success('Thread archived')
      setSelectedThreadId(null)
      setMessages([])
      await loadThreads()
      queryClient.invalidateQueries({ queryKey: ['messages-unread-summary'] })
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Failed to archive thread')
    } finally {
      setThreadActionBusy(false)
    }
  }

  const deleteSelectedThread = async () => {
    if (!selectedThread) return
    const confirmed = window.confirm(
      `Delete this thread for ${selectedThread.customer.first_name} ${selectedThread.customer.last_name}? This hides it from inbox and keeps audit history.`,
    )
    if (!confirmed) return
    const hardDelete = window.confirm(
      'Hard delete local records permanently? Click OK for hard delete, or Cancel for soft delete.',
    )
    setThreadActionBusy(true)
    try {
      await api.delete(`/messages/threads/${selectedThread.id}`, {
        params: { hard_delete: hardDelete || undefined },
      })
      toast.success(hardDelete ? 'Thread permanently deleted' : 'Thread deleted')
      setSelectedThreadId(null)
      setMessages([])
      await loadThreads()
      queryClient.invalidateQueries({ queryKey: ['messages-unread-summary'] })
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Failed to delete thread')
    } finally {
      setThreadActionBusy(false)
    }
  }

  const unarchiveSelectedThread = async () => {
    if (!selectedThread) return
    setThreadActionBusy(true)
    try {
      await api.post(`/messages/threads/${selectedThread.id}/unarchive`)
      toast.success('Thread unarchived')
      await loadThreads()
      queryClient.invalidateQueries({ queryKey: ['messages-unread-summary'] })
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Failed to unarchive thread')
    } finally {
      setThreadActionBusy(false)
    }
  }

  useEffect(() => { void loadCustomers() }, [loadCustomers])


  useEffect(() => {
    setSelectedThreadId(null)
    setMessages([])
    void loadThreads()
  }, [loadThreads])

  useEffect(() => {
    if (selectedThreadId) void loadMessages(selectedThreadId)
  }, [selectedThreadId, loadMessages])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const onSmsEvent = (event: Event) => {
      const customEvent = event as CustomEvent<SmsRealtimeEvent>
      const payload = customEvent.detail
      if (!payload?.thread_id) return

      if (
        selectedThreadId &&
        selectedThreadId === payload.thread_id &&
        (payload.action === 'hard_deleted' ||
          payload.action === 'soft_deleted' ||
          (payload.action === 'archived' && !includeArchived))
      ) {
        setSelectedThreadId(null)
        setMessages([])
      }

      if (payload.type === 'sms_thread_updated') {
        let found = false
        setThreads((prev) => {
          const next = prev
            .map((thread) => {
              if (thread.id !== payload.thread_id) return thread
              found = true
              if (payload.action === 'hard_deleted' || payload.action === 'soft_deleted') return null
              if (payload.action === 'archived' && !includeArchived) return null
              let archivedAt = thread.archived_at ?? null
              if (payload.action === 'archived') archivedAt = new Date().toISOString()
              if (payload.action === 'unarchived') archivedAt = null
              return {
                ...thread,
                unread_count_staff:
                  typeof payload.unread_count_staff === 'number'
                    ? payload.unread_count_staff
                    : thread.unread_count_staff,
                last_message_at: payload.last_message_at ?? thread.last_message_at,
                last_message_preview: payload.last_message_preview ?? thread.last_message_preview,
                archived_at: archivedAt,
              }
            })
            .filter((t): t is MessageThread => t !== null)
          return sortThreads(next)
        })
        if (!found) enqueueSmsRefresh(async () => { await loadThreads() })
      }

      if (payload.type === 'sms_message_created' && selectedThreadId && selectedThreadId === payload.thread_id) {
        enqueueSmsRefresh(async () => { await loadMessages(selectedThreadId) })
      }
    }

    window.addEventListener('dieselbridge:sms-event', onSmsEvent as EventListener)
    return () => { window.removeEventListener('dieselbridge:sms-event', onSmsEvent as EventListener) }
  }, [enqueueSmsRefresh, includeArchived, loadMessages, loadThreads, selectedThreadId])

  // On mobile: show conversation panel when a thread is selected, thread list otherwise
  const mobileShowConversation = !!selectedThreadId

  const tabButton = (tab: InboxTab, icon: React.ReactNode, label: string, badge?: number) => (
    <button
      onClick={() => { setActiveTab(tab); setSelectedThreadId(null); setMessages([]) }}
      className={`relative flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
        activeTab === tab
          ? 'border-current text-white'
          : 'border-transparent text-gray-500 hover:text-gray-300'
      }`}
      style={activeTab === tab ? { borderColor: accentColors[400], color: accentColors[400] } : undefined}
    >
      {icon}
      <span>{label}</span>
      {!!badge && badge > 0 && (
        <span
          className="min-w-[18px] h-[18px] rounded-full flex items-center justify-center text-[10px] font-bold text-white px-1"
          style={{ backgroundColor: accentColors[500] }}
        >
          {badge > 99 ? '99+' : badge}
        </span>
      )}
    </button>
  )

  const composeForm = (
    <div className="flex flex-col gap-2.5">
      <CustomerSelect
        customers={customers}
        value={newCustomerId}
        onChange={(id) => { setNewCustomerId(id); setNewCustomerPhone('') }}
        placeholder="Search customers…"
        allowAddNew={false}
        variant="dark"
        subLabelField="phone"
        phoneRequired
        phoneValue={newCustomerPhone}
        onPhoneChange={setNewCustomerPhone}
      />

      {/* Message + send */}
      <div className="flex min-w-0 gap-2">
        <input
          className="min-w-0 flex-1 rounded-lg bg-white/10 border border-white/20 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:outline-none focus:border-white/40 transition-colors"
          placeholder="Write your message…"
          value={newThreadBody}
          onChange={(e) => setNewThreadBody(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              startNewThread()
            }
          }}
        />
        <button
          className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50 flex-shrink-0 transition-opacity"
          style={{ backgroundColor: accentColors[600] }}
          onClick={startNewThread}
          disabled={
            sending ||
            !newCustomerId ||
            !newThreadBody.trim() ||
            (!!selectedNewCustomer && !selectedNewCustomer.phone && !newCustomerPhone.trim())
          }
        >
          {sending ? <Spinner size="xs" /> : <Send className="w-3.5 h-3.5" />}
          <span className="hidden sm:inline">Send</span>
        </button>
      </div>
    </div>
  )

  const threadListPanel = (
    <div className="flex min-w-0 flex-col flex-1 min-h-0">
      {/* Mobile header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 lg:hidden">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4" style={{ color: accentColors[400] }} />
          <h1 className="text-base font-semibold text-white">Messages</h1>
        </div>
        <button
          onClick={() => setShowCompose((v) => !v)}
          className="inline-flex items-center gap-1 rounded-lg border border-white/20 bg-white/10 px-2.5 py-1.5 text-xs text-gray-200 hover:bg-white/15 transition-colors"
        >
          <Pencil className="w-3 h-3" />
          New
        </button>
      </div>

      {/* Mobile compose panel */}
      {showCompose && (
        <div className="border-b border-white/10 bg-black/20 p-3 lg:hidden">
          {composeForm}
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-white/10 px-2">
        {tabButton('inbox', <Inbox className="w-3.5 h-3.5" />, 'Inbox', inboxUnread)}
        {tabButton('archived', <Archive className="w-3.5 h-3.5" />, 'Archived')}
        {threadsLoading && <Spinner size="xs" />}
      </div>

      {/* Thread list */}
      <div className="flex-1 overflow-y-auto">
        {displayedThreads.length === 0 && !threadsLoading && (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-gray-500 py-12 px-4 text-center">
            {activeTab === 'inbox' ? <Inbox className="w-8 h-8 opacity-30" /> : <Archive className="w-8 h-8 opacity-30" />}
            <p className="text-sm">{activeTab === 'inbox' ? 'No active threads' : 'No archived threads'}</p>
          </div>
        )}

        {displayedThreads.map((thread) => {
          const isSelected = thread.id === selectedThreadId
          const hasUnread = thread.unread_count_staff > 0
          const initials = customerInitials(thread.customer.first_name, thread.customer.last_name)

          return (
            <button
              key={thread.id}
              onClick={() => setSelectedThreadId(thread.id)}
              className={`w-full text-left px-3 py-3 border-b border-white/5 transition-colors flex items-start gap-3 ${
                isSelected ? 'bg-white/10' : 'hover:bg-white/5'
              }`}
            >
              <div
                className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold text-white"
                style={{ backgroundColor: isSelected ? accentColors[600] : '#374151' }}
              >
                {initials || '?'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-1 mb-0.5">
                  <p className={`text-sm truncate ${hasUnread ? 'font-semibold text-white' : 'font-medium text-gray-200'}`}>
                    {thread.customer.first_name} {thread.customer.last_name}
                  </p>
                  <span className="flex-shrink-0 text-[10px] text-gray-500">{relativeTime(thread.last_message_at)}</span>
                </div>
                <p className={`text-xs truncate ${hasUnread ? 'text-gray-300' : 'text-gray-500'}`}>
                  {thread.last_message_preview || 'No messages yet'}
                </p>
              </div>
              {hasUnread && (
                <span
                  className="flex-shrink-0 min-w-[18px] h-[18px] rounded-full flex items-center justify-center text-[10px] font-bold text-white px-1 mt-0.5"
                  style={{ backgroundColor: accentColors[500] }}
                >
                  {thread.unread_count_staff}
                </span>
              )}
            </button>
          )
        })}

        {threadsHasMore && (
          <button
            className="w-full py-2.5 text-xs text-gray-400 hover:text-gray-200 hover:bg-white/5 transition-colors"
            onClick={() => loadThreads(threadsCursor, true)}
          >
            Load more
          </button>
        )}
      </div>
    </div>
  )

  const conversationPanel = (
    <div className="flex flex-col flex-1 min-h-0 min-w-0">
      {!selectedThread ? (
        <div className="hidden lg:flex flex-col items-center justify-center h-full gap-3 text-gray-500">
          <MessageSquare className="w-10 h-10 opacity-20" />
          <p className="text-sm">Select a conversation</p>
        </div>
      ) : (
        <>
          {/* Conversation header */}
          <div className="flex items-center justify-between gap-3 px-3 py-3 border-b border-white/10 bg-black/10 flex-shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              {/* Back button — mobile only */}
              <button
                onClick={() => { setSelectedThreadId(null); setMessages([]) }}
                className="lg:hidden flex-shrink-0 p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
                aria-label="Back to threads"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <div
                className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white"
                style={{ backgroundColor: accentColors[600] }}
              >
                {customerInitials(selectedThread.customer.first_name, selectedThread.customer.last_name)}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-white truncate">
                  {selectedThread.customer.first_name} {selectedThread.customer.last_name}
                </p>
                <p className="text-xs text-gray-400">
                  {selectedThread.customer.phone ? formatUSPhone(selectedThread.customer.phone) : 'No phone'}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1.5 flex-shrink-0">
              {selectedThread.archived_at ? (
                <button
                  onClick={unarchiveSelectedThread}
                  disabled={threadActionBusy}
                  className="inline-flex items-center gap-1 rounded-md border border-emerald-400/30 bg-emerald-500/10 px-2 py-1.5 text-xs text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-50 transition-colors"
                >
                  <ArchiveRestore className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Unarchive</span>
                </button>
              ) : (
                <button
                  onClick={archiveSelectedThread}
                  disabled={threadActionBusy}
                  className="inline-flex items-center gap-1 rounded-md border border-white/20 bg-white/5 px-2 py-1.5 text-xs text-gray-300 hover:bg-white/10 disabled:opacity-50 transition-colors"
                >
                  <Archive className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Archive</span>
                </button>
              )}
              {canHardDeleteThread && (
                <button
                  onClick={deleteSelectedThread}
                  disabled={threadActionBusy}
                  className="inline-flex items-center gap-1 rounded-md border border-rose-400/30 bg-rose-500/10 px-2 py-1.5 text-xs text-rose-300 hover:bg-rose-500/20 disabled:opacity-50 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Delete</span>
                </button>
              )}
            </div>
          </div>

          {/* Messages */}
          <div className="min-w-0 flex-1 overflow-y-auto px-3 py-3 sm:px-4 space-y-1">
            {messagesHasMore && (
              <div className="flex justify-center mb-2">
                <button
                  className="rounded-full border border-white/20 bg-white/5 px-3 py-1 text-xs text-gray-400 hover:bg-white/10 transition-colors disabled:opacity-50"
                  onClick={() => loadMessages(selectedThread.id, messagesCursor, true)}
                  disabled={messagesLoading}
                >
                  Load earlier messages
                </button>
              </div>
            )}

            {messagesLoading && messages.length === 0 && (
              <div className="flex justify-center py-8">
                <Spinner size="sm" />
              </div>
            )}

            {messages.map((message, i) => {
              const isOutbound = message.direction === 'outbound'
              const prevMessage = messages[i - 1]
              const showTimestamp =
                !prevMessage ||
                new Date(message.created_at).getTime() - new Date(prevMessage.created_at).getTime() > 300_000

              return (
                <div key={message.id}>
                  {showTimestamp && (
                    <div className="flex justify-center my-3">
                      <span className="text-[10px] text-gray-500 bg-white/5 rounded-full px-3 py-0.5">
                        {formatMessageTime(message.created_at)}
                      </span>
                    </div>
                  )}
                  <div className={`flex w-full min-w-0 ${isOutbound ? 'justify-end' : 'justify-start'} mb-0.5`}>
                    <div
                      className={`min-w-0 max-w-[88%] overflow-hidden rounded-2xl px-3.5 py-2 text-sm sm:max-w-[72%] ${
                        isOutbound ? 'rounded-tr-sm text-white' : 'rounded-tl-sm bg-white/10 text-gray-100'
                      }`}
                      style={isOutbound ? { backgroundColor: accentColors[600] } : undefined}
                    >
                      <p className="whitespace-pre-wrap leading-relaxed [overflow-wrap:anywhere]">{message.body}</p>
                      {isOutbound && (
                        <div className="flex items-center justify-end gap-1 mt-1 opacity-70">
                          <DeliveryIcon status={message.delivery_status} />
                          <span className="text-[10px]">{message.delivery_status}</span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
            <div ref={messagesEndRef} />
          </div>

          {/* Reply input */}
          <div className="border-t border-white/10 bg-black/10 px-3 py-3 flex-shrink-0">
            {selectedThread.archived_at && (
              <p className="text-xs text-amber-400/70 mb-2">
                This thread is archived. Sending a reply will not unarchive it.
              </p>
            )}
            <div className="flex min-w-0 items-end gap-2">
              <textarea
                ref={replyRef}
                rows={1}
                className="min-w-0 flex-1 resize-none rounded-xl bg-white/10 border border-white/20 px-3.5 py-2.5 text-sm text-white placeholder:text-gray-500 focus:outline-none focus:border-white/40 transition-colors"
                placeholder="Type a reply… (Enter to send)"
                value={replyBody}
                onChange={(e) => {
                  setReplyBody(e.target.value)
                  e.target.style.height = 'auto'
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendReply() }
                }}
              />
              <button
                className="flex-shrink-0 inline-flex items-center justify-center w-10 h-10 rounded-xl text-white disabled:opacity-40 transition-opacity"
                style={{ backgroundColor: accentColors[600] }}
                onClick={sendReply}
                disabled={sending || !replyBody.trim()}
              >
                {sending ? <Spinner size="xs" /> : <Send className="w-4 h-4" />}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )

  return (
    <div className="db-messages-workspace flex h-full w-full min-w-0 flex-col overflow-hidden" style={{ minHeight: 0 }}>

      {/* Desktop header — hidden on mobile (mobile header is inside threadListPanel) */}
      <div className="hidden lg:flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-5 h-5" style={{ color: accentColors[400] }} />
          <h1 className="text-xl font-semibold text-white">Messages</h1>
        </div>
        <button
          onClick={() => setShowCompose((v) => !v)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/20 bg-white/10 px-3 py-1.5 text-sm text-gray-200 hover:bg-white/15 transition-colors"
        >
          <Pencil className="w-3.5 h-3.5" />
          New Message
        </button>
      </div>

      {/* Desktop compose panel */}
      {showCompose && (
        <div className="hidden lg:block rounded-xl border border-white/10 bg-white/5 p-4 mb-4">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">New Outbound Message</p>
          {composeForm}
        </div>
      )}

      {/* Main panel */}
      <div
        className="flex w-full min-w-0 flex-1 rounded-xl border border-white/10 overflow-hidden"
        style={{ minHeight: 0, height: 'calc(100vh - 13rem)' }}
      >
        {/* Mobile: single panel navigation */}
        <div className="flex w-full min-w-0 flex-col flex-1 min-h-0 lg:hidden">
          {mobileShowConversation ? conversationPanel : threadListPanel}
        </div>

        {/* Desktop: sidebar + thread list + conversation side by side */}
        <div className="hidden lg:flex flex-1 min-h-0 min-w-0">
          {/* Vertical sidebar */}
          <div className="flex flex-col items-center gap-1 border-r border-white/10 bg-black/20 py-3 px-1.5 w-14 flex-shrink-0">
            <button
              onClick={() => { setActiveTab('inbox'); setSelectedThreadId(null); setMessages([]) }}
              title="Inbox"
              className={`relative flex flex-col items-center gap-1 rounded-lg p-2 w-10 transition-colors ${
                activeTab === 'inbox' ? 'bg-white/15 text-white' : 'text-gray-500 hover:text-gray-300 hover:bg-white/10'
              }`}
            >
              <Inbox className="w-4 h-4" />
              <span className="text-[9px] font-medium">Inbox</span>
              {inboxUnread > 0 && (
                <span
                  className="absolute -top-1 -right-1 min-w-[16px] h-4 rounded-full flex items-center justify-center text-[9px] font-bold text-white px-1"
                  style={{ backgroundColor: accentColors[500] }}
                >
                  {inboxUnread > 99 ? '99+' : inboxUnread}
                </span>
              )}
            </button>
            <button
              onClick={() => { setActiveTab('archived'); setSelectedThreadId(null); setMessages([]) }}
              title="Archived"
              className={`flex flex-col items-center gap-1 rounded-lg p-2 w-10 transition-colors ${
                activeTab === 'archived' ? 'bg-white/15 text-white' : 'text-gray-500 hover:text-gray-300 hover:bg-white/10'
              }`}
            >
              <Archive className="w-4 h-4" />
              <span className="text-[9px] font-medium">Archive</span>
            </button>
          </div>

          {/* Thread list — desktop */}
          <div className="flex flex-col border-r border-white/10 bg-black/10 w-72 flex-shrink-0">
            <div className="flex items-center justify-between px-3 py-2.5 border-b border-white/10">
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                {activeTab === 'inbox' ? 'Inbox' : 'Archived'}
              </span>
              {threadsLoading && <Spinner size="xs" />}
            </div>
            <div className="flex-1 overflow-y-auto">
              {displayedThreads.length === 0 && !threadsLoading && (
                <div className="flex flex-col items-center justify-center h-full gap-2 text-gray-500 py-12 px-4 text-center">
                  {activeTab === 'inbox' ? <Inbox className="w-8 h-8 opacity-30" /> : <Archive className="w-8 h-8 opacity-30" />}
                  <p className="text-sm">{activeTab === 'inbox' ? 'No active threads' : 'No archived threads'}</p>
                </div>
              )}
              {displayedThreads.map((thread) => {
                const isSelected = thread.id === selectedThreadId
                const hasUnread = thread.unread_count_staff > 0
                const initials = customerInitials(thread.customer.first_name, thread.customer.last_name)
                return (
                  <button
                    key={thread.id}
                    onClick={() => setSelectedThreadId(thread.id)}
                    className={`w-full text-left px-3 py-3 border-b border-white/5 transition-colors flex items-start gap-3 ${
                      isSelected ? 'bg-white/10' : 'hover:bg-white/5'
                    }`}
                  >
                    <div
                      className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold text-white"
                      style={{ backgroundColor: isSelected ? accentColors[600] : '#374151' }}
                    >
                      {initials || '?'}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-1 mb-0.5">
                        <p className={`text-sm truncate ${hasUnread ? 'font-semibold text-white' : 'font-medium text-gray-200'}`}>
                          {thread.customer.first_name} {thread.customer.last_name}
                        </p>
                        <span className="flex-shrink-0 text-[10px] text-gray-500">{relativeTime(thread.last_message_at)}</span>
                      </div>
                      <p className={`text-xs truncate ${hasUnread ? 'text-gray-300' : 'text-gray-500'}`}>
                        {thread.last_message_preview || 'No messages yet'}
                      </p>
                    </div>
                    {hasUnread && (
                      <span
                        className="flex-shrink-0 min-w-[18px] h-[18px] rounded-full flex items-center justify-center text-[10px] font-bold text-white px-1 mt-0.5"
                        style={{ backgroundColor: accentColors[500] }}
                      >
                        {thread.unread_count_staff}
                      </span>
                    )}
                  </button>
                )
              })}
              {threadsHasMore && (
                <button
                  className="w-full py-2.5 text-xs text-gray-400 hover:text-gray-200 hover:bg-white/5 transition-colors"
                  onClick={() => loadThreads(threadsCursor, true)}
                >
                  Load more
                </button>
              )}
            </div>
          </div>

          {/* Conversation — desktop */}
          {conversationPanel}
        </div>
      </div>
    </div>
  )
}
