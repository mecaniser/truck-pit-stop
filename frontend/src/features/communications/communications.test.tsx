import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import CommunicationsPreview from "./CommunicationsPreview";
import { createDemoConversations, DEMO_TENANT, DEMO_USER } from "./fixtures";
import { canCompose, draftKey, filterConversations } from "./model";

afterEach(cleanup);
describe("shared inbox foundation", () => {
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
  it("keeps separate drafts across contacts and channels and blocks unavailable channel sends", () => {
    render(<CommunicationsPreview />);
    const draft = screen.getByRole("textbox", { name: "Message draft" });
    fireEvent.change(draft, { target: { value: "SMS draft" } });
    fireEvent.change(screen.getByLabelText("Reply channel"), {
      target: { value: "whatsapp" },
    });
    expect(draft).toHaveValue("");
    fireEvent.change(draft, { target: { value: "WhatsApp draft" } });
    expect(screen.getByRole("button", { name: "Send preview" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Reply channel"), {
      target: { value: "sms" },
    });
    expect(draft).toHaveValue("SMS draft");
    fireEvent.click(
      screen.getByRole("button", { name: /Maria Torres.*Blue Ridge/ }),
    );
    expect(draft).toHaveValue("");
    fireEvent.click(
      screen.getByRole("button", { name: /Daniel Brooks.*Northline/ }),
    );
    expect(draft).toHaveValue("SMS draft");
    fireEvent.change(screen.getByLabelText("Reply channel"), {
      target: { value: "whatsapp" },
    });
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
    fireEvent.change(screen.getByLabelText("Assign conversation"), {
      target: { value: "nina" },
    });
    expect(screen.getByLabelText("Assign conversation")).toHaveValue("nina");
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
