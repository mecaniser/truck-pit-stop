import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
import { useWebSocket } from '@/hooks/useWebSocket'
import toast from 'react-hot-toast'
import { Archive, ArchiveRestore, Loader2, MessageSquare, Send, Trash2 } from 'lucide-react'

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

const sortThreads = (rows: MessageThread[]) =>
  [...rows].sort((a, b) => {
    const aTs = a.last_message_at ? new Date(a.last_message_at).getTime() : 0
    const bTs = b.last_message_at ? new Date(b.last_message_at).getTime() : 0
    return bTs - aTs
  })

export default function MessagesInboxPage() {
  const { accentColors } = useTheme()
  const queryClient = useQueryClient()
  const { user } = useAuthStore()
  useWebSocket()
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
  const [includeArchived, setIncludeArchived] = useState(false)

  const [customers, setCustomers] = useState<Customer[]>([])
  const [newCustomerId, setNewCustomerId] = useState('')
  const [newThreadBody, setNewThreadBody] = useState('')
  const [replyBody, setReplyBody] = useState('')
  const smsEventQueueRef = useRef<Promise<void>>(Promise.resolve())

  const selectedThread = useMemo(
    () => threads.find((thread) => thread.id === selectedThreadId) || null,
    [threads, selectedThreadId]
  )
  const canHardDeleteThread = user?.role === 'garage_owner' || user?.role === 'garage_admin'

  const loadThreads = useCallback(async (cursor: string | null = null, append = false) => {
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
  }, [includeArchived])

  const loadMessages = useCallback(async (threadId: string, cursor: string | null = null, appendOlder = false) => {
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
          })
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
  }, [queryClient])

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

        if (!data.has_more || data.items.length === 0) {
          break
        }

        skip = data.skip + data.limit
      }

      setCustomers(allCustomers.filter((customer) => !!customer.phone))
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || 'Failed to load customers')
      setCustomers([])
    }
  }, [])

  const enqueueSmsRefresh = useCallback((task: () => Promise<void>) => {
    smsEventQueueRef.current = smsEventQueueRef.current
      .then(task)
      .catch(() => {})
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
    setSending(true)
    try {
      await api.post('/messages/threads/new', {
        customer_id: newCustomerId,
        body: newThreadBody.trim(),
      })
      setNewThreadBody('')
      setNewCustomerId('')
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

  useEffect(() => {
    void loadCustomers()
  }, [loadCustomers])

  useEffect(() => {
    setSelectedThreadId(null)
    setMessages([])
    void loadThreads()
  }, [loadThreads])

  useEffect(() => {
    if (selectedThreadId) {
      void loadMessages(selectedThreadId)
    }
  }, [selectedThreadId, loadMessages])

  useEffect(() => {
    const onSmsEvent = (event: Event) => {
      const customEvent = event as CustomEvent<SmsRealtimeEvent>
      const payload = customEvent.detail
      if (!payload?.thread_id) return

      if (
        selectedThreadId
        && selectedThreadId === payload.thread_id
        && (payload.action === 'hard_deleted' || payload.action === 'soft_deleted' || (payload.action === 'archived' && !includeArchived))
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

              if (payload.action === 'hard_deleted' || payload.action === 'soft_deleted') {
                return null
              }
              if (payload.action === 'archived' && !includeArchived) {
                return null
              }

              let archivedAt = thread.archived_at ?? null
              if (payload.action === 'archived') archivedAt = new Date().toISOString()
              if (payload.action === 'unarchived') archivedAt = null

              return {
                ...thread,
                unread_count_staff: typeof payload.unread_count_staff === 'number' ? payload.unread_count_staff : thread.unread_count_staff,
                last_message_at: payload.last_message_at ?? thread.last_message_at,
                last_message_preview: payload.last_message_preview ?? thread.last_message_preview,
                archived_at: archivedAt,
              }
            })
            .filter((thread): thread is MessageThread => thread !== null)

          return sortThreads(next)
        })

        if (!found) {
          enqueueSmsRefresh(async () => {
            await loadThreads()
          })
        }
      }

      if (payload.type === 'sms_message_created' && selectedThreadId && selectedThreadId === payload.thread_id) {
        enqueueSmsRefresh(async () => {
          await loadMessages(selectedThreadId)
        })
      }
    }

    window.addEventListener('truckpitstop:sms-event', onSmsEvent as EventListener)
    return () => {
      window.removeEventListener('truckpitstop:sms-event', onSmsEvent as EventListener)
    }
  }, [enqueueSmsRefresh, includeArchived, loadMessages, loadThreads, selectedThreadId])

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <MessageSquare className="w-5 h-5" style={{ color: accentColors[400] }} />
        <h1 className="text-xl font-semibold text-white">Messages</h1>
        <button
          className={`ml-2 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs ${
            includeArchived
              ? 'border-amber-400/40 bg-amber-500/15 text-amber-200'
              : 'border-white/20 bg-white/10 text-gray-300'
          }`}
          onClick={() => setIncludeArchived((prev) => !prev)}
        >
          <Archive className="w-3.5 h-3.5" />
          {includeArchived ? 'Hide Archived' : 'Include Archived'}
        </button>
      </div>

      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <h2 className="text-sm text-gray-300 mb-3">New Outbound Message</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <select
            className="md:col-span-1 rounded-lg bg-white/10 border border-white/20 px-3 py-2 text-sm text-white"
            value={newCustomerId}
            onChange={(e) => setNewCustomerId(e.target.value)}
          >
            <option value="">Select customer</option>
            {customers.map((customer) => (
            <option key={customer.id} value={customer.id}>
                {customer.first_name} {customer.last_name} {customer.phone ? formatUSPhone(customer.phone) : '(No phone)'}
            </option>
            ))}
          </select>
          <input
            className="md:col-span-2 rounded-lg bg-white/10 border border-white/20 px-3 py-2 text-sm text-white placeholder:text-gray-400"
            placeholder="Write your message..."
            value={newThreadBody}
            onChange={(e) => setNewThreadBody(e.target.value)}
          />
          <button
            className="md:col-span-1 inline-flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-white"
            style={{ backgroundColor: accentColors[600] }}
            onClick={startNewThread}
            disabled={sending || !newCustomerId || !newThreadBody.trim()}
          >
            <Send className="w-4 h-4" /> Send
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="rounded-xl border border-white/10 bg-white/5 p-3 lg:col-span-1">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm text-gray-300">Threads</h3>
            {threadsLoading && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
          </div>
          <div className="space-y-2 max-h-[520px] overflow-y-auto">
            {threads.map((thread) => (
              <button
                key={thread.id}
                className={`w-full text-left rounded-lg border px-3 py-2 transition ${
                  thread.id === selectedThreadId
                    ? 'border-white/40 bg-white/10'
                    : 'border-white/10 bg-white/5 hover:bg-white/10'
                }`}
                onClick={() => setSelectedThreadId(thread.id)}
              >
                <div className="flex justify-between items-start gap-2">
                  <div>
                    <p className="text-sm text-white font-medium">
                      {thread.customer.first_name} {thread.customer.last_name}
                    </p>
                    <p className="text-xs text-gray-400">
                      {thread.customer.phone ? formatUSPhone(thread.customer.phone) : 'No phone'}
                    </p>
                    {thread.archived_at ? (
                      <p className="text-[10px] text-amber-300 mt-0.5">Archived</p>
                    ) : null}
                  </div>
                  {thread.unread_count_staff > 0 && (
                    <span className="text-xs rounded-full px-2 py-0.5 text-white" style={{ backgroundColor: accentColors[600] }}>
                      {thread.unread_count_staff}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-300 mt-1 truncate">{thread.last_message_preview || 'No messages yet'}</p>
              </button>
            ))}
            {threadsHasMore && (
              <button
                className="w-full rounded-lg border border-white/20 bg-white/10 px-3 py-2 text-xs text-white"
                onClick={() => loadThreads(threadsCursor, true)}
              >
                Load more threads
              </button>
            )}
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/5 p-3 lg:col-span-2">
          {!selectedThread ? (
            <div className="h-[520px] flex items-center justify-center text-gray-400">Select a conversation</div>
          ) : (
            <div className="flex flex-col h-[520px]">
              <div className="pb-3 border-b border-white/10">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-white font-medium">
                      {selectedThread.customer.first_name} {selectedThread.customer.last_name}
                    </p>
                    <p className="text-xs text-gray-400">
                      {selectedThread.customer.phone ? formatUSPhone(selectedThread.customer.phone) : 'No phone'}
                    </p>
                    {selectedThread.archived_at ? (
                      <p className="text-[11px] text-amber-300 mt-1">Archived</p>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-2">
                    {selectedThread.archived_at ? (
                      <button
                        onClick={unarchiveSelectedThread}
                        disabled={threadActionBusy}
                        className="inline-flex items-center gap-1 rounded-md border border-emerald-400/40 bg-emerald-500/10 px-2.5 py-1.5 text-xs text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-60"
                        title="Unarchive thread"
                      >
                        <ArchiveRestore className="w-3.5 h-3.5" />
                        Unarchive
                      </button>
                    ) : (
                      <button
                        onClick={archiveSelectedThread}
                        disabled={threadActionBusy}
                        className="inline-flex items-center gap-1 rounded-md border border-white/20 bg-white/10 px-2.5 py-1.5 text-xs text-gray-200 hover:bg-white/15 disabled:opacity-60"
                        title="Archive thread"
                      >
                        <Archive className="w-3.5 h-3.5" />
                        Archive
                      </button>
                    )}
                    {canHardDeleteThread ? (
                      <button
                        onClick={deleteSelectedThread}
                        disabled={threadActionBusy}
                        className="inline-flex items-center gap-1 rounded-md border border-rose-400/40 bg-rose-500/10 px-2.5 py-1.5 text-xs text-rose-200 hover:bg-rose-500/20 disabled:opacity-60"
                        title="Delete thread from inbox"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        Delete
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto py-3 space-y-2">
                {messagesHasMore && (
                  <button
                    className="rounded-lg border border-white/20 bg-white/10 px-3 py-1 text-xs text-white"
                    onClick={() => loadMessages(selectedThread.id, messagesCursor, true)}
                    disabled={messagesLoading}
                  >
                    Load earlier
                  </button>
                )}
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`max-w-[80%] rounded-xl px-3 py-2 text-sm ${
                      message.direction === 'outbound'
                        ? 'ml-auto text-white'
                        : 'mr-auto bg-white/10 text-gray-100'
                    }`}
                    style={message.direction === 'outbound' ? { backgroundColor: accentColors[600] } : undefined}
                  >
                    <p>{message.body}</p>
                    <p className="mt-1 text-[10px] opacity-80">
                      {message.delivery_status}
                    </p>
                  </div>
                ))}
              </div>

              <div className="pt-3 border-t border-white/10 flex gap-2">
                <input
                  className="flex-1 rounded-lg bg-white/10 border border-white/20 px-3 py-2 text-sm text-white placeholder:text-gray-400"
                  placeholder="Type a reply..."
                  value={replyBody}
                  onChange={(e) => setReplyBody(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      sendReply()
                    }
                  }}
                />
                <button
                  className="inline-flex items-center justify-center rounded-lg px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
                  style={{ backgroundColor: accentColors[600] }}
                  onClick={sendReply}
                  disabled={sending || !replyBody.trim()}
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
