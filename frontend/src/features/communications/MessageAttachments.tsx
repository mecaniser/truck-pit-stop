import { ControlButton } from '@/components/ui/Controls'
import { useEffect, useRef, useState } from "react";
import { Image as ImageIcon, X } from "lucide-react";
import { getAuthenticatedSessionIdentity, useAuthStore } from "../../stores/authStore";
import { inboxApi } from "./api";
import type { Message } from "./model";

const notice = "[Attachment received in CallRail. Open CallRail to view.]";
// One bound across the selected thread, including multiple receipt bubbles.
let activeBlobs = 0;
const waiting: (() => void)[] = [];
async function limitedBlob<T>(signal: AbortSignal, request: () => Promise<T>): Promise<T> {
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  await new Promise<void>((resolve, reject) => {
    const start = () => {
      signal.removeEventListener("abort", cancel);
      activeBlobs += 1;
      resolve();
    };
    const cancel = () => {
      const index = waiting.indexOf(start);
      if (index !== -1) waiting.splice(index, 1);
      reject(new DOMException("Aborted", "AbortError"));
    };
    if (activeBlobs < 2) start();
    else {
      waiting.push(start);
      signal.addEventListener("abort", cancel, { once: true });
    }
  });
  try {
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    return await request();
  } finally {
    activeBlobs -= 1;
    waiting.shift()?.();
  }
}

type ImageItem = { index: number; url: string };
type Props = { tenantId: string; message: Message };

/** Key sensitive resources by session as well as thread; no old state is rendered
 * during a shop switch, even before the previous effect cleanup runs. */
export default function MessageAttachments({ tenantId, message }: Props) {
  const session = useAuthStore(getAuthenticatedSessionIdentity);
  const authTenant = useAuthStore((state) => state.user?.tenant_id);
  if (!session || (authTenant && authTenant !== tenantId)) return <>{message.body}</>;
  return <AttachmentSession key={JSON.stringify([session, tenantId, message.conversationId, message.id])}
    tenantId={tenantId} message={message} session={session} />;
}

function AttachmentSession({ tenantId, message, session }: Props & { session: string }) {
  const [attempt, setAttempt] = useState(0);
  const [images, setImages] = useState<ImageItem[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [expanded, setExpanded] = useState<ImageItem | null>(null);
  const urls = useRef(new Set<string>());
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const close = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    const valid = () => current && !controller.signal.aborted &&
      getAuthenticatedSessionIdentity(useAuthStore.getState()) === session;
    const ownedUrls = urls.current;
    setImages([]);
    setExpanded(null);
    setStatus("loading");
    void (async () => {
      try {
        const manifest = await inboxApi.attachmentManifest(message.conversationId, message.id, controller.signal);
        if (!valid()) return;
        // Fail closed on a malformed manifest; never use any provider-supplied URL.
        if (!Array.isArray(manifest.items) || manifest.items.length > 10 ||
          manifest.items.some((item) => item.kind !== "image" || !Number.isInteger(item.index) || item.index < 0 || item.index > 9) ||
          new Set(manifest.items.map((item) => item.index)).size !== manifest.items.length) throw new Error("Invalid attachments");
        if (!manifest.items.length) { setStatus("empty"); return; }
        let failed = false;
        await Promise.all(manifest.items.map(async ({ index }) => {
          try {
            const blob = await limitedBlob(controller.signal, () => {
              if (!valid()) throw new DOMException("Aborted", "AbortError");
              return inboxApi.attachmentBlob(message.conversationId, message.id, index, controller.signal);
            });
            if (!valid()) return;
            if (!(blob instanceof Blob) || !["image/jpeg", "image/png"].includes(blob.type) || !blob.size || blob.size > 10 * 1024 * 1024) throw new Error("Invalid image");
            const url = URL.createObjectURL(blob);
            ownedUrls.add(url);
            if (!valid()) { URL.revokeObjectURL(url); ownedUrls.delete(url); return; }
            setImages((items) => [...items, { index, url }].sort((a, b) => a.index - b.index));
          } catch {
            failed = true;
          }
        }));
        if (valid()) setStatus((previous) => failed || previous === "error" ? "error" : "ready");
      } catch {
        if (valid()) setStatus("error");
      }
    })();
    return () => {
      current = false;
      controller.abort();
      for (const url of ownedUrls) URL.revokeObjectURL(url);
      ownedUrls.clear();
    };
  }, [session, tenantId, message.conversationId, message.id, attempt]);

  useEffect(() => {
    if (expanded) {
      dialog.current?.showModal();
      close.current?.focus();
    }
  }, [expanded]);

  const closeViewer = () => {
    dialog.current?.close();
    setExpanded(null);
    trigger.current?.focus();
  };
  const body = (status === "loading" || images.length > 0) && message.body.endsWith(notice)
    ? message.body.slice(0, -notice.length).trimEnd() : message.body;
  return <>
    {body && <span className="attachment-caption">{body}</span>}
    <div className="message-attachments" aria-label="Message images">
      {images.map((item) => <ControlButton controlKind="content" key={item.index} className="attachment-thumbnail" type="button"
        aria-label={`Open received image ${item.index + 1}`}
        onClick={(event) => { trigger.current = event.currentTarget; setExpanded(item); }}>
        <img src={item.url} alt={`Received MMS image ${item.index + 1}`} referrerPolicy="no-referrer"
          onError={() => {
            URL.revokeObjectURL(item.url); urls.current.delete(item.url);
            setImages((items) => items.filter((image) => image.url !== item.url)); setStatus("error");
          }} />
      </ControlButton>)}
      {status === "loading" && <span role="status" className="attachment-placeholder motion-reduce:animate-pulse">
        <ImageIcon size={28} strokeWidth={1.5} aria-hidden="true" />
        <span>Loading images…</span>
      </span>}
      {(status === "empty" || status === "error") && <div className="attachment-state" role="status">
        <span>{status === "empty" ? "Image no longer available." : "Image unavailable."}</span>
        <ControlButton type="button" onClick={() => setAttempt((value) => value + 1)}>Retry</ControlButton>
      </div>}
    </div>
    {expanded && <dialog ref={dialog} className="attachment-viewer" aria-label="Received image"
      onCancel={(event) => { event.preventDefault(); closeViewer(); }}
      onClick={(event) => { if (event.target === event.currentTarget) closeViewer(); }}>
      <div className="attachment-viewer-content">
        <ControlButton controlKind="icon" ref={close} type="button" aria-label="Close image" className="attachment-close" onClick={closeViewer}><X size={20} /></ControlButton>
        <img src={expanded.url} alt={`Received MMS image ${expanded.index + 1}, expanded`} referrerPolicy="no-referrer" />
      </div>
    </dialog>}
  </>;
}
