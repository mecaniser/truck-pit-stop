import api from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import type { Conversation, Message } from "./model";
export interface Bootstrap {
  tenant_id: string;
  user_id: string;
  delivery_mode: "simulated" | "live";
  assignees: { id: string; name: string }[];
  channels: { channel: string; connected: boolean }[];
}
export interface WireMessage {
  id: string;
  conversation_id: string;
  channel: Message["channel"];
  direction: Message["direction"];
  source: Message["source"];
  body: string;
  created_at: string;
  delivery_status: Message["deliveryStatus"];
  error_code?: string;
  send_operation_id?: string;
}
export interface WireConversation {
  id: string;
  tenant_id: string;
  customer_id: string | null;
  customer_name: string;
  company: string;
  channel: Conversation["channel"];
  channel_account_id: string;
  contact_identity_id: string;
  identity_label: string;
  status: Conversation["status"];
  assignee_id: string | null;
  unread_count: number;
  last_message_at: string;
  preview: string;
  version: number;
  messages: WireMessage[];
  messages_has_more?: boolean;
  messages_next_cursor?: string | null;
  send_policy: {
    can_send: boolean;
    reason: Conversation["sendPolicy"]["reason"];
    max_length?: number;
  };
  context: {
    sms_provider?: string;
    sender_number?: string;
    selected_sender_id?: string;
    sms_sender_options?: { id: string; provider: "twilio" | "callrail"; enabled?: boolean; sender_number: string }[];
    vehicle_label?: string;
    repair_order_label?: string;
    repair_status?: string;
    concern?: string;
  };
}
export const mapMessage = (m: WireMessage): Message => ({
  id: m.id,
  conversationId: m.conversation_id,
  channel: m.channel,
  direction: m.direction,
  source: m.source,
  body: m.body,
  createdAt: m.created_at,
  deliveryStatus: m.delivery_status,
  errorCode: m.error_code,
  sendOperationId: m.send_operation_id,
});
export const mapConversation = (r: WireConversation): Conversation => ({
  id: r.id,
  tenantId: r.tenant_id,
  customerId: r.customer_id,
  customerName: r.customer_name,
  company: r.company,
  channel: r.channel,
  channelAccountId: r.channel_account_id,
  contactIdentityId: r.contact_identity_id,
  identityLabel: r.identity_label,
  status: r.status,
  assigneeId: r.assignee_id,
  unreadCount: r.unread_count,
  lastMessageAt: r.last_message_at,
  preview: r.preview,
  version: r.version,
  messages: (r.messages || []).map(mapMessage),
  messagesHasMore: r.messages_has_more,
  messagesNextCursor: r.messages_next_cursor,
  sendPolicy: {
    canSend: r.send_policy.can_send,
    reason: r.send_policy.reason,
    maxLength: r.send_policy.max_length,
  },
  context: {
    smsProvider: r.context?.sms_provider,
    senderNumber: r.context?.sender_number,
    selectedSenderId: r.context?.selected_sender_id,
    smsSenderOptions: r.context?.sms_sender_options?.map((option) => ({ id: option.id, provider: option.provider, enabled: option.enabled, senderNumber: option.sender_number })),
    vehicleLabel: r.context?.vehicle_label,
    repairOrderLabel: r.context?.repair_order_label,
    repairStatus: r.context?.repair_status,
    concern: r.context?.concern,
  },
});
export interface SendIntent {
  key: string;
  conversationId: string;
  draftKey: string;
  draft: string;
  payload: {
    channel_account_id: string;
    contact_identity_id: string;
    body: string;
    expected_version: number;
  };
}
export interface SendOperation {
  id: string;
  conversation_id: string;
  state: string;
  delivery_status: string;
}
export function createIntent(
  row: Conversation,
  draft: string,
  draftKey: string,
): SendIntent {
  return {
    key: crypto.randomUUID(),
    conversationId: row.id,
    draftKey,
    draft,
    payload: {
      channel_account_id: row.channelAccountId,
      contact_identity_id: row.contactIdentityId,
      body: draft.trim(),
      expected_version: row.version ?? 0,
    },
  };
}
export function errorMessage(error: unknown): string {
  const detail = (
    error as {
      response?: { data?: { detail?: string | { message?: string } } };
    }
  )?.response?.data?.detail;
  return typeof detail === "string"
    ? detail
    : detail && !Array.isArray(detail) && detail.message
      ? detail.message
      : "Could not confirm the request. Check your connection and try again.";
}
export const inboxApi = {
  bootstrap: async () => {
    const session = useAuthStore.getState();
    return (
      await api.get<Bootstrap>("/communications/bootstrap", {
        // Probe existing cookies, but preserve a signed-out 401 when there is no
        // renewable session. WorkOS cookie sessions keep their normal renewal.
        skipAuthRefresh:
          !session.refreshToken && session.authProvider !== "workos",
      })
    ).data;
  },
  list: async (search?: string) => {
    const rows: Conversation[] = [];
    let cursor: string | null = null;
    do {
      const {
        data,
      }: {
        data: {
          items: WireConversation[];
          next_cursor: string | null;
          has_more: boolean;
        };
      } = await api.get("/communications/conversations", {
        params: { limit: 100, search, ...(cursor ? { cursor } : {}) },
      });
      rows.push(...data.items.map(mapConversation));
      cursor = data.has_more ? data.next_cursor : null;
    } while (cursor);
    return rows;
  },
  detail: async (id: string) =>
    mapConversation(
      (await api.get<WireConversation>(`/communications/conversations/${id}`))
        .data,
    ),
  patch: async (
    row: Conversation,
    patch: { status?: "open" | "resolved"; assignee_id?: string | null },
  ) =>
    mapConversation(
      (
        await api.patch<WireConversation>(
          `/communications/conversations/${row.id}`,
          { expected_version: row.version, ...patch },
        )
      ).data,
    ),
  changeSender: async (row: Conversation, bindingId: string | null) =>
    mapConversation((await api.patch<WireConversation>(
      `/communications/conversations/${row.id}/sender`,
      { expected_version: row.version, binding_id: bindingId },
    )).data),
  read: async (row: Conversation) =>
    row.messages.length
      ? (
          await api.post<{ unread_count: number }>(
            `/communications/conversations/${row.id}/read`,
            { through_message_id: row.messages[row.messages.length - 1].id },
          )
        ).data.unread_count
      : 0,
  older: async (row: Conversation) => {
    const { data } = await api.get<{
      items: WireMessage[];
      has_more: boolean;
      next_cursor: string | null;
    }>(`/communications/conversations/${row.id}/messages`, {
      params: { limit: 50, cursor: row.messagesNextCursor },
    });
    return data;
  },
  send: async (intent: SendIntent) =>
    (
      await api.post<SendOperation>(
        `/communications/conversations/${intent.conversationId}/send-operations`,
        intent.payload,
        { headers: { "Idempotency-Key": intent.key } },
      )
    ).data,
};
