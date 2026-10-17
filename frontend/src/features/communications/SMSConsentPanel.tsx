import { useEffect, useRef, useState } from "react";
import { errorMessage } from "./api";
import { smsOnboardingApi, type SMSConsent } from "./smsOnboardingApi";
export default function SMSConsentPanel({
  customerId,
}: {
  customerId: string;
}) {
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
      <h4>Service SMS consent</h4>
      <p>
        {loaded
          ? records[0]
            ? `${records[0].status === "granted" ? "Granted" : "Withdrawn"} · phone ending ${records[0].phone_last4}`
            : "No recorded consent"
          : "Loading consent…"}
      </p>
      {error && (
        <p role="alert" className="sms-error">
          {error}
        </p>
      )}
      <button className="subtle-button" onClick={() => setEditing(!editing)}>
        {editing ? "Close evidence form" : "Record consent evidence"}
      </button>
      {editing && (
        <div className="sms-consent-form">
          <label>
            Evidence source
            <input
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder="Signed service intake"
            />
          </label>
          <label>
            Disclosure version
            <input
              value={version}
              onChange={(e) => setVersion(e.target.value)}
            />
          </label>
          <label>
            Collected at
            <input
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
            <button
              className="subtle-button"
              disabled={!ready}
              onClick={() => void record("granted")}
            >
              Record grant
            </button>
            <button
              className="subtle-button"
              disabled={!ready}
              onClick={() => void record("withdrawn")}
            >
              Record withdrawal
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
