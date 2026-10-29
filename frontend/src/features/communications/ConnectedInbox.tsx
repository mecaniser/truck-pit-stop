import { restoredConversation } from "./inboxSelection";
import { useCallback, useEffect, useRef, useState } from "react";
import api from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import CommunicationsPreview from "./CommunicationsPreview";
import SMSSetup from "./SMSSetup";
import InboxLoading from "./InboxLoading";
import {
  createIntent,
  errorMessage,
  inboxApi,
  mapMessage,
  type Bootstrap,
  type SendIntent,
} from "./api";
import type { Conversation } from "./model";
import "./communications.css";

interface InboxProps {
  embedded?: boolean;
  onUnreadCountChange?: (count: number) => void;
}

export default function ConnectedInbox({
  embedded = false,
  onUnreadCountChange,
}: InboxProps) {
  return (
    <div
      className={`communications-surface${embedded ? " communications-embedded" : ""}`}
    >
      <InboxContent
        embedded={embedded}
        onUnreadCountChange={onUnreadCountChange}
      />
    </div>
  );
}

function InboxContent({ embedded, onUnreadCountChange }: InboxProps) {
  const sessionEpoch = useAuthStore((state) => state.authSessionEpoch);
  const user = useAuthStore((state) => state.user);
  const canSetup =
    !!user && ["garage_owner", "garage_admin"].includes(user.role);
  const [showSetup, setShowSetup] = useState(false);
  const [searchIds, setSearchIds] = useState<string[] | null>(null);
  const searchGeneration = useRef(0);
  const onSearch = useCallback((search: string) => {
    const request = ++searchGeneration.current;
    if (!search.trim()) {
      setSearchIds(null);
      return;
    }
    void inboxApi
      .list(search.slice(0, 200))
      .then((results) => {
        if (request === searchGeneration.current)
          setSearchIds(results.map((r) => r.id));
      })
      .catch((e) => setError(errorMessage(e)));
  }, []);
  const [blocked, setBlocked] = useState(false);
  const [confirmedDraft, setConfirmedDraft] = useState<{
    key: string;
    text: string;
  } | null>(null);
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [rows, setRows] = useState<Conversation[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [loginRequired, setLoginRequired] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<SendIntent | null>(null);
  const lock = useRef(false);
  const selectedId = useRef<string | null>(null);
  const generation = useRef(0);
  const storageKey = bootstrap
    ? `inbox-send:${bootstrap.tenant_id}:${bootstrap.user_id}`
    : "";
  const merge = useCallback(
    (row: Conversation) =>
      setRows((previous) => previous.map((r) =>
        r.id === row.id && (row.version ?? 0) >= (r.version ?? 0) ? row : r,
      )),
    [],
  );
  const select = useCallback(
    async (id: string) => {
      selectedId.current = id;
      const request = ++generation.current;
      try {
        const detail = await inboxApi.detail(id);
        if (request !== generation.current) return;
        const unreadCount = await inboxApi.read(detail);
        if (request === generation.current) merge({ ...detail, unreadCount });
      } catch (e) {
        if (request === generation.current) setError(errorMessage(e));
      }
    },
    [merge],
  );
  const initialize = useCallback(async () => {
    const epoch = useAuthStore.getState().authSessionEpoch;
    setLoading(true);
    setError("");
    setBlocked(false);
    setPending(null);
    try {
      const meta = await inboxApi.bootstrap();
      const list = await inboxApi.list();
      if (epoch !== useAuthStore.getState().authSessionEpoch) return;
      setBootstrap(meta);
      setRows(list);
      setLoginRequired(false);
      const stored = localStorage.getItem(
        `inbox-send:${meta.tenant_id}:${meta.user_id}`,
      );
      if (stored) {
        try {
          const restored = JSON.parse(stored) as SendIntent;
          if (
            !restored ||
            typeof restored.key !== "string" ||
            typeof restored.conversationId !== "string" ||
            typeof restored.draftKey !== "string" ||
            typeof restored.draft !== "string" ||
            typeof restored.payload?.body !== "string" ||
            typeof restored.payload.channel_account_id !== "string" ||
            typeof restored.payload.contact_identity_id !== "string" ||
            typeof restored.payload.expected_version !== "number"
          )
            throw new Error("Invalid recovery record");
          setPending(restored);
        } catch {
          setBlocked(true);
          setError(
            "The saved send request could not be read. Contact support before sending again.",
          );
        }
      }
      const restored = restoredConversation(list, meta.tenant_id, meta.user_id);
      if (restored) await select(restored.id);
    } catch (e) {
      if (epoch !== useAuthStore.getState().authSessionEpoch) return;
      setLoginRequired(
        (e as { response?: { status?: number } }).response?.status === 401,
      );
      setError(errorMessage(e));
    } finally {
      if (epoch === useAuthStore.getState().authSessionEpoch) setLoading(false);
    }
  }, [select]);
  useEffect(() => {
    setRows([]);
    setBootstrap(null);
    setShowSetup(false);
    generation.current += 1;
    void initialize();
    return () => {
      generation.current += 1;
    };
  }, [initialize, sessionEpoch]);
  useEffect(() => {
    if (!bootstrap) return;
    let stopped = false;
    let inFlight = false;
    const timer = setInterval(async () => {
      if (inFlight || lock.current) return;
      inFlight = true;
      const id = selectedId.current;
      const request = generation.current;
      try {
        const list = await inboxApi.list();
        const detail = id ? await inboxApi.detail(id) : null;
        if (stopped || request !== generation.current) return;
        setRows((previous) =>
          list.map((row) => {
            const old = previous.find((r) => r.id === row.id);
            const incoming = detail?.id === row.id ? detail : row;
            if (old && (incoming.version ?? 0) < (old.version ?? 0)) return old;
            if (detail?.id === row.id)
              return {
                ...detail,
                messages: [
                  ...(old?.messages.filter(
                    (m) => !detail.messages.some((n) => n.id === m.id),
                  ) ?? []),
                  ...detail.messages,
                ],
                messagesHasMore: old?.messagesHasMore ?? detail.messagesHasMore,
                messagesNextCursor:
                  old?.messagesNextCursor ?? detail.messagesNextCursor,
              };
            return { ...row, messages: old?.messages ?? row.messages };
          }),
        );
      } catch (e) {
        if (!stopped) {
          const status = (e as { response?: { status?: number } }).response
            ?.status;
          if (status === 401 || status === 403) {
            setRows([]);
            setBootstrap(null);
            setLoginRequired(status === 401);
          }
          setError(errorMessage(e));
        }
      } finally {
        inFlight = false;
      }
    }, 2500);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [bootstrap]);
  useEffect(() => {
    if (bootstrap)
      onUnreadCountChange?.(
        rows.reduce((count, row) => count + row.unreadCount, 0),
      );
  }, [bootstrap, rows, onUnreadCountChange]);
  async function submit(intent: SendIntent): Promise<boolean> {
    const epoch = useAuthStore.getState().authSessionEpoch;
    if (lock.current) return false;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      // Store before any request; an unacknowledged transport must reuse this exact intent.
      localStorage.setItem(storageKey, JSON.stringify(intent));
      setPending(intent);
      await inboxApi.send(intent);
      if (epoch !== useAuthStore.getState().authSessionEpoch) return false;
      localStorage.removeItem(storageKey);
      setPending(null);
      setConfirmedDraft({ key: intent.draftKey, text: intent.draft });
      const draftStorage = `inbox-drafts:${bootstrap!.tenant_id}:${bootstrap!.user_id}`;
      const drafts = JSON.parse(localStorage.getItem(draftStorage) || "{}");
      if (drafts[intent.draftKey] === intent.draft) {
        delete drafts[intent.draftKey];
        localStorage.setItem(draftStorage, JSON.stringify(drafts));
      }
      try {
        const updated = await inboxApi.detail(intent.conversationId);
        if (epoch === useAuthStore.getState().authSessionEpoch) merge(updated);
      } catch (e) {
        setError(errorMessage(e));
      }
      return true;
    } catch (e) {
      // Only definitive request rejection permits a new intent. 5xx/network remains ambiguous.
      if (epoch !== useAuthStore.getState().authSessionEpoch) return false;
      const status = (e as { response?: { status?: number } }).response?.status;
      const code = (
        e as { response?: { data?: { detail?: { code?: string } } } }
      ).response?.data?.detail?.code;
      if (
        status === 422 ||
        status === 429 ||
        (code &&
          [
            "stale_version",
            "opted_out",
            "identity_unverified",
            "not_connected",
          ].includes(code))
      ) {
        localStorage.removeItem(storageKey);
        setPending(null);
      }
      setError(errorMessage(e));
      try {
        const updated = await inboxApi.detail(intent.conversationId);
        if (epoch === useAuthStore.getState().authSessionEpoch) merge(updated);
      } catch {
        /* keep original error and draft */
      }
      return false;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function patch(
    row: Conversation,
    values: { status?: "open" | "resolved"; assignee_id?: string | null },
  ) {
    const epoch = useAuthStore.getState().authSessionEpoch;
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      await inboxApi.patch(row, values);
      const updated = await inboxApi.detail(row.id);
      if (epoch === useAuthStore.getState().authSessionEpoch) merge(updated);
    } catch (e) {
      if (epoch !== useAuthStore.getState().authSessionEpoch) return;
      setError(errorMessage(e));
      try {
        const updated = await inboxApi.detail(row.id);
        if (epoch === useAuthStore.getState().authSessionEpoch) merge(updated);
      } catch {
        /* keep error */
      }
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function older(id: string) {
    const epoch = useAuthStore.getState().authSessionEpoch;
    const row = rows.find((r) => r.id === id);
    if (!row?.messagesHasMore) return;
    try {
      const page = await inboxApi.older(row);
      if (epoch !== useAuthStore.getState().authSessionEpoch) return;
      setRows((previous) =>
        previous.map((r) =>
          r.id !== id
            ? r
            : {
                ...r,
                messages: [
                  ...page.items
                    .map(mapMessage)
                    .filter((m) => !r.messages.some((n) => n.id === m.id)),
                  ...r.messages,
                ],
                messagesHasMore: page.has_more,
                messagesNextCursor: page.next_cursor,
              },
        ),
      );
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  if (loginRequired) return <InboxLogin onLogin={initialize} />;
  if (showSetup && bootstrap && canSetup)
    return (
      <SMSSetup
        key={`${sessionEpoch}:${bootstrap.tenant_id}:${bootstrap.user_id}`}
        onClose={() => setShowSetup(false)}
      />
    );
  if (loading) return <InboxLoading />;
  if (!bootstrap || !rows.length)
    return (
      <main className="inbox-entry">
        <h1>Messages</h1>
        <p>
          {error || "No conversations yet. Incoming SMS conversations will appear here."}
        </p>
        {!loading && bootstrap && canSetup && (
          <button className="subtle-button" onClick={() => setShowSetup(true)}>
            SMS setup
          </button>
        )}
        {!loading && (
          <button className="primary-button" onClick={() => void initialize()}>
            Refresh inbox
          </button>
        )}
      </main>
    );
  return (
    <CommunicationsPreview
      key={`${bootstrap.tenant_id}:${bootstrap.user_id}`}
      connection={{
        embedded,
        canManageCustomerContext: !!user && ["garage_owner", "garage_admin", "receptionist"].includes(user.role),
        rows,
        onSMSSetup: canSetup ? () => setShowSetup(true) : undefined,
        searchIds,
        onSearch,
        tenantId: bootstrap.tenant_id,
        userId: bootstrap.user_id,
        people: {
          unassigned: "Unassigned",
          ...Object.fromEntries(
            bootstrap.assignees.map((p) => [
              p.id,
              p.name + (p.id === bootstrap.user_id ? " · You" : ""),
            ]),
          ),
        },
        deliveryMode: bootstrap.delivery_mode,
        channels: bootstrap.channels,
        busy,
        error,
        pending: !!pending || blocked,
        canRecover: !!pending && !blocked,
        confirmedDraft,
        onSelect: (id) => void select(id),
        onSend: (row, body, draftKey) =>
          pending || blocked
            ? Promise.resolve(false)
            : submit(createIntent(row, body, draftKey)),
        onPatch: (row, values) => void patch(row, values),
        onOlder: (id) => void older(id),
        onRecover: () => {
          if (pending) void submit(pending);
        },
      }}
    />
  );
}
function InboxLogin({ onLogin }: { onLogin: () => Promise<void> }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <main className="inbox-entry">
      <div className="brand-mark">
        D<span>B</span>
      </div>
      <h1>Sign in to Messages</h1>
      <p>Use your workspace account.</p>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (busy) return;
          setBusy(true);
          setError("");
          try {
            const { data } = await api.post(
              "/auth/login",
              {
                email,
                password,
                remember_me: false,
              },
              { skipAuthRefresh: true },
            );
            const user = await api.get("/auth/me", {
              headers: { Authorization: `Bearer ${data.access_token}` },
            });
            useAuthStore
              .getState()
              .login(data.access_token, data.refresh_token, user.data);
            await onLogin();
          } catch (e) {
            setError(errorMessage(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Email
          <input
            type="email"
            autoComplete="username"
            value={email}
            required
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            required
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && <p role="alert">{error}</p>}
        <button className="primary-button" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
