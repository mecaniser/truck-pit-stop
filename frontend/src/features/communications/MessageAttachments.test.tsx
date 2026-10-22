import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MessageAttachments from "./MessageAttachments";
import CommunicationsPreview, { type InboxConnection } from "./CommunicationsPreview";
import { inboxApi } from "./api";
import { useAuthStore } from "../../stores/authStore";
import { createDemoConversations, DEMO_TENANT, DEMO_USER } from "./fixtures";
import type { Message } from "./model";
vi.mock("./SMSConsentPanel", () => ({ default: () => null }));
vi.mock("./api", () => ({ inboxApi: { attachmentManifest: vi.fn(), attachmentBlob: vi.fn() } }));
vi.mock("../../lib/sessionKeepAlive", () => ({ startSessionKeepAlive: vi.fn(), stopSessionKeepAlive: vi.fn() }));
const notice = "[Attachment received in CallRail. Open CallRail to view.]";
const message: Message = { id: "receipt", conversationId: "thread", channel: "sms", direction: "inbound", source: "customer", body: `Synthetic caption\n\n${notice}`, createdAt: "2026-10-21T16:10:13.068-04:00", deliveryStatus: "received", hasAttachments: true };
const blob = () => new Blob(["synthetic raster"], { type: "image/png" });
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>((yes) => { resolve = yes; }); return { promise, resolve }; }
const manifest = vi.mocked(inboxApi.attachmentManifest);
const content = vi.mocked(inboxApi.attachmentBlob);
const create = vi.fn(); const revoke = vi.fn();
beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear();
  useAuthStore.setState({ isAuthenticated: true, logoutInProgress: false, authSessionEpoch: 1, authProvider: "legacy", user: { id: DEMO_USER, tenant_id: DEMO_TENANT, is_active: true, role: "garage_owner" } as NonNullable<ReturnType<typeof useAuthStore.getState>["user"]> });
  let next = 0;
  create.mockImplementation(() => `blob:synthetic-${++next}`);
  URL.createObjectURL = create; URL.revokeObjectURL = revoke;
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
  manifest.mockResolvedValue({ items: [{ index: 0, kind: "image" }] }); content.mockImplementation(async () => blob());
});
afterEach(cleanup);
const mount = (m = message) => render(<MessageAttachments tenantId={DEMO_TENANT} message={m} />);

