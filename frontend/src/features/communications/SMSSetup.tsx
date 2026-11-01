import { ControlButton, ControlInput } from '@/components/ui/Controls'
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ChevronDown, Download, PauseCircle } from "lucide-react";
import { errorMessage } from "./api";
import {
  platformSMSRegistrationApi,
  type SMSDraft,
  type SMSOnboarding,
} from "./smsOnboardingApi";
const fields: {
  key: Exclude<keyof SMSDraft, "sample_messages" | "message_description">;
  label: string;
  type?: string;
  help?: string;
}[] = [
  { key: "legal_name", label: "Legal business name", help: "Use the name on your business registration." },
  { key: "trade_name", label: "Shop / trade name" },
  { key: "website_url", label: "Business website", type: "url" },
  { key: "support_email", label: "Support email", type: "email" },
  { key: "support_phone", label: "Support phone", help: "Optional. A number customers can call for help." },
  { key: "representative_name", label: "Authorized representative", help: "The owner or person authorized to register the shop." },
  { key: "representative_email", label: "Representative email", type: "email" },
  { key: "consent_source_url", label: "Customer opt-in page", type: "url", help: "Link to the form or page where customers agree to receive repair texts." },
  { key: "privacy_url", label: "Privacy policy URL", type: "url" },
  { key: "terms_url", label: "Terms URL", type: "url" },
];
const readable = (value: string) => value.replace(/_/g, " ");
export default function SMSSetup(props: { tenantId: string; shopName: string; onClose: () => void; onDirtyChange?: (dirty: boolean) => void }) {
  return <ShopRegistration key={props.tenantId} {...props} />;
}
function ShopRegistration({ tenantId, shopName, onClose, onDirtyChange }: { tenantId: string; shopName: string; onClose: () => void; onDirtyChange?: (dirty: boolean) => void }) {
  const [record, setRecord] = useState<SMSOnboarding | null>(null);
  const [draft, setDraft] = useState<SMSDraft | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [showConnection, setShowConnection] = useState(false);
  const [stale, setStale] = useState(false);
  const alive = useRef(true);
  const lock = useRef(false);
  useEffect(() => {
    alive.current = true;
    void platformSMSRegistrationApi
      .get(tenantId)
      .then((value) => {
        if (alive.current) {
          setRecord(value);
          setDraft(value.fields);
        }
      })
      .catch((e) => {
        if (alive.current) setError(errorMessage(e));
      });
    return () => {
      alive.current = false;
    };
  }, [tenantId]);
  const dirty =
    record && draft && JSON.stringify(record.fields) !== JSON.stringify(draft);
  useEffect(() => { onDirtyChange?.(!!dirty); return () => onDirtyChange?.(false); }, [dirty, onDirtyChange]);
  const missing = draft ? [
    ...fields.filter(field => field.key !== "support_phone" && !draft[field.key]?.trim()).map(field => field.key),
    ...(!draft.message_description?.trim() ? ["message_description"] : []),
    ...(!draft.sample_messages.some(value => value.trim()) ? ["sample_messages"] : []),
  ] : [];
  const stage = record ? ({ draft: "Draft", ready_for_review: "Ready for review", submitted: "Submitted", in_review: "Under review", approved: "Approved", rejected: "Needs changes", suspended: "Suspended" }[record.status] ?? "Review needed") : "Loading";
  const editable = !record || ["draft", "rejected", "ready_for_review"].includes(record.status);
  function fieldInput(field: typeof fields[number]) {
    const required = field.key !== "support_phone";
    const id = `sms-registration-${field.key}`;
    return <div className="sms-field" key={field.key}>
      <label htmlFor={id}>{field.label}</label>
      <ControlInput id={id} type={field.type ?? "text"} value={draft?.[field.key] ?? ""}
        aria-required={required} aria-describedby={field.help ? `${id}-help` : undefined}
        disabled={busy || !editable} onChange={event => draft && setDraft({ ...draft, [field.key]: event.target.value })} />
      {field.help && <p className="sms-field-help" id={`${id}-help`}>{field.help}</p>}
      {required && !draft?.[field.key]?.trim() && <span className="sms-field-needed">Required for review</span>}
    </div>;
  }
  async function action(kind: "save" | "review" | "export" | "rebase") {
    if (!record || !draft || lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (kind === "export") {
        const value = await platformSMSRegistrationApi.package(tenantId);
        if (!alive.current) return;
        const url = URL.createObjectURL(
          new Blob([JSON.stringify(value, null, 2)], {
            type: "application/json",
          }),
        );
        const link = document.createElement("a");
        link.href = url;
        link.download = "sms-registration-review.json";
        link.click();
        URL.revokeObjectURL(url);
      } else if (kind === "rebase") {
        const current = await platformSMSRegistrationApi.get(tenantId);
        if (!alive.current) return;
        setRecord(current);
        setStale(false);
        setNotice(
          "Latest version loaded. Your edits are preserved; compare them before saving.",
        );
      } else {
        const value =
          kind === "save"
            ? await platformSMSRegistrationApi.save(tenantId, draft, record.version)
            : await platformSMSRegistrationApi.review(tenantId, record.version);
        if (!alive.current) return;
        setRecord(value);
        setDraft(value.fields);
        setNotice(
          kind === "save"
            ? "Draft saved."
            : "Prepared for review. Registration remains on hold.",
        );
      }
    } catch (e) {
      if (!alive.current) return;
      if ((e as { response?: { status?: number } }).response?.status === 409) {
        setStale(true);
        setError(
          "This draft changed in another session. Your edits are preserved.",
        );
      } else setError(errorMessage(e));
    } finally {
      lock.current = false;
      if (alive.current) setBusy(false);
    }
  }
  return (
    <main className="sms-setup">
      {<ControlButton className="subtle-button" onClick={onClose}>
        <ArrowLeft size={16} /> Back to shops
      </ControlButton>}
      <header className="sms-setup-header">
        <div>
          <h1>Repair texting registration</h1>
          <p>Prepare {shopName}’s details for Twilio to review repair-update texting.</p>
        </div>
        <span className="sms-state">
          {stage}
        </span>
      </header>
      <div className="sms-hold">
        <PauseCircle size={18} aria-hidden="true" />
        <span>Preparation only. This form does not submit to Twilio or turn on automatic messages.</span>
      </div>
      {error && (
        <p role="alert" className="sms-error">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {stale && (
        <ControlButton
          className="subtle-button"
          disabled={busy}
          onClick={() => void action("rebase")}
        >
          Load latest version and keep my edits
        </ControlButton>
      )}
      {record && draft && (
        <>
          <section className="sms-next-step" aria-label="Registration next step">
            <h2>{!editable ? "Check your registration status" : record.status === "ready_for_review" && !dirty ? "Your draft is ready for review" : "Next: complete the registration draft"}</h2>
            <p>{!editable ? "This draft is locked for editing. Check the provider status below and contact your shop administrator if changes are needed." : record.status === "ready_for_review" && !dirty ? "Download the review package for your shop administrator. Provider submission and approval are separate steps." : "Add your business details, how customers opt in, and examples of the repair texts you plan to send. Save the draft, then prepare it for review."}</p>
            <p className="sms-existing-note">Existing inbox conversations keep their current sending number and settings.</p>
            {editable && <span className="sms-progress">{missing.length ? `${missing.length} required ${missing.length === 1 ? "item" : "items"} left` : "Required information filled in"}</span>}
          </section>
          <section className="sms-connection">
            <ControlButton controlKind="action" type="button" className="sms-connection-toggle" aria-expanded={showConnection} aria-controls="sms-connection-details" onClick={() => setShowConnection(!showConnection)}>
              Registration status and number <ChevronDown size={16} className={showConnection ? "is-expanded" : ""} />
            </ControlButton>
            <div id="sms-connection-details" hidden={!showConnection}>
              <p>{({ legacy_configured: "An existing SMS number is configured. This does not confirm approval for repair texting.", not_configured: "No Twilio number is configured for this registration.", managed_routing_disabled: "A number is assigned. The new repair-texting route is not enabled.", pending_verification: "The assigned number still needs verification.", configured: "The assigned number has passed the connection checks." }[record.connection.status] ?? "The connection needs an administrator’s review.")}</p>
              {record.connection.sender_last4 && <p>Number ending {record.connection.sender_last4}</p>}
              {record.connection.registration_status && <p>Provider status: {readable(record.connection.registration_status)}</p>}
              {record.blockers.includes("provider_registration_required") && <p>Provider registration is still required.</p>}
              {record.blockers.some(code => !code.endsWith("_required") && code !== "managed_routing_disabled") && <p>The provider connection has an unresolved check. Ask your shop administrator to review it before activation.</p>}
              {record.rejection_reason && <p className="sms-error">{record.rejection_reason}</p>}
            </div>
          </section>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void action("save");
            }}
          >
            <section className="sms-form-section">
              <h2>Business details</h2>
              <p className="sms-section-help">Who is sending the texts, and who can answer questions about the registration? All fields are required except support phone.</p>
              <div className="sms-field-grid">{fields.filter(field => !["consent_source_url", "privacy_url", "terms_url"].includes(field.key)).map(fieldInput)}</div>
            </section>
            <section className="sms-form-section">
              <h2>Customer permission</h2>
              <p className="sms-section-help">Show how customers agree to receive repair texts and where they can read your policies. This does not record consent for individual contacts.</p>
              <div className="sms-field-grid">{fields.filter(field => ["consent_source_url", "privacy_url", "terms_url"].includes(field.key)).map(fieldInput)}</div>
            </section>
            <section className="sms-form-section">
              <h2>Texts you plan to send</h2>
              <p className="sms-section-help">Describe the repair updates customers will receive and provide sample wording for review.</p>
              <label>
                Messaging purpose
                <textarea
                  value={draft.message_description ?? ""}
                  disabled={busy || !editable}
                  onChange={(e) =>
                    setDraft({ ...draft, message_description: e.target.value })
                  }
                />
              </label>
              <label>
                Sample messages · one per line
                <textarea
                  rows={4}
                  value={(draft.sample_messages ?? []).join("\n")}
                  disabled={busy || !editable}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      sample_messages: e.target.value.split("\n"),
                    })
                  }
                />
              </label>
            </section>
            <p className="sms-section-help">Save draft keeps your progress here. Prepare for review checks the required information; it does not submit a registration.</p>
            <div className="sms-actions">
              <ControlButton className="primary-button" disabled={busy || stale || !editable}>
                Save draft
              </ControlButton>
              <ControlButton
                className="subtle-button"
                type="button"
                disabled={busy || stale || !!dirty || !editable}
                onClick={() => void action("review")}
              >
                Prepare for review
              </ControlButton>
              <ControlButton
                className="subtle-button"
                type="button"
                disabled={busy || !!dirty}
                onClick={() => void action("export")}
              >
                <Download size={16} /> Download review package
              </ControlButton>
              {dirty && <span>Unsaved changes</span>}
            </div>
          </form>
        </>
      )}
    </main>
  );
}
