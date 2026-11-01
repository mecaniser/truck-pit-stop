import { ControlButton, ControlInput } from '@/components/ui/Controls'
import { ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { errorMessage } from "./api";
import { smsOnboardingApi, type SMSConsent } from "./smsOnboardingApi";
export default function SMSConsentPanel({
  customerId,
}: {
  customerId: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const panelId = useId();
  const [records, setRecords] = useState<SMSConsent[]>([]);
  const [source, setSource] = useState("");
  const [version, setVersion] = useState("");
  const [collected, setCollected] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const alive = useRef(true);
  const lock = useRef(false);
  useEffect(() => {
    alive.current = true;
    void smsOnboardingApi
      .consents(customerId)
      .then((items) => {
        if (alive.current) {
          setRecords(items);
          setLoaded(true);
        }
      })
      .catch((e) => {
        if (alive.current) setError(errorMessage(e));
      });
    return () => {
      alive.current = false;
    };
  }, [customerId]);
  async function record(status: "granted" | "withdrawn") {
    if (lock.current || !confirmed) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      await smsOnboardingApi.recordConsent({
        customer_id: customerId,
        status,
        source,
        disclosure_version: version,
        collected_at: new Date(collected).toISOString(),
      });
      const items = await smsOnboardingApi.consents(customerId);
      if (!alive.current) return;
      setRecords(items);
      setEditing(false);
      setConfirmed(false);
      setSource("");
      setVersion("");
      setCollected("");
    } catch (e) {
      if (alive.current) setError(errorMessage(e));
    } finally {
      lock.current = false;
      if (alive.current) setBusy(false);
    }
  }
  const ready =
    loaded &&
    !!source.trim() &&
    !!version.trim() &&
    !!collected &&
    confirmed &&
    !busy;
  return (
    <section className="sms-consent">
      <ControlButton controlKind="action" type="button" className="sms-permissions-toggle" aria-expanded={expanded} aria-controls={panelId} onClick={() => setExpanded(value => !value)}>
        <span>SMS permissions</span><ChevronDown size={14} aria-hidden="true" className={expanded ? "is-expanded" : ""} />
      </ControlButton>
      {records[0]?.status === "withdrawn" && <p className="context-warning">SMS consent withdrawn</p>}
      {error && <p role="alert" className="sms-error">{error}</p>}
      <div id={panelId} hidden={!expanded}>
      <p>
        {loaded
          ? records[0]
            ? `${records[0].status === "granted" ? "Granted" : "Withdrawn"} · phone ending ${records[0].phone_last4}`
            : "No recorded consent"
          : "Loading consent…"}
      </p>
      <ControlButton className="subtle-button" onClick={() => setEditing(!editing)}>
        {editing ? "Close evidence form" : "Record consent evidence"}
      </ControlButton>
      {editing && (
        <div className="sms-consent-form">
          <label>
            Evidence source
            <ControlInput
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder="Signed service intake"
            />
          </label>
          <label>
            Disclosure version
            <ControlInput
              value={version}
              onChange={(e) => setVersion(e.target.value)}
            />
          </label>
          <label>
            Collected at
            <ControlInput
              type="datetime-local"
              value={collected}
              onChange={(e) => setCollected(e.target.value)}
            />
          </label>
          <label className="sms-checkbox">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            I verified this customer’s explicit consent or withdrawal evidence.
          </label>
          <div className="sms-consent-actions">
            <ControlButton
              className="subtle-button"
              disabled={!ready}
              onClick={() => void record("granted")}
            >
              Record grant
            </ControlButton>
            <ControlButton
              className="subtle-button"
              disabled={!ready}
              onClick={() => void record("withdrawn")}
            >
              Record withdrawal
            </ControlButton>
          </div>
        </div>
      )}
      </div>
    </section>
  );
}