describe("authenticated incoming MMS images", () => {
  it("keeps one loading status through discovery and image retrieval, then removes it", async () => {
    const discovery = deferred<{ items: { index: number; kind: "image" }[] }>();
    const image = deferred<Blob>();
    manifest.mockReturnValueOnce(discovery.promise); content.mockReturnValueOnce(image.promise);
    mount(); expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent("Loading images…");
    expect(screen.getByText("Synthetic caption")).toBeInTheDocument();
    expect(screen.queryByText(notice, { exact: false })).not.toBeInTheDocument();
    await act(async () => discovery.resolve({ items: [{ index: 0, kind: "image" }] }));
    await waitFor(() => expect(content).toHaveBeenCalledTimes(1));
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent("Loading images…");
    expect(screen.queryByText(notice, { exact: false })).not.toBeInTheDocument();
    await act(async () => image.resolve(blob()));
    await screen.findByRole("img");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
  it("loads media, keeps caption, hides only the trailing receipt and revokes on unmount", async () => {
    const view = mount(); expect(screen.getByRole("status")).toHaveTextContent("Loading images");
    const image = await screen.findByRole("img"); expect(image).toHaveAttribute("src", "blob:synthetic-1"); expect(image).toHaveAttribute("referrerpolicy", "no-referrer");
    expect(screen.getByText("Synthetic caption")).toBeInTheDocument(); expect(screen.queryByText(notice, { exact: false })).not.toBeInTheDocument();
    expect(content).toHaveBeenCalledWith("thread", "receipt", 0, expect.any(AbortSignal)); expect(document.body.innerHTML).not.toMatch(/api\.callrail|Bearer|media_url/);
    view.unmount(); expect(revoke).toHaveBeenCalledWith("blob:synthetic-1");
  });
  it("opens expanded viewing, closes on Escape and restores focus", async () => {
    mount(); const trigger = await screen.findByRole("button", { name: "Open received image 1" }); fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Received image" }); expect(screen.getByRole("button", { name: "Close image" })).toHaveFocus(); expect(screen.getAllByRole("img")).toHaveLength(2);
    fireEvent(dialog, new Event("cancel", { bubbles: false, cancelable: true })); expect(screen.queryByRole("dialog")).not.toBeInTheDocument(); expect(trigger).toHaveFocus(); expect(content).toHaveBeenCalledTimes(1);
  });
  it.each(["empty", "error"])("retains the notice for %s and manually retries", async (mode) => {
    if (mode === "empty") manifest.mockResolvedValueOnce({ items: [] }); else manifest.mockRejectedValueOnce(new Error("private upstream context must not appear"));
    mount(); const retry = await screen.findByRole("button", { name: "Retry" }); expect(screen.getByText(notice, { exact: false })).toBeInTheDocument(); fireEvent.click(retry);
    await screen.findByRole("img"); expect(manifest).toHaveBeenCalledTimes(2); expect(document.body.innerHTML).not.toContain("private upstream");
  });
  it("bounds all receipts to two blob requests and preserves slot order", async () => {
    const requests = Array.from({ length: 4 }, () => deferred<Blob>()); manifest.mockResolvedValue({ items: [{ index: 0, kind: "image" }, { index: 1, kind: "image" }] }); let n = 0; content.mockImplementation(() => requests[n++].promise);
    render(<><MessageAttachments tenantId={DEMO_TENANT} message={message} /><MessageAttachments tenantId={DEMO_TENANT} message={{ ...message, id: "receipt2" }} /></>);
    await waitFor(() => expect(content).toHaveBeenCalledTimes(2)); await act(async () => { requests[1].resolve(blob()); }); await waitFor(() => expect(content).toHaveBeenCalledTimes(3));
    await act(async () => { requests[0].resolve(blob()); requests[2].resolve(blob()); }); await waitFor(() => expect(content).toHaveBeenCalledTimes(4)); await act(async () => { requests[3].resolve(blob()); });
    expect(screen.getAllByRole("img").map((img) => img.getAttribute("alt"))).toEqual(["Received MMS image 1", "Received MMS image 2", "Received MMS image 1", "Received MMS image 2"]);
  });
  it("aborts pending operations on unmount and ignores late blobs", async () => {
    const pending = deferred<Blob>(); content.mockReturnValueOnce(pending.promise); const view = mount(); await waitFor(() => expect(content).toHaveBeenCalledTimes(1)); const signal = content.mock.calls[0][3]; view.unmount(); expect(signal.aborted).toBe(true);
    await act(async () => pending.resolve(blob())); expect(create).not.toHaveBeenCalled();
  });
  it("never starts content from a late manifest after logout", async () => {
    const pending = deferred<{ items: { index: number; kind: "image" }[] }>(); manifest.mockReturnValueOnce(pending.promise); mount(); act(() => useAuthStore.setState({ isAuthenticated: false, authSessionEpoch: 2, user: null }));
    await act(async () => pending.resolve({ items: [{ index: 0, kind: "image" }] })); expect(content).not.toHaveBeenCalled(); expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
  it("clears images and viewer immediately on same-user session replacement", async () => {
    mount(); fireEvent.click(await screen.findByRole("button", { name: "Open received image 1" })); manifest.mockReturnValueOnce(new Promise(() => {})); act(() => useAuthStore.setState({ authSessionEpoch: 2 }));
    expect(screen.queryByRole("img")).not.toBeInTheDocument(); expect(screen.queryByRole("dialog")).not.toBeInTheDocument(); expect(revoke).toHaveBeenCalledWith("blob:synthetic-1");
    act(() => useAuthStore.setState({ isAuthenticated: false, user: null })); expect(screen.queryByText("Loading images…")).not.toBeInTheDocument();
  });
  it("discards old thread images and blocks tenant-mismatched requests", async () => {
    const view = mount(); await screen.findByRole("img"); manifest.mockReturnValueOnce(new Promise(() => {})); view.rerender(<MessageAttachments tenantId={DEMO_TENANT} message={{ ...message, conversationId: "next-thread" }} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument(); expect(revoke).toHaveBeenCalledWith("blob:synthetic-1"); act(() => useAuthStore.setState({ user: { ...useAuthStore.getState().user!, tenant_id: "other-shop" } })); expect(screen.queryByText("Loading images…")).not.toBeInTheDocument();
  });
  it("revokes partial images on retry and restores fallback if browser decoding fails", async () => {
    manifest.mockResolvedValueOnce({ items: [{ index: 0, kind: "image" }, { index: 1, kind: "image" }] }); content.mockResolvedValueOnce(blob()).mockRejectedValueOnce(new Error("unavailable")); mount(); await screen.findByRole("img"); fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    await waitFor(() => expect(revoke).toHaveBeenCalledWith("blob:synthetic-1")); fireEvent.error(await screen.findByRole("img")); expect(screen.getByText(notice, { exact: false })).toBeInTheDocument(); expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
  it("rejects malformed manifests and non-raster blobs", async () => {
    manifest.mockResolvedValueOnce({ items: [{ index: 10, kind: "image" }] }); const view = mount(); await screen.findByRole("button", { name: "Retry" }); expect(content).not.toHaveBeenCalled(); view.unmount();
    content.mockResolvedValueOnce(new Blob(["<svg>"], { type: "image/svg+xml" })); mount(); await screen.findByRole("button", { name: "Retry" }); expect(create).not.toHaveBeenCalled();
  });
  it("keeps draft, original time, derived reply number and plain SMS", async () => {
    const row = { ...createDemoConversations()[0], messages: [message, { ...message, id: "plain", body: "Plain SMS", hasAttachments: false }], context: { smsProvider: "callrail", senderMode: "reply" as const, senderNumber: "+15005550001" } };
    const connection: InboxConnection = { rows: [row], tenantId: DEMO_TENANT, userId: DEMO_USER, people: {}, deliveryMode: "live", busy: false, error: "", pending: false, onSelect: vi.fn(), onSend: vi.fn(), onPatch: vi.fn(), onOlder: vi.fn(), onRecover: vi.fn() };
    render(<CommunicationsPreview connection={connection} />); const draft = screen.getByRole("textbox", { name: "Message draft" }); fireEvent.change(draft, { target: { value: "Unsent draft" } }); await screen.findByRole("img");
    expect(draft).toHaveValue("Unsent draft"); expect(screen.getByText("Plain SMS")).toBeInTheDocument(); expect(screen.getAllByText("4:10 PM").length).toBeGreaterThan(0); expect(screen.getByText("+15005550001", { exact: false })).toBeInTheDocument(); expect(screen.queryByRole("combobox", { name: /sender/i })).not.toBeInTheDocument(); expect(connection.onSend).not.toHaveBeenCalled(); expect(connection.onPatch).not.toHaveBeenCalled();
  });
});
