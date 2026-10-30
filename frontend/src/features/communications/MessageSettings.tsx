import { useEffect, useRef, useState, type RefObject } from "react";
import { MessageSquare, X } from "lucide-react";
import SMSSetup from "./SMSSetup";

type Props = {
  canSetupSMS: boolean;
  channels?: { channel: string; connected: boolean }[];
  deliveryMode?: string;
  onClose: () => void;
  opener?: RefObject<HTMLButtonElement | null>;
};

export default function MessageSettings({ canSetupSMS, channels, deliveryMode, onClose, opener }: Props) {
  const [section, setSection] = useState<"channels" | "sms">("channels");
  const [visitedSMS, setVisitedSMS] = useState(false);
  const dialog = useRef<HTMLElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = opener?.current ?? document.activeElement;
    dialog.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => { if (previous instanceof HTMLElement) previous.focus(); };
  }, [opener]);
  return (
    <div className="sheet-backdrop settings-backdrop">
      <section ref={dialog} className="connections-sheet message-settings" role="dialog" aria-modal="true" aria-label="Messages settings"
        onKeyDown={event => {
          if (event.key === "Escape") { event.stopPropagation(); close.current(); }
          if (event.key !== "Tab") return;
          const controls = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href]') ?? []).filter(el => !el.closest('[hidden]'));
          const first = controls[0]; const last = controls[controls.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
          if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }}>
        <header><div><h2>Messages settings</h2><p>Manage inbox connections and prepare repair texting.</p></div>
          <button className="icon-button" aria-label="Close settings" onClick={onClose}><X size={20} /></button>
        </header>
        <nav className="settings-sections" aria-label="Settings sections">
          <button className="subtle-button" aria-pressed={section === "channels"} onClick={() => setSection("channels")}>Channels</button>
          {canSetupSMS && <button className="subtle-button" aria-pressed={section === "sms"} onClick={() => { setVisitedSMS(true); setSection("sms"); }}>Repair texting</button>}
        </nav>
        <div hidden={section !== "channels"}>
          {(["sms", "whatsapp", "telegram"] as const).map(channel => (
            <div className="connection-row" key={channel}>
              <span className={`channel-chip ${channel}`}><MessageSquare size={18} /></span>
              <div><h3>{{ sms: "SMS", whatsapp: "WhatsApp", telegram: "Telegram" }[channel]}</h3>
                <p>{channel === "sms" ? (deliveryMode ? deliveryMode === "simulated" ? "Local test connection · no live messages" : "Uses each conversation’s existing reply number" : "Sample connection") : channel === "whatsapp" ? "Business sender and approved templates required" : "Shop bot and customer-started conversation required"}</p>
              </div>
              <span className={`connection-state ${channels?.some(c => c.channel === channel && c.connected) ? "ready" : ""}`}>
                {channel === "sms" ? (channels ? channels.some(c => c.channel === channel && c.connected) ? "Connected" : "Unavailable" : "Preview") : "Planned"}
              </span>
            </div>
          ))}
          <p className="connection-summary">New channels require setup and approval before messages can be sent.</p>
        </div>
        {canSetupSMS && visitedSMS && <div hidden={section !== "sms"}><SMSSetup embedded onClose={onClose} /></div>}
      </section>
    </div>
  );
}
