import { beforeEach, expect, it, vi } from "vitest";
import api from "../../lib/api";
import { smsOnboardingApi, type SMSDraft } from "./smsOnboardingApi";
vi.mock("../../lib/api", () => ({
  default: { get: vi.fn(), put: vi.fn(), post: vi.fn() },
}));
beforeEach(() => vi.resetAllMocks());
it("sends blank optional fields as null so partial drafts can be saved", async () => {
  vi.mocked(api.put).mockResolvedValue({ data: { version: 1 } });
  const draft: SMSDraft = {
    legal_name: "Example LLC",
    trade_name: "",
    website_url: "",
    support_email: null,
    support_phone: "",
    consent_source_url: "",
    privacy_url: null,
    terms_url: "",
    representative_name: "",
    representative_email: "",
    message_description: "",
    sample_messages: ["Shop repair update.", ""],
  };
  await smsOnboardingApi.save(draft, 0);
  expect(api.put).toHaveBeenCalledWith("/communications/sms/onboarding", {
    ...draft,
    trade_name: null,
    website_url: null,
    support_phone: null,
    consent_source_url: null,
    terms_url: null,
    representative_name: null,
    representative_email: null,
    message_description: null,
    sample_messages: ["Shop repair update."],
    expected_version: 0,
  });
});
it("prepares a versioned local review without provider submission", async () => {
  vi.mocked(api.post).mockResolvedValue({
    data: { status: "ready_for_review" },
  });
  await smsOnboardingApi.review(3);
  expect(api.post).toHaveBeenCalledWith(
    "/communications/sms/onboarding/review",
    { expected_version: 3 },
  );
});
