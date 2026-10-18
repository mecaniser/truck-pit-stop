import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ConnectedInbox from "./ConnectedInbox";
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
