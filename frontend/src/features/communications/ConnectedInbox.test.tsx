import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ConnectedInbox from "./ConnectedInbox";
import DashboardInboxPage from "./DashboardInboxPage";
import { inboxApi } from "./api";
import { useAuthStore } from "../../stores/authStore";
import { createDemoConversations, DEMO_TENANT, DEMO_USER } from "./fixtures";
vi.mock("../../lib/api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock("../../stores/authStore", () => {
  const state = { authSessionEpoch: 0, user: null as { role: string } | null };
  return {
    useAuthStore: Object.assign(
      (select: (s: typeof state) => unknown) => select(state),
      { getState: () => state },
    ),
  };
});
vi.mock("./api", async (original) => {
  const actual = await original<typeof import("./api")>();
  return {
    ...actual,
    inboxApi: {
      bootstrap: vi.fn(),
      list: vi.fn(),
      detail: vi.fn(),
      read: vi.fn(),
      send: vi.fn(),
      patch: vi.fn(),
      changeSender: vi.fn(),
      older: vi.fn(),
    },
  };
});
const unreadCache = vi.hoisted(() => ({ setQueryData: vi.fn() }));
vi.mock("@tanstack/react-query", () => ({ useQueryClient: () => unreadCache }));
const row = { ...createDemoConversations()[0], version: 2 };
const inquiry = {
  ...row, id: "new-inquiry", conversationKind: "inquiry" as const,
  customerId: null, customerName: "New inquiry", company: null,
  identityLabel: "+15005550002", unreadCount: 1,
  context: { smsProvider: "callrail", senderNumber: "+15005550001", selectedSenderId: "receiving-binding", senderSelectionAllowed: false, smsSenderOptions: [{ id: "receiving-binding", provider: "callrail" as const, senderNumber: "+15005550001", enabled: true }] },
  sendPolicy: { canSend: true, reason: null, maxLength: 140 },
};
const storeKey = `inbox-send:${DEMO_TENANT}:${DEMO_USER}`;
beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  (
    useAuthStore.getState() as unknown as { user: { role: string } | null }
  ).user = null;
  vi.mocked(inboxApi.bootstrap).mockResolvedValue({
    tenant_id: DEMO_TENANT,
    user_id: DEMO_USER,
    delivery_mode: "simulated",
    assignees: [],
    channels: [],
  });
  vi.mocked(inboxApi.list).mockResolvedValue([row]);
  vi.mocked(inboxApi.detail).mockResolvedValue(row);
  vi.mocked(inboxApi.read).mockResolvedValue(0);
});
afterEach(() => { cleanup(); vi.useRealTimers(); });
async function compose() {
  await screen.findByRole("textbox", { name: "Message draft" });
  fireEvent.change(screen.getByRole("textbox", { name: "Message draft" }), {
    target: { value: "A safe reply" },
  });
}
describe("connected inbox sending", () => {
  it("keeps the loading frame until inbox initialization finishes, then shows conversations", async () => {
    let finish!: (value: Awaited<ReturnType<typeof inboxApi.bootstrap>>) => void;
    vi.mocked(inboxApi.bootstrap).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    render(<ConnectedInbox />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading your inbox…");
    expect(screen.getByRole("region", { name: "Messages" })).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("textbox", { name: "Message draft" })).not.toBeInTheDocument();
    await act(async () => finish({ tenant_id: DEMO_TENANT, user_id: DEMO_USER, delivery_mode: "simulated", assignees: [], channels: [] }));
    await compose();
    expect(screen.queryByText("Loading your inbox…")).not.toBeInTheDocument();
  });
  it("explains an inquiry STOP hold without allowing a reply or offering opt-in", async () => {
    const stopped = {
      ...inquiry,
      messages: [{ ...inquiry.messages[0], id: "stop-message", conversationId: inquiry.id, body: "STOP", direction: "inbound" as const, deliveryStatus: "received" as const }],
      sendPolicy: { canSend: false, reason: "recipient_opted_out" as const, maxLength: 140 },
    };
    vi.mocked(inboxApi.list).mockResolvedValue([stopped]);
    vi.mocked(inboxApi.detail).mockResolvedValue(stopped);
    render(<ConnectedInbox />);
    await compose();
    expect(screen.getByText("This contact opted out of SMS. Replies are blocked.")).toBeInTheDocument();
    expect(screen.getByText("STOP")).toBeInTheDocument();
    expect(screen.queryByText("SMS connection or consent requires review.")).not.toBeInTheDocument();
    expect(screen.queryByText("recipient_opted_out")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /opt.in/i })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message draft" })).toHaveValue("A safe reply");
    expect(screen.getByRole("button", { name: "Send SMS" })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Message draft" }), { key: "Enter", ctrlKey: true });
    expect(inboxApi.send).not.toHaveBeenCalled();
  });
  it("lists new inquiries with unread count and phone evidence, retaining drafts across customer and inquiry filters", async () => {
    vi.mocked(inboxApi.list).mockResolvedValue([row, inquiry]);
    vi.mocked(inboxApi.detail).mockImplementation(async (id) => id === inquiry.id ? inquiry : row);
    render(<ConnectedInbox />);
    await screen.findByRole("textbox", { name: "Message draft" });
    expect(screen.getByRole("button", { name: "Service updates" })).toBeInTheDocument();
    const filter = screen.getByRole("button", { name: "New inquiries 1" });
    fireEvent.click(filter);
    expect(screen.queryByRole("button", { name: /James Miller.*Carolina/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /New inquiry.*15005550002/ }));
    const conversation = screen.getByRole("region", { name: "Conversation with New inquiry" });
    expect(screen.queryByRole("button", { name: "Service updates" })).not.toBeInTheDocument();
    expect(within(conversation).getByRole("heading", { name: "New inquiry" })).toBeInTheDocument();
    expect(within(conversation).getByText(/CallRail · To \+15005550001/)).toBeInTheDocument();
    expect(within(conversation).queryByRole("combobox", { name: "SMS sender" })).not.toBeInTheDocument();
    expect(within(conversation).queryByRole("link")).not.toBeInTheDocument();
    const draft = screen.getByRole("textbox", { name: "Message draft" });
    fireEvent.change(draft, { target: { value: "x".repeat(141) } });
    expect(screen.getByRole("button", { name: "Send SMS" })).toBeDisabled();
    expect(screen.getByText("141/140")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Open \d/ }));
    fireEvent.click(screen.getByRole("button", { name: new RegExp(row.customerName) }));
    expect(screen.getByRole("button", { name: "Service updates" })).toBeInTheDocument();
    fireEvent.change(draft, { target: { value: "Existing customer draft" } });
    fireEvent.click(screen.getByRole("button", { name: /New inquiries/ }));
    fireEvent.click(screen.getByRole("button", { name: /New inquiry.*15005550002/ }));
    expect(draft).toHaveValue("x".repeat(141));
    expect(inboxApi.changeSender).not.toHaveBeenCalled();
    await waitFor(() => expect(inboxApi.read).toHaveBeenCalledWith(expect.objectContaining({ id: inquiry.id, customerId: null })));
  });
  it("retains manual reply and workflow actions for a null-customer inquiry", async () => {
    vi.mocked(inboxApi.bootstrap).mockResolvedValue({ tenant_id: DEMO_TENANT, user_id: DEMO_USER, delivery_mode: "simulated", assignees: [{ id: "staff-2", name: "Staff member" }], channels: [] });
    vi.mocked(inboxApi.list).mockResolvedValue([inquiry]);
    vi.mocked(inboxApi.detail).mockResolvedValue(inquiry);
    vi.mocked(inboxApi.send).mockResolvedValue({ id: "inquiry-operation", conversation_id: inquiry.id, state: "pending", delivery_status: "pending" });
    render(<ConnectedInbox />);
    await compose();
    fireEvent.click(screen.getByRole("button", { name: "Send SMS" }));
    await waitFor(() => expect(inboxApi.send).toHaveBeenCalledTimes(1));
    expect(vi.mocked(inboxApi.send).mock.calls[0][0]).toMatchObject({ conversationId: inquiry.id, payload: { channel_account_id: inquiry.channelAccountId, contact_identity_id: inquiry.contactIdentityId } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Resolve" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Resolve" }));
    await waitFor(() => expect(inboxApi.patch).toHaveBeenCalledWith(expect.objectContaining({ id: inquiry.id, customerId: null }), { status: "resolved" }));
    await waitFor(() => expect(screen.getByLabelText("Assign conversation")).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Assign conversation"), { target: { value: "staff-2" } });
    await waitFor(() => expect(inboxApi.patch).toHaveBeenCalledWith(expect.objectContaining({ id: inquiry.id, customerId: null }), { assignee_id: "staff-2" }));
    expect(inboxApi.changeSender).not.toHaveBeenCalled();
  });
  it("ignores an older in-flight poll after a confirmed sender change without reverting policy or draft", async () => {
    const options = [{ id: "twilio", provider: "twilio" as const, senderNumber: "+17045550000" }, { id: "binding-1", provider: "callrail" as const, senderNumber: "+19809071896" }];
    const initial = { ...row, context: { ...row.context, selectedSenderId: "twilio", smsSenderOptions: options } };
    const updated = { ...initial, version: 8, channelAccountId: "callrail-account", sendPolicy: { ...row.sendPolicy, maxLength: 140 }, context: { ...initial.context, selectedSenderId: "binding-1", smsProvider: "callrail", senderNumber: "+19809071896" } };
    vi.mocked(inboxApi.list).mockResolvedValue([initial]);
    vi.mocked(inboxApi.detail).mockResolvedValue(initial);
    vi.mocked(inboxApi.changeSender).mockResolvedValue(updated);
    vi.mocked(inboxApi.send).mockResolvedValue({ id: "operation", conversation_id: row.id, state: "pending", delivery_status: "pending" });
    render(<ConnectedInbox />);
    const draft = await screen.findByRole("textbox", { name: "Message draft" });
    await waitFor(() => expect(inboxApi.read).toHaveBeenCalled());
    vi.useFakeTimers();
    let finishPoll!: (value: typeof initial[]) => void;
    vi.mocked(inboxApi.list).mockReturnValueOnce(new Promise((resolve) => { finishPoll = resolve; }));
    await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
    fireEvent.change(draft, { target: { value: "x".repeat(141) } });
    await act(async () => { fireEvent.change(screen.getByLabelText("SMS sender"), { target: { value: "binding-1" } }); });
    expect(screen.getByText("141/140")).toBeInTheDocument();
    await act(async () => { finishPoll([initial]); });
    expect(screen.getByLabelText("SMS sender")).toHaveValue("binding-1");
    expect(screen.getByText("141/140")).toBeInTheDocument();
    expect(draft).toHaveValue("x".repeat(141));
    expect(screen.getByRole("button", { name: "Send SMS" })).toBeDisabled();
    fireEvent.change(draft, { target: { value: "A confirmed reply" } });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Send SMS" })); });
    expect(vi.mocked(inboxApi.send).mock.calls[0][0].payload).toMatchObject({ expected_version: 8, channel_account_id: "callrail-account" });
    expect(screen.getByLabelText("SMS sender")).toHaveValue("binding-1");
  });
  it("disables sender changes while an original send outcome is unknown", async () => {
    const current = { ...row, context: { ...row.context, smsProvider: "callrail", selectedSenderId: "binding-1", smsSenderOptions: [{ id: "binding-1", provider: "callrail" as const, senderNumber: "+19809071896" }] } };
    vi.mocked(inboxApi.list).mockResolvedValue([current]);
    vi.mocked(inboxApi.detail).mockResolvedValue(current);
    vi.mocked(inboxApi.send).mockRejectedValue(new Error("Network unavailable"));
    render(<ConnectedInbox />);
    await compose();
    fireEvent.click(screen.getByRole("button", { name: "Send SMS" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("SMS sender")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send SMS" })).toBeDisabled();
    expect(inboxApi.changeSender).not.toHaveBeenCalled();
  });
  it("blocks stale sending when a failed sender update cannot be reconciled", async () => {
    const current = { ...row, context: { ...row.context, selectedSenderId: "twilio", smsSenderOptions: [{ id: "binding-1", provider: "callrail" as const, senderNumber: "+19809071896" }] } };
    vi.mocked(inboxApi.list).mockResolvedValue([current]);
    vi.mocked(inboxApi.detail).mockResolvedValue(current);
    vi.mocked(inboxApi.changeSender).mockRejectedValue(new Error("Network unavailable"));
    render(<ConnectedInbox />);
    await compose();
    await waitFor(() => expect(inboxApi.detail).toHaveBeenCalled());
    vi.mocked(inboxApi.detail).mockRejectedValue(new Error("Network unavailable"));
    fireEvent.change(screen.getByLabelText("SMS sender"), { target: { value: "binding-1" } });
    await screen.findByText("The SMS connection changed. Refresh before replying.");
    expect(screen.getByRole("textbox", { name: "Message draft" })).toHaveValue("A safe reply");
    expect(screen.getByRole("button", { name: "Send SMS" })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Message draft" }), { key: "Enter", ctrlKey: true });
    expect(inboxApi.send).not.toHaveBeenCalled();
  });
  it("changes sender with server confirmation, preserves overlimit drafts, and sends with returned version", async () => {
    const options = [
      { id: "twilio", provider: "twilio" as const, senderNumber: "+17045550000" },
      { id: "binding-1", provider: "callrail" as const, senderNumber: "+19809071896" },
    ];
    const initial = { ...row, context: { ...row.context, smsProvider: "twilio", selectedSenderId: "twilio", smsSenderOptions: options } };
    const updated = { ...initial, version: 8, channelAccountId: "callrail-account", sendPolicy: { ...row.sendPolicy, maxLength: 140 }, context: { ...initial.context, smsProvider: "callrail", selectedSenderId: "binding-1", senderNumber: "+19809071896" } };
    vi.mocked(inboxApi.list).mockResolvedValue([initial]);
    vi.mocked(inboxApi.detail).mockResolvedValue(initial);
    let finish!: (value: typeof updated) => void;
    vi.mocked(inboxApi.changeSender).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    vi.mocked(inboxApi.send).mockResolvedValue({ id: "operation", conversation_id: row.id, state: "pending", delivery_status: "pending" });
    render(<ConnectedInbox />);
    const draft = await screen.findByRole("textbox", { name: "Message draft" });
    fireEvent.change(draft, { target: { value: "x".repeat(141) } });
    fireEvent.change(screen.getByLabelText("SMS sender"), { target: { value: "binding-1" } });
    expect(inboxApi.changeSender).toHaveBeenCalledWith(expect.objectContaining({ version: 2 }), "binding-1");
    expect(screen.getByLabelText("SMS sender")).toBeDisabled();
    fireEvent.keyDown(draft, { key: "Enter", ctrlKey: true });
    expect(inboxApi.send).not.toHaveBeenCalled();
    finish(updated);
    await waitFor(() => expect(screen.getByText("141/140")).toBeInTheDocument());
    expect(draft).toHaveValue("x".repeat(141));
    expect(screen.getByRole("button", { name: "Send SMS" })).toBeDisabled();
    fireEvent.change(draft, { target: { value: "x".repeat(140) } });
    fireEvent.click(screen.getByRole("button", { name: "Send SMS" }));
    await waitFor(() => expect(inboxApi.send).toHaveBeenCalledTimes(1));
    expect(vi.mocked(inboxApi.send).mock.calls[0][0].payload).toMatchObject({ expected_version: 8, channel_account_id: "callrail-account" });
  });
  it("routes the Twilio sender choice as null", async () => {
    const options = [{ id: "twilio", provider: "twilio" as const, senderNumber: "+17045550000" }, { id: "binding-disabled", provider: "callrail" as const, senderNumber: "+19809071896", enabled: false }];
    const current = { ...row, context: { ...row.context, smsProvider: "callrail", selectedSenderId: "binding-disabled", senderNumber: "+19809071896", smsSenderOptions: options } };
    vi.mocked(inboxApi.list).mockResolvedValue([current]);
    vi.mocked(inboxApi.detail).mockResolvedValue(current);
    vi.mocked(inboxApi.changeSender).mockResolvedValue({ ...row, context: { ...row.context, selectedSenderId: "twilio", smsSenderOptions: options } });
    render(<ConnectedInbox />);
    await screen.findByRole("textbox", { name: "Message draft" });
    expect(screen.getByRole("option", { name: /CallRail.*unavailable/ })).toBeDisabled();
    expect(screen.getByLabelText("SMS sender")).toHaveValue("binding-disabled");
    fireEvent.change(screen.getByLabelText("SMS sender"), { target: { value: "twilio" } });
    await waitFor(() => expect(inboxApi.changeSender).toHaveBeenCalledWith(expect.objectContaining({ id: row.id }), null));
  });
  it("shows the CallRail sender, preserves drafts, and blocks 141 characters on click and keyboard", async () => {
    const callrailRow = {
      ...row,
      context: { ...row.context, smsProvider: "callrail", senderNumber: "+19809071896", selectedSenderId: "binding-1", smsSenderOptions: [{ id: "binding-1", provider: "callrail" as const, senderNumber: "+19809071896" }] },
      sendPolicy: { ...row.sendPolicy, maxLength: 140 },
    };
    vi.mocked(inboxApi.list).mockResolvedValue([callrailRow]);
    vi.mocked(inboxApi.detail).mockResolvedValue(callrailRow);
    render(<ConnectedInbox />);
    const draft = await screen.findByRole("textbox", { name: "Message draft" });
    expect(screen.getByLabelText("SMS sender")).toHaveTextContent("CallRail +19809071896");
    fireEvent.change(draft, { target: { value: "x".repeat(141) } });
    expect(screen.getByText("141/140")).toHaveClass("over-limit");
    const send = screen.getByRole("button", { name: "Send SMS" });
    expect(send).toBeDisabled();
    fireEvent.click(send);
    fireEvent.keyDown(draft, { key: "Enter", ctrlKey: true });
    expect(inboxApi.send).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Reply channel"), { target: { value: "whatsapp" } });
    expect(screen.queryByLabelText("SMS sender")).not.toBeInTheDocument();
    expect(screen.getByText("0/1600")).toBeInTheDocument();
    fireEvent.change(draft, { target: { value: "WhatsApp draft" } });
    fireEvent.change(screen.getByLabelText("Reply channel"), { target: { value: "sms" } });
    expect(draft).toHaveValue("x".repeat(141));
    expect(inboxApi.send).not.toHaveBeenCalled();
  });
  it("allows exactly 140 CallRail characters through the keyboard send path", async () => {
    const callrailRow = {
      ...row,
      context: { ...row.context, smsProvider: "callrail", senderNumber: "+19809071896", selectedSenderId: "binding-1", smsSenderOptions: [{ id: "binding-1", provider: "callrail" as const, senderNumber: "+19809071896" }] },
      sendPolicy: { ...row.sendPolicy, maxLength: 140 },
    };
    vi.mocked(inboxApi.list).mockResolvedValue([callrailRow]);
    vi.mocked(inboxApi.detail).mockResolvedValue(callrailRow);
    vi.mocked(inboxApi.send).mockResolvedValue({ id: "operation", conversation_id: row.id, state: "pending", delivery_status: "pending" });
    render(<ConnectedInbox />);
    const draft = await screen.findByRole("textbox", { name: "Message draft" });
    fireEvent.change(draft, { target: { value: "x".repeat(140) } });
    expect(screen.getByRole("button", { name: "Send SMS" })).toBeEnabled();
    fireEvent.keyDown(draft, { key: "Enter", ctrlKey: true });
    await waitFor(() => expect(inboxApi.send).toHaveBeenCalledTimes(1));
    expect(vi.mocked(inboxApi.send).mock.calls[0][0].payload.body).toBe("x".repeat(140));
  });
  it("keeps existing SMS defaults at 1600 without inventing provider metadata", async () => {
    render(<ConnectedInbox />);
    const draft = await screen.findByRole("textbox", { name: "Message draft" });
    fireEvent.change(draft, { target: { value: "x".repeat(1600) } });
    expect(screen.getByText("1600/1600")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send SMS" })).toBeEnabled();
    expect(screen.queryByLabelText("SMS sender")).not.toBeInTheDocument();
    fireEvent.change(draft, { target: { value: "x".repeat(1601) } });
    expect(screen.getByRole("button", { name: "Send SMS" })).toBeDisabled();
  });
  it("locks concurrent clicks until durable acceptance, never inventing delivery", async () => {
    let finish!: (value: {
      id: string;
      conversation_id: string;
      state: string;
      delivery_status: string;
    }) => void;
    vi.mocked(inboxApi.send).mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    render(<ConnectedInbox />);
    await compose();
    const send = screen.getByRole("button", { name: "Send SMS" });
    fireEvent.click(send);
    fireEvent.click(send);
    expect(inboxApi.send).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(storeKey)).toContain("A safe reply");
    finish({
      id: "operation",
      conversation_id: row.id,
      state: "pending",
      delivery_status: "pending",
    });
    await waitFor(() => expect(localStorage.getItem(storeKey)).toBeNull());
    expect(screen.getByRole("textbox", { name: "Message draft" })).toHaveValue(
      "",
    );
  });
  it("preserves the exact intent across network failure and reload, and clears only the submitted draft", async () => {
    vi.mocked(inboxApi.send)
      .mockRejectedValueOnce(new Error("connection lost"))
      .mockResolvedValue({
        id: "operation",
        conversation_id: row.id,
        state: "accepted",
        delivery_status: "queued",
      });
    const first = render(<ConnectedInbox />);
    await compose();
    fireEvent.click(screen.getByRole("button", { name: "Send SMS" }));
    await screen.findByRole("alert");
    const intent = JSON.parse(localStorage.getItem(storeKey)!);
    first.unmount();
    render(<ConnectedInbox />);
    await screen.findByRole("textbox", { name: "Message draft" });
    fireEvent.change(screen.getByRole("textbox", { name: "Message draft" }), {
      target: { value: "A newer draft" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Check original send" }),
    );
    await waitFor(() => expect(inboxApi.send).toHaveBeenCalledTimes(2));
    expect(vi.mocked(inboxApi.send).mock.calls[1][0]).toEqual(intent);
    await waitFor(() => expect(localStorage.getItem(storeKey)).toBeNull());
    expect(screen.getByRole("textbox", { name: "Message draft" })).toHaveValue(
      "A newer draft",
    );
  });
  it("retains uncertain intent on idempotency conflict", async () => {
    vi.mocked(inboxApi.send).mockRejectedValue({
      response: {
        status: 409,
        data: {
          detail: {
            code: "idempotency_conflict",
            message: "Original request differs.",
          },
        },
      },
    });
    render(<ConnectedInbox />);
    await compose();
    fireEvent.click(screen.getByRole("button", { name: "Send SMS" }));
    await screen.findByRole("alert");
    expect(localStorage.getItem(storeKey)).not.toBeNull();
    expect(screen.getByRole("button", { name: "Send SMS" })).toBeDisabled();
  });
  it("blocks sends when a saved recovery record is unreadable", async () => {
    localStorage.setItem(storeKey, "{broken");
    render(<ConnectedInbox />);
    await compose();
    expect(screen.getByRole("button", { name: "Send SMS" })).toBeDisabled();
    expect(inboxApi.send).not.toHaveBeenCalled();
  });
});

describe("SMS setup entry", () => {
  it("offers setup to shop owners with an empty inbox", async () => {
    (useAuthStore.getState() as unknown as { user: { role: string } }).user = {
      role: "garage_owner",
    };
    vi.mocked(inboxApi.list).mockResolvedValue([]);
    render(<ConnectedInbox />);
    expect(
      await screen.findByRole("button", { name: "SMS setup" }),
    ).toBeVisible();
  });
  it("hides registration actions from reception staff", async () => {
    (useAuthStore.getState() as unknown as { user: { role: string } }).user = {
      role: "receptionist",
    };
    render(<ConnectedInbox />);
    await screen.findByRole("textbox", { name: "Message draft" });
    expect(
      screen.queryByRole("button", { name: "SMS setup" }),
    ).not.toBeInTheDocument();
  });
});

describe("dashboard inbox integration", () => {
  it("separates real history by the same New York calendar days as message times", async () => {
    const history = {
      ...row,
      messages: [
        {
          ...row.messages[0],
          id: "friday",
          body: "Before midnight",
          createdAt: "2026-10-17T03:55:00Z",
        },
        {
          ...row.messages[0],
          id: "saturday",
          body: "After midnight",
          createdAt: "2026-10-17T04:05:00Z",
        },
      ],
    };
    vi.mocked(inboxApi.list).mockResolvedValue([history]);
    vi.mocked(inboxApi.detail).mockResolvedValue(history);
    render(<DashboardInboxPage />);
    expect(
      await screen.findByText("Friday, October 16, 2026"),
    ).toBeInTheDocument();
    expect(screen.getByText("Saturday, October 17, 2026")).toBeInTheDocument();
    expect(screen.getByText("Before midnight")).toBeInTheDocument();
    expect(screen.getByText("After midnight")).toBeInTheDocument();
  });

  it("explains the existing routing hold without enabling sending", async () => {
    const held = {
      ...row,
      sendPolicy: { canSend: false, reason: "routing_disabled" as const },
    };
    vi.mocked(inboxApi.list).mockResolvedValue([held]);
    vi.mocked(inboxApi.detail).mockResolvedValue(held);
    render(<DashboardInboxPage />);
    expect(
      await screen.findByText(
        "SMS routing for this shop is awaiting activation.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send SMS" })).toBeDisabled();
    expect(inboxApi.send).not.toHaveBeenCalled();
  });

  it("loads real API rows inside the dashboard without prototype chrome or sample contacts", async () => {
    render(<DashboardInboxPage />);
    await screen.findByRole("textbox", { name: "Message draft" });
    expect(inboxApi.bootstrap).toHaveBeenCalledTimes(1);
    expect(inboxApi.list).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByLabelText("DieselBridge workspace"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Connected inbox")).not.toBeInTheDocument();
    expect(screen.queryByText("Interactive prototype")).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: row.customerName }),
    ).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message draft" })).toHaveValue(
      "",
    );
    expect(inboxApi.send).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(unreadCache.setQueryData).toHaveBeenLastCalledWith(
        ["messages-unread-summary"],
        { unread_count_staff: 0 },
      ),
    );
  });

  it("shows an empty API inbox without falling back to demo conversations", async () => {
    vi.mocked(inboxApi.list).mockResolvedValue([]);
    render(<DashboardInboxPage />);
    expect(await screen.findByText(/No conversations yet/)).toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: "Message draft" }),
    ).not.toBeInTheDocument();
    expect(inboxApi.detail).not.toHaveBeenCalled();
    expect(inboxApi.send).not.toHaveBeenCalled();
  });
});
