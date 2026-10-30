import { useEffect, useRef, type RefObject } from "react";
import { MessageSquare, X } from "lucide-react";

type Props = {
  channels?: { channel: string; connected: boolean }[];
  deliveryMode?: string;
  onClose: () => void;
  opener?: RefObject<HTMLButtonElement | null>;
};

export default function MessageSettings({ channels, deliveryMode, onClose, opener }: Props) {
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
        <header><div><h2>Messages settings</h2><p>View your shop’s messaging channels.</p></div>
          <button className="icon-button" aria-label="Close settings" onClick={onClose}><X size={20} /></button>
        </header>
        <div>
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
          <p className="connection-summary">Your platform administrator manages channel setup and sending numbers.</p>
        </div>
      </section>
    </div>
  );
}
