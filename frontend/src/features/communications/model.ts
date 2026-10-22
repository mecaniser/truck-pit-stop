/** Proposed shared inbox contract. No transport or provider dependencies. */
export type Channel = "sms" | "whatsapp" | "telegram";
export type DeliveryStatus =
  | "received"
  | "pending"
  | "queued"
  | "sent"
  | "delivered"
  | "undelivered"
  | "failed"
  | "unknown";
export type SendRestriction =
  | "reply_route_unavailable"
  | "reply_route_ambiguous"
  | "not_connected"
  | "opted_out"
  | "recipient_opted_out"
  | "identity_unverified"
  | "ambiguous_outcome"
  | "template_required"
  | "not_started"
  | "routing_disabled"
  | "credentials_unavailable"
  | "tenant_disabled"
  | "binding_changed"
  | "registration_required"
  | "consent_required";
export interface Message {
  id: string;
  conversationId: string;
  channel: Channel;
  direction: "inbound" | "outbound";
  source: "customer" | "staff" | "automation";
  body: string;
  createdAt: string;
  deliveryStatus: DeliveryStatus;
  errorCode?: string;
  sendOperationId?: string;
  hasAttachments?: boolean;
}
export interface Conversation {
  version?: number;
  messagesHasMore?: boolean;
  messagesNextCursor?: string | null;
  id: string;
  tenantId: string;
  customerId: string | null;
  conversationKind?: "customer" | "inquiry";
  customerName: string;
  company: string | null;
  channel: Channel;
  channelAccountId: string;
  contactIdentityId: string;
  identityLabel: string;
  status: "open" | "resolved";
  assigneeId: string | null;
  unreadCount: number;
  lastMessageAt: string;
  preview: string;
  messages: Message[];
  sendPolicy: { canSend: boolean; reason: SendRestriction | null; maxLength?: number };
  context: {
    smsProvider?: string;
    senderNumber?: string;
    senderMode?: "reply" | "initiation" | "unavailable";
    senderRouteReason?: string;
    vehicleLabel?: string;
    repairOrderLabel?: string;
    repairStatus?: string;
    concern?: string;
  };
}
export type InboxView = "open" | "unread" | "mine" | "resolved" | "inquiries";
export const channelLabels: Record<Channel, string> = {
  sms: "SMS",
  whatsapp: "WhatsApp",
  telegram: "Telegram",
};
export const restrictionLabels: Record<SendRestriction, string> = {
  reply_route_unavailable: "This conversation’s number needs review before replying.",
  reply_route_ambiguous: "This conversation’s number needs review before replying.",
  not_connected: "This channel is not connected yet.",
  routing_disabled: "SMS routing for this shop is awaiting activation.",
  credentials_unavailable: "This shop’s SMS connection needs review.",
  tenant_disabled: "SMS is disabled for this shop.",
  binding_changed: "The SMS connection changed. Refresh before replying.",
  registration_required: "This shop’s SMS registration needs approval.",
  consent_required: "Record this contact’s SMS consent before replying.",
  opted_out: "This contact has opted out of SMS.",
  recipient_opted_out: "This contact opted out of SMS. Replies are blocked.",
  identity_unverified: "Verify and link this contact before replying.",
  ambiguous_outcome:
    "Delivery is uncertain. Check the provider before sending again.",
  template_required:
    "An approved WhatsApp template is required outside the reply window.",
  not_started: "Ask the customer to start a conversation with the shop bot.",
};
export function draftKey(
  tenantId: string,
  userId: string,
  conversation: Conversation,
): string {
  return JSON.stringify([
    tenantId,
    userId,
    conversation.id,
    conversation.channel,
    conversation.channelAccountId,
    conversation.contactIdentityId,
  ]);
}
export function filterConversations(
  rows: Conversation[],
  tenantId: string,
  view: InboxView,
  channel: Channel | "all",
  search: string,
  userId: string,
): Conversation[] {
  const term = search.trim().toLowerCase();
  return rows
    .filter(
      (row) =>
        row.tenantId === tenantId &&
        (channel === "all" || row.channel === channel) &&
        (view === "resolved"
          ? row.status === "resolved"
          : row.status === "open") &&
        (view !== "unread" || row.unreadCount > 0) &&
        (view !== "mine" || row.assigneeId === userId) &&
        (view !== "inquiries" || row.conversationKind === "inquiry") &&
        (!term ||
          [
            row.customerName,
            row.company,
            row.identityLabel,
            row.context.senderNumber,
            row.context.vehicleLabel,
            row.context.repairOrderLabel,
            ...row.messages.map((m) => m.body),
          ].some((value) => value?.toLowerCase().includes(term))),
    )
    .sort((a, b) => b.lastMessageAt.localeCompare(a.lastMessageAt));
}
export function composeMaxLength(conversation: Conversation): number {
  if (conversation.channel !== "sms") return 1600;
  const providerLimit = conversation.context.smsProvider === "callrail" ? 140 : 1600;
  return Math.min(providerLimit, conversation.sendPolicy.maxLength ?? 1600);
}
export function canCompose(conversation: Conversation, body: string): boolean {
  return (
    conversation.context.senderMode !== "unavailable" &&
    conversation.sendPolicy.canSend &&
    conversation.sendPolicy.reason === null &&
    body.trim().length > 0 &&
    body.trim().length <= composeMaxLength(conversation)
  );
}
