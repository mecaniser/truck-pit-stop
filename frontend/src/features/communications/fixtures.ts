import type { Channel, Conversation, Message } from "./model";

export const DEMO_TENANT = "preview-shop";
export const DEMO_USER = "alex";
const message = (
  id: string,
  conversationId: string,
  body: string,
  direction: Message["direction"],
  minute: string,
  source: Message["source"] = direction === "inbound" ? "customer" : "staff",
  deliveryStatus: Message["deliveryStatus"] = direction === "inbound"
    ? "received"
    : "delivered",
): Message => ({
  id,
  conversationId,
  body,
  direction,
  source,
  deliveryStatus,
  channel: "sms",
  createdAt: `2026-10-16T14:${minute}:00-04:00`,
});
const base = (
  id: string,
  name: string,
  company: string,
  channel: Channel = "sms",
): Conversation => ({
  id,
  tenantId: DEMO_TENANT,
  customerId: `customer-${id}`,
  customerName: name,
  company,
  channel,
  channelAccountId: `preview-${channel}`,
  contactIdentityId: `identity-${id}`,
  identityLabel: "(704) 555-01" + id.padStart(2, "0"),
  status: "open",
  assigneeId: null,
  unreadCount: 0,
  lastMessageAt: "2026-10-16T14:00:00-04:00",
  preview: "",
  messages: [],
  sendPolicy: {
    canSend: channel === "sms",
    reason: channel === "sms" ? null : "not_connected",
  },
  context: {},
});

export function createDemoConversations(): Conversation[] {
  return [
    {
      ...base("01", "Daniel Brooks", "Northline Transport"),
      assigneeId: DEMO_USER,
      unreadCount: 2,
      lastMessageAt: "2026-10-16T14:42:00-04:00",
      preview: "Perfect. Can the driver pick it up around 4?",
      context: {
        vehicleLabel: "2021 Freightliner Cascadia · Unit 204",
        repairOrderLabel: "RO-1048",
        repairStatus: "Ready for pickup",
        concern: "Air leak · Rear brake chamber",
      },
      messages: [
        message(
          "a1",
          "01",
          "Hi, any update on unit 204? The driver has a load this evening.",
          "inbound",
          "12",
        ),
        message(
          "a2",
          "01",
          "The brake chamber is replaced. We’re finishing the air-leak check now. I’ll let you know as soon as it’s ready.",
          "outbound",
          "18",
        ),
        message(
          "a3",
          "01",
          "Unit 204 is ready for pickup. Your invoice is available in the customer portal.",
          "outbound",
          "35",
          "automation",
        ),
        message(
          "a4",
          "01",
          "Perfect. Can the driver pick it up around 4?",
          "inbound",
          "42",
        ),
      ],
    },
    {
      ...base("02", "Maria Torres", "Blue Ridge Freight"),
      unreadCount: 1,
      lastMessageAt: "2026-10-16T14:28:00-04:00",
      preview: "Is the estimate ready for the coolant leak?",
      context: {
        vehicleLabel: "2020 Volvo VNL · Unit 318",
        repairOrderLabel: "RO-1046",
        repairStatus: "Estimate in progress",
        concern: "Coolant leak",
      },
      messages: [
        message(
          "b1",
          "02",
          "Is the estimate ready for the coolant leak?",
          "inbound",
          "28",
        ),
      ],
    },
    {
      ...base("03", "James Parker", "Parker Hauling"),
      assigneeId: "nina",
      lastMessageAt: "2026-10-16T14:15:00-04:00",
      preview: "Pickup notice could not be delivered.",
      context: {
        vehicleLabel: "2019 Kenworth T680 · Unit 12",
        repairOrderLabel: "RO-1041",
        repairStatus: "Ready for pickup",
        concern: "Annual inspection",
      },
      messages: [
        message(
          "c1",
          "03",
          "Please text me when the inspection is complete.",
          "inbound",
          "02",
        ),
        {
          ...message(
            "c2",
            "03",
            "Your inspection is complete. Unit 12 is ready for pickup.",
            "outbound",
            "15",
            "automation",
            "undelivered",
          ),
          errorCode: "30003",
        },
      ],
    },
    {
      ...base("04", "Olivia Reed", "Summit Fleet"),
      channel: "whatsapp",
      channelAccountId: "preview-whatsapp",
      identityLabel: "WhatsApp · Not linked",
      sendPolicy: { canSend: false, reason: "not_connected" },
      lastMessageAt: "2026-10-16T14:05:00-04:00",
      preview: "WhatsApp connection preview",
      context: {
        vehicleLabel: "2022 Peterbilt 579 · Unit 87",
        repairOrderLabel: "RO-1049",
        repairStatus: "In the shop",
      },
      messages: [],
    },
    {
      ...base("05", "Victor Lane", "Crosswind Logistics", "telegram"),
      identityLabel: "Telegram · Not linked",
      lastMessageAt: "2026-10-16T13:55:00-04:00",
      preview: "Telegram connection preview",
      context: { vehicleLabel: "2021 Volvo VNL · Unit 42" },
      messages: [],
    },
    {
      ...base("06", "Ethan Cole", "Cole Transport"),
      sendPolicy: { canSend: false, reason: "opted_out" },
      lastMessageAt: "2026-10-16T13:48:00-04:00",
      preview: "STOP",
      messages: [message("f1", "06", "STOP", "inbound", "00")],
    },
    {
      ...base("07", "Ava Morgan", "Westbound Carrier"),
      status: "resolved",
      assigneeId: DEMO_USER,
      lastMessageAt: "2026-10-16T12:40:00-04:00",
      preview: "Thanks, the driver has the keys.",
      context: {
        vehicleLabel: "2020 International LT · Unit 65",
        repairOrderLabel: "RO-1039",
        repairStatus: "Picked up",
      },
      messages: [
        message(
          "g1",
          "07",
          "Thanks, the driver has the keys.",
          "inbound",
          "00",
        ),
      ],
    },
  ];
}
