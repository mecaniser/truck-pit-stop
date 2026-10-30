import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SMSSetup from "./SMSSetup";
import SMSConsentPanel from "./SMSConsentPanel";
import { smsOnboardingApi, type SMSOnboarding } from "./smsOnboardingApi";
vi.mock("./smsOnboardingApi", () => ({
  smsOnboardingApi: {
    get: vi.fn(),
    save: vi.fn(),
    review: vi.fn(),
    package: vi.fn(),
    consents: vi.fn(),
    recordConsent: vi.fn(),
  },
}));
const record: SMSOnboarding = {
  version: 1,
  status: "draft",
  submission_enabled: false,
  fields: {
    legal_name: "Shop A LLC",
    trade_name: "Shop A",
    website_url: "https://a.example",
    support_email: "help@a.example",
    support_phone: "+15005550001",
    consent_source_url: "https://a.example/sms",
    privacy_url: "https://a.example/privacy",
    terms_url: "https://a.example/terms",
    representative_name: "Owner A",
    representative_email: "owner@a.example",
    message_description: "Repair updates",
    sample_messages: ["Shop A repair is ready."],
  },
  blockers: ["provider_registration_required"],
  connection: {
    status: "not_configured",
    sender_last4: null,
    registration_status: null,
    verified_at: null,
  },
  rejection_reason: null,
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(smsOnboardingApi.get).mockResolvedValue(record);
  vi.mocked(smsOnboardingApi.consents).mockResolvedValue([]);
});
afterEach(cleanup);
describe("SMS onboarding", () => {
  it("explains purpose and next step without treating a configured sender as approval", async () => {
    vi.mocked(smsOnboardingApi.get).mockResolvedValue({...record, connection: {...record.connection, status: "legacy_configured", sender_last4: "0001"}, fields: {...record.fields, legal_name: null}, blockers: ["legal_name_required", "provider_registration_required"]});
    render(<SMSSetup onClose={vi.fn()} />);
    await screen.findByText("Next: complete the registration draft");
    expect(screen.getByText(/does not submit to Twilio or turn on automatic messages/)).toBeVisible();
    expect(screen.getByText("1 required item left")).toBeVisible();
    expect(screen.queryByText("legal name required", {exact: false})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {name: "Registration status and number"}));
    expect(screen.getByText(/does not confirm approval for repair texting/)).toBeVisible();
    expect(screen.getByLabelText("Legal business name")).toHaveAttribute("aria-required", "true");
    expect(smsOnboardingApi.review).not.toHaveBeenCalled();
  });

  it("saves tenant draft with version and requires saved draft for review", async () => {
    vi.mocked(smsOnboardingApi.save).mockResolvedValue({
      ...record,
      version: 2,
      fields: { ...record.fields, trade_name: "Changed shop" },
    });
    vi.mocked(smsOnboardingApi.review).mockResolvedValue({
      ...record,
      version: 3,
      status: "ready_for_review",
    });
    render(<SMSSetup onClose={vi.fn()} />);
    const input = await screen.findByLabelText("Shop / trade name");
    fireEvent.change(input, { target: { value: "Changed shop" } });
    expect(
      screen.getByRole("button", { name: "Prepare for review" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await screen.findByText("Draft saved.");
    expect(smsOnboardingApi.save).toHaveBeenCalledWith(
      { ...record.fields, trade_name: "Changed shop" },
      1,
    );
    fireEvent.click(screen.getByRole("button", { name: "Prepare for review" }));
    await screen.findByText(
      "Prepared for review. Registration remains on hold.",
    );
    expect(smsOnboardingApi.review).toHaveBeenCalledWith(2);
    expect(
      screen.queryByRole("button", { name: /submit to twilio|activate/i }),
    ).not.toBeInTheDocument();
  });
  it("keeps edits on failure and conflicts, then rebases only the version", async () => {
    vi.mocked(smsOnboardingApi.save).mockRejectedValue({
      response: { status: 409 },
    });
    render(<SMSSetup onClose={vi.fn()} />);
    const input = await screen.findByLabelText("Legal business name");
    fireEvent.change(input, { target: { value: "Unsaved legal name" } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await screen.findByRole("alert");
    expect(input).toHaveValue("Unsaved legal name");
    vi.mocked(smsOnboardingApi.get).mockResolvedValue({
      ...record,
      version: 5,
    });
    fireEvent.click(
      screen.getByRole("button", {
        name: "Load latest version and keep my edits",
      }),
    );
    await screen.findByText(/Latest version loaded/);
    expect(input).toHaveValue("Unsaved legal name");
    vi.mocked(smsOnboardingApi.save).mockResolvedValue({
      ...record,
      version: 6,
    });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() =>
      expect(smsOnboardingApi.save).toHaveBeenLastCalledWith(
        { ...record.fields, legal_name: "Unsaved legal name" },
        5,
      ),
    );
  });
  it("discards late request results after tenant scope unmount", async () => {
    let resolve!: (v: SMSOnboarding) => void;
    vi.mocked(smsOnboardingApi.get).mockReturnValueOnce(
      new Promise((r) => {
        resolve = r;
      }),
    );
    const { unmount } = render(<SMSSetup onClose={vi.fn()} />);
    unmount();
    render(<SMSSetup onClose={vi.fn()} />);
    await screen.findByDisplayValue("Shop A LLC");
    resolve({
      ...record,
      fields: { ...record.fields, legal_name: "Foreign tenant" },
    });
    await waitFor(() =>
      expect(
        screen.queryByDisplayValue("Foreign tenant"),
      ).not.toBeInTheDocument(),
    );
  });
  it("collapses permissions without hiding withdrawal warnings or changing consent", async () => {
    vi.mocked(smsOnboardingApi.consents).mockResolvedValue([{id: "withdrawal", customer_id: "customer-a", phone_last4: "0001", purpose: "service_notifications", status: "withdrawn", source: "STOP", disclosure_version: "v1", collected_at: "2026-10-16T12:00:00Z", created_at: "2026-10-16T12:00:00Z"}]);
    render(<SMSConsentPanel customerId="customer-a" />);
    const toggle = screen.getByRole("button", {name: "SMS permissions"});
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(await screen.findByText("SMS consent withdrawn")).toBeVisible();
    expect(screen.queryByRole("button", {name: "Record consent evidence"})).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.getByRole("button", {name: "Record consent evidence"})).toBeVisible();
    fireEvent.click(toggle);
    expect(screen.getByText("SMS consent withdrawn")).toBeVisible();
    expect(smsOnboardingApi.recordConsent).not.toHaveBeenCalled();
  });
  it("requires explicit evidence before recording current customer consent", async () => {
    vi.mocked(smsOnboardingApi.recordConsent).mockResolvedValue({
      id: "evidence",
      customer_id: "customer-a",
      phone_last4: "0001",
      purpose: "service_notifications",
      status: "granted",
      source: "intake",
      disclosure_version: "v1",
      collected_at: "2026-10-16T12:00:00Z",
      created_at: "2026-10-16T12:00:00Z",
    });
    render(<SMSConsentPanel customerId="customer-a" />);
    fireEvent.click(screen.getByRole("button", {name: "SMS permissions"}));
    await screen.findByText("No recorded consent");
    fireEvent.click(
      screen.getByRole("button", { name: "Record consent evidence" }),
    );
    expect(screen.getByRole("button", { name: "Record grant" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Evidence source"), {
      target: { value: "Signed intake" },
    });
    fireEvent.change(screen.getByLabelText("Disclosure version"), {
      target: { value: "v1" },
    });
    fireEvent.change(screen.getByLabelText("Collected at"), {
      target: { value: "2026-10-16T12:00" },
    });
    expect(screen.getByRole("button", { name: "Record grant" })).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Record grant" }));
    await waitFor(() =>
      expect(smsOnboardingApi.recordConsent).toHaveBeenCalledWith(
        expect.objectContaining({
          customer_id: "customer-a",
          status: "granted",
          source: "Signed intake",
          disclosure_version: "v1",
        }),
      ),
    );
  });
});
