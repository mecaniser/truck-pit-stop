import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Check, Download } from "lucide-react";
import { errorMessage } from "./api";
import {
  smsOnboardingApi,
  type SMSDraft,
  type SMSOnboarding,
} from "./smsOnboardingApi";
const fields: {
  key: Exclude<keyof SMSDraft, "sample_messages" | "message_description">;
  label: string;
  type?: string;
}[] = [
  { key: "legal_name", label: "Legal business name" },
  { key: "trade_name", label: "Shop / trade name" },
  { key: "website_url", label: "Business website", type: "url" },
  { key: "support_email", label: "Support email", type: "email" },
  { key: "support_phone", label: "Support phone" },
  { key: "representative_name", label: "Authorized representative" },
  { key: "representative_email", label: "Representative email", type: "email" },
  { key: "consent_source_url", label: "SMS consent evidence URL", type: "url" },
  { key: "privacy_url", label: "Privacy policy URL", type: "url" },
  { key: "terms_url", label: "Terms URL", type: "url" },
];
const readable = (value: string) => value.replace(/_/g, " ");
export default function SMSSetup({ onClose }: { onClose: () => void }) {
  const [record, setRecord] = useState<SMSOnboarding | null>(null);
  const [draft, setDraft] = useState<SMSDraft | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const alive = useRef(true);
  const lock = useRef(false);
  useEffect(() => {
    alive.current = true;
    void smsOnboardingApi
      .get()
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
  }, []);
  const dirty =
    record && draft && JSON.stringify(record.fields) !== JSON.stringify(draft);
  async function action(kind: "save" | "review" | "export" | "rebase") {
    if (!record || !draft || lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (kind === "export") {
        const value = await smsOnboardingApi.package();
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
        const current = await smsOnboardingApi.get();
        if (!alive.current) return;
        setRecord(current);
        setStale(false);
        setNotice(
          "Latest version loaded. Your edits are preserved; compare them before saving.",
        );
      } else {
        const value =
          kind === "save"
            ? await smsOnboardingApi.save(draft, record.version)
            : await smsOnboardingApi.review(record.version);
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
      <button className="subtle-button" onClick={onClose}>
        <ArrowLeft size={16} /> Back to inbox
      </button>
      <header className="sms-setup-header">
        <div>
          <p className="sms-eyebrow">Communication · Shop registration</p>
          <h1>SMS setup</h1>
          <p>Register this shop’s legal business and messaging program.</p>
        </div>
        <span className="sms-state">
          {record ? readable(record.status) : "Loading"}
        </span>
      </header>
      <div className="sms-hold">
        <Check size={17} />
        <span>Review only · Twilio submissions and deployment on hold</span>
      </div>
      {error && (
        <p role="alert" className="sms-error">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {stale && (
        <button
          className="subtle-button"
          disabled={busy}
          onClick={() => void action("rebase")}
        >
          Load latest version and keep my edits
        </button>
      )}
      {record && draft && (
        <>
          <section className="sms-connection">
            <h2>Connection</h2>
            <strong>{readable(record.connection.status)}</strong>
            {record.connection.sender_last4 && (
              <span> · Sender ending {record.connection.sender_last4}</span>
            )}
            {record.connection.registration_status && (
              <p>
                Registration: {readable(record.connection.registration_status)}
              </p>
            )}
            {record.rejection_reason && (
              <p className="sms-error">{record.rejection_reason}</p>
            )}
            {record.blockers.length > 0 && (
              <ul>
                {record.blockers.map((blocker) => (
                  <li key={blocker}>{readable(blocker)}</li>
                ))}
              </ul>
            )}
          </section>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void action("save");
            }}
          >
            <section className="sms-form-section">
              <h2>Business and consent evidence</h2>
              <div className="sms-field-grid">
                {fields.map((field) => (
                  <label key={field.key}>
                    {field.label}
                    <input
                      type={field.type ?? "text"}
                      value={draft[field.key] ?? ""}
                      disabled={busy}
                      onChange={(e) =>
                        setDraft({ ...draft, [field.key]: e.target.value })
                      }
                    />
                  </label>
                ))}
              </div>
            </section>
            <section className="sms-form-section">
              <h2>Service messages</h2>
              <label>
                Messaging purpose
                <textarea
                  value={draft.message_description ?? ""}
                  disabled={busy}
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
                  disabled={busy}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      sample_messages: e.target.value.split("\n"),
                    })
                  }
                />
              </label>
            </section>
            <div className="sms-actions">
              <button className="primary-button" disabled={busy || stale}>
                Save draft
              </button>
              <button
                className="subtle-button"
                type="button"
                disabled={busy || stale || !!dirty}
                onClick={() => void action("review")}
              >
                Prepare for review
              </button>
              <button
                className="subtle-button"
                type="button"
                disabled={busy || !!dirty}
                onClick={() => void action("export")}
              >
                <Download size={16} /> Review package
              </button>
              {dirty && <span>Unsaved changes</span>}
            </div>
          </form>
        </>
      )}
    </main>
  );
}
