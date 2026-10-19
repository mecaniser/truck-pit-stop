import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
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
      older: vi.fn(),
    },
  };
});
const unreadCache = vi.hoisted(() => ({ setQueryData: vi.fn() }));
vi.mock("@tanstack/react-query", () => ({ useQueryClient: () => unreadCache }));
const row = { ...createDemoConversations()[0], version: 2 };
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
afterEach(cleanup);
async function compose() {
  await screen.findByRole("textbox", { name: "Message draft" });
  fireEvent.change(screen.getByRole("textbox", { name: "Message draft" }), {
    target: { value: "A safe reply" },
  });
}
describe("connected inbox sending", () => {
  it("shows the CallRail sender, preserves drafts, and blocks 141 characters on click and keyboard", async () => {
    const callrailRow = {
      ...row,
      context: { ...row.context, smsProvider: "callrail", senderNumber: "+19809071896" },
      sendPolicy: { ...row.sendPolicy, maxLength: 140 },
    };
    vi.mocked(inboxApi.list).mockResolvedValue([callrailRow]);
    vi.mocked(inboxApi.detail).mockResolvedValue(callrailRow);
    render(<ConnectedInbox />);
    const draft = await screen.findByRole("textbox", { name: "Message draft" });
    expect(screen.getByLabelText("SMS sender")).toHaveTextContent("CallRail · +19809071896");
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
      context: { ...row.context, smsProvider: "callrail", senderNumber: "+19809071896" },
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
