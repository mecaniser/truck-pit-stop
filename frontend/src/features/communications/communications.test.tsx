import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CommunicationsPreview from "./CommunicationsPreview";
import { createDemoConversations, DEMO_TENANT, DEMO_USER } from "./fixtures";
import { canCompose, draftKey, filterConversations } from "./model";

// jsdom has no layout observer; real layout/anchoring is covered in browser QA.
beforeEach(() => vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => vi.unstubAllGlobals());
afterEach(cleanup);
describe("shared inbox foundation", () => {
  it("updates linked inquiry labels in list and header without resetting its draft or sender", () => {
    const row = {...createDemoConversations()[0], conversationKind: "inquiry" as const, customerId: null, customerName: "New inquiry", company: null};
    const connection = {rows: [row], tenantId: DEMO_TENANT, userId: DEMO_USER, people: {}, deliveryMode: "simulated", busy: false, error: "", pending: false, onSelect: vi.fn(), onSend: vi.fn(), onPatch: vi.fn(), onOlder: vi.fn(), onRecover: vi.fn()};
    const {rerender} = render(<CommunicationsPreview connection={connection} />);
    fireEvent.change(screen.getByRole("textbox", {name: "Message draft"}), {target: {value: "Keep this draft"}});
    const key = draftKey(DEMO_TENANT, DEMO_USER, row);
    const linked = {...row, customerName: "Taylor Driver", company: "Example Fleet"};
    rerender(<CommunicationsPreview connection={{...connection, rows: [linked]}} />);
    expect(screen.getByRole("heading", {name: "Taylor Driver", level: 2})).toBeVisible();
    expect(screen.getAllByText("Example Fleet").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("New inquiry")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", {name: "Message draft"})).toHaveValue("Keep this draft");
    expect(draftKey(DEMO_TENANT, DEMO_USER, linked)).toBe(key);
    expect(linked.context.senderNumber).toBe(row.context.senderNumber);
  });
  it("filters inquiries without guessing customers and searches remote and receiving phone numbers", () => {
    const customer = createDemoConversations()[0];
    const inquiry = { ...customer, id: "inquiry", conversationKind: "inquiry" as const, customerId: null, customerName: "New inquiry", company: null, identityLabel: "+15005550002", context: { smsProvider: "callrail", senderNumber: "+15005550001" } };
    const foreign = { ...inquiry, id: "foreign", tenantId: "other-tenant" };
    const resolved = { ...inquiry, id: "resolved", status: "resolved" as const };
    expect(filterConversations([customer, inquiry, foreign, resolved], DEMO_TENANT, "inquiries", "all", "", DEMO_USER).map((r) => r.id)).toEqual(["inquiry"]);
    for (const phone of ["15005550002", "15005550001"])
      expect(filterConversations([inquiry], DEMO_TENANT, "open", "sms", phone, DEMO_USER)).toEqual([inquiry]);
    expect(filterConversations([inquiry], DEMO_TENANT, "resolved", "sms", "", DEMO_USER)).toEqual([]);
  });
  it("isolates tenant records and supports repair-order and message search", () => {
    const rows = createDemoConversations();
    const otherTenant = { ...rows[0], id: "other", tenantId: "other-shop" };
    const result = filterConversations(
      [...rows, otherTenant],
      DEMO_TENANT,
      "open",
      "sms",
      "RO-1048",
      DEMO_USER,
    );
    expect(result.map((row) => row.id)).toEqual(["01"]);
    expect(
      filterConversations(
        rows,
        DEMO_TENANT,
        "open",
        "sms",
        "coolant leak",
        DEMO_USER,
      ).map((row) => row.id),
    ).toEqual(["02"]);
  });
  it("draft identity changes for tenant, user, recipient, conversation, sender and channel", () => {
    const row = createDemoConversations()[0];
    const keys = [
      draftKey(DEMO_TENANT, DEMO_USER, row),
      draftKey("other", DEMO_USER, row),
      draftKey(DEMO_TENANT, "other", row),
      draftKey(DEMO_TENANT, DEMO_USER, { ...row, id: "other" }),
      draftKey(DEMO_TENANT, DEMO_USER, { ...row, channelAccountId: "other" }),
      draftKey(DEMO_TENANT, DEMO_USER, { ...row, contactIdentityId: "other" }),
      draftKey(DEMO_TENANT, DEMO_USER, { ...row, channel: "telegram" }),
    ];
    expect(new Set(keys).size).toBe(keys.length);
  });
  it("fails closed on contradictory policy, opt-out and excessive length", () => {
    const row = createDemoConversations()[0];
    expect(canCompose(row, "Hi")).toBe(true);
    expect(canCompose(row, "   ")).toBe(false);
    expect(canCompose(row, "x".repeat(1601))).toBe(false);
    expect(
      canCompose(
        { ...row, sendPolicy: { canSend: true, reason: "opted_out" } },
        "Hi",
      ),
    ).toBe(false);
    expect(
      canCompose(
        { ...row, sendPolicy: { canSend: false, reason: null } },
        "Hi",
      ),
    ).toBe(false);
  });
  it("keeps CallRail's provider cap when optional policy is absent and existing Twilio capacity unchanged", () => {
    const row = createDemoConversations()[0];
    const callrail = { ...row, context: { ...row.context, smsProvider: "callrail" } };
    expect(canCompose(callrail, "x".repeat(140))).toBe(true);
    expect(canCompose(callrail, "x".repeat(141))).toBe(false);
    expect(canCompose({ ...row, context: { ...row.context, smsProvider: "twilio" } }, "x".repeat(1600))).toBe(true);
  });
  it("keeps separate drafts across contacts and channels and blocks unavailable channel sends", () => {
    render(<CommunicationsPreview />);
    const draft = screen.getByRole("textbox", { name: "Message draft" });
    fireEvent.change(draft, { target: { value: "SMS draft" } });
    fireEvent.click(screen.getByRole("button", {name: "Reply channel"}));
    fireEvent.click(screen.getByRole("option", {name: "WhatsApp"}));
    expect(draft).toHaveValue("");
    fireEvent.change(draft, { target: { value: "WhatsApp draft" } });
    expect(screen.getByRole("button", { name: "Send preview" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", {name: "Reply channel"}));
    fireEvent.click(screen.getByRole("option", {name: "SMS"}));
    expect(draft).toHaveValue("SMS draft");
    fireEvent.click(
      screen.getByRole("button", { name: /Maria Torres.*Blue Ridge/ }),
    );
    expect(draft).toHaveValue("");
    fireEvent.click(
      screen.getByRole("button", { name: /Daniel Brooks.*Northline/ }),
    );
    expect(draft).toHaveValue("SMS draft");
    fireEvent.click(screen.getByRole("button", {name: "Reply channel"}));
    fireEvent.click(screen.getByRole("option", {name: "WhatsApp"}));
    expect(draft).toHaveValue("WhatsApp draft");
  });
  it("adds one preview message, clears only its draft, and does not pretend delivery", () => {
    render(<CommunicationsPreview />);
    fireEvent.change(screen.getByRole("textbox", { name: "Message draft" }), {
      target: { value: "A preview reply" },
    });
    const send = screen.getByRole("button", { name: "Send preview" });
    fireEvent.click(send);
    expect(send).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "Message draft" })).toHaveValue(
      "",
    );
    const conversation = screen.getByRole("region", {
      name: "Conversation with Daniel Brooks",
    });
    expect(within(conversation).getAllByText("A preview reply")).toHaveLength(
      1,
    );
    expect(within(conversation).getByText("Preview only")).toBeInTheDocument();
    expect(
      screen.getByText("Added to the preview. No message was sent."),
    ).toBeInTheDocument();
  });
  it("supports resolution, assignment and hiding automated notices", () => {
    render(<CommunicationsPreview />);
    fireEvent.click(screen.getByRole("button", {name: "Assign conversation"}));
    fireEvent.click(screen.getByRole("option", {name: "Nina"}));
    expect(screen.getByLabelText("Assign conversation")).toHaveTextContent("Nina");
    fireEvent.click(screen.getByRole("button", { name: "Service updates" }));
    expect(
      screen.queryByText(
        "Unit 204 is ready for pickup. Your invoice is available in the customer portal.",
      ),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resolve" }));
    expect(screen.getByRole("button", { name: "Reopen" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Resolved/ }));
    expect(
      screen.getByRole("button", { name: /Daniel Brooks.*Northline/ }),
    ).toBeInTheDocument();
  });
  it("preserves an opted-out draft without allowing send", () => {
    render(<CommunicationsPreview />);
    fireEvent.click(
      screen.getByRole("button", { name: /Ethan Cole.*Cole Transport/ }),
    );
    fireEvent.change(screen.getByRole("textbox", { name: "Message draft" }), {
      target: { value: "Do not send" },
    });
    expect(
      screen.getByText("This contact has opted out of SMS."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send preview" })).toBeDisabled();
  });
});
