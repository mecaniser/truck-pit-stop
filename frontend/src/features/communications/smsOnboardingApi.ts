import api from "../../lib/api";
export interface SMSDraft {
  legal_name: string | null;
  trade_name: string | null;
  website_url: string | null;
  support_email: string | null;
  support_phone: string | null;
  consent_source_url: string | null;
  privacy_url: string | null;
  terms_url: string | null;
  representative_name: string | null;
  representative_email: string | null;
  message_description: string | null;
  sample_messages: string[];
}
export interface SMSOnboarding {
  version: number;
  status: string;
  submission_enabled: false;
  fields: SMSDraft;
  blockers: string[];
  rejection_reason: string | null;
  connection: {
    status: string;
    sender_last4: string | null;
    registration_status: string | null;
    verified_at: string | null;
  };
}
export interface SMSConsent {
  id: string;
  customer_id: string;
  phone_last4: string;
  purpose: string;
  status: "granted" | "withdrawn";
  source: string;
  disclosure_version: string;
  collected_at: string;
  created_at: string;
}
const base = "/communications/sms";
export const smsOnboardingApi = {
  get: async () => (await api.get<SMSOnboarding>(`${base}/onboarding`)).data,
  save: async (draft: SMSDraft, version: number) =>
    (
      await api.put<SMSOnboarding>(`${base}/onboarding`, {
        ...Object.fromEntries(
          Object.entries(draft).map(([key, value]) => [
            key,
            typeof value === "string" && !value.trim()
              ? null
              : key === "sample_messages" && Array.isArray(value)
                ? value.filter((sample) => sample.trim())
                : value,
          ]),
        ),
        expected_version: version,
      })
    ).data,
  review: async (version: number) =>
    (
      await api.post<SMSOnboarding>(`${base}/onboarding/review`, {
        expected_version: version,
      })
    ).data,
  package: async () =>
    (
      await api.get<SMSOnboarding & { review_only: true }>(
        `${base}/onboarding/review-package`,
      )
    ).data,
  consents: async (customerId: string) =>
    (
      await api.get<{ items: SMSConsent[] }>(`${base}/consents`, {
        params: { customer_id: customerId },
      })
    ).data.items,
  recordConsent: async (body: {
    customer_id: string;
    status: "granted" | "withdrawn";
    source: string;
    disclosure_version: string;
    collected_at: string;
  }) => (await api.post<SMSConsent>(`${base}/consents`, body)).data,
};
