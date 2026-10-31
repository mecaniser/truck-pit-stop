import { beforeEach, describe, expect, it, vi } from 'vitest'
import api from '../../lib/api'
import { platformSMSRegistrationApi, smsOnboardingApi, type SMSDraft } from './smsOnboardingApi'
vi.mock('../../lib/api', () => ({default:{get:vi.fn(),put:vi.fn(),post:vi.fn()}}))
beforeEach(()=> {vi.resetAllMocks(); vi.mocked(api.get).mockResolvedValue({data:{items:[]}});vi.mocked(api.post).mockResolvedValue({data:{}})})
describe('Registration scope',()=>{
 it('requires selected shop in admin paths and leaves consent tenant scoped',async()=>{
  await platformSMSRegistrationApi.get('shop-a')
  expect(api.get).toHaveBeenLastCalledWith('/admin/tenants/shop-a/sms/onboarding')
  await platformSMSRegistrationApi.review('shop-b',2)
  expect(api.post).toHaveBeenLastCalledWith('/admin/tenants/shop-b/sms/onboarding/review',{expected_version:2})
  await platformSMSRegistrationApi.package('shop-b')
  expect(api.get).toHaveBeenLastCalledWith('/admin/tenants/shop-b/sms/onboarding/review-package')
  await smsOnboardingApi.consents('customer')
  expect(api.get).toHaveBeenLastCalledWith('/communications/sms/consents',{params:{customer_id:'customer'}})
 })
})

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
  await platformSMSRegistrationApi.save("shop-a", draft, 0);
  expect(api.put).toHaveBeenCalledWith("/admin/tenants/shop-a/sms/onboarding", {
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
  await platformSMSRegistrationApi.review("shop-a", 3);
  expect(api.post).toHaveBeenCalledWith(
    "/admin/tenants/shop-a/sms/onboarding/review",
    { expected_version: 3 },
  );
});
