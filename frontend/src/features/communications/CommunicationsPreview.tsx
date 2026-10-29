import InboxSelect from "./InboxSelect";
import CustomerRepairContext from "./CustomerRepairContext";
import { rememberConversation, restoredConversation } from "./inboxSelection";
import MessageAttachments from "./MessageAttachments";
import SMSConsentPanel from "./SMSConsentPanel";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowUpRight,
  Bell,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Inbox,
  Info,
  MessageCircle,
  MessageSquare,
  Plus,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Truck,
  UserRound,
  UsersRound,
  Wrench,
  X,
  AlertCircle,
  RotateCcw,
} from "lucide-react";
import {
  canCompose,
  composeMaxLength,
  channelLabels,
  draftKey,
  filterConversations,
  restrictionLabels,
  type Channel,
  type Conversation,
  type InboxView,
  type Message,
} from "./model";
import { createDemoConversations, DEMO_TENANT, DEMO_USER } from "./fixtures";
import "./communications.css";

const demoPeople: Record<string, string> = {
  alex: "Alex · You",
  nina: "Nina",
  unassigned: "Unassigned",
};
function sameDraftRecipient(left: string, right: string): boolean {
  try {
    const a: unknown = JSON.parse(left);
    const b: unknown = JSON.parse(right);
    return Array.isArray(a) && Array.isArray(b) && a.length === 6 && b.length === 6 &&
      a.every((value) => typeof value === "string") && b.every((value) => typeof value === "string") &&
      [0, 1, 2, 3, 5].every((index) => a[index] === b[index]);
  } catch {
    return false;
  }
}
const channelIcon = (channel: Channel) =>
  channel === "telegram" ? (
    <Send size={14} />
  ) : channel === "whatsapp" ? (
    <MessageCircle size={14} />
  ) : (
    <MessageSquare size={14} />
  );
const initials = (name: string) =>
  name
    .split(" ")
    .map((n) => n[0])
    .slice(0, 2)
    .join("");
const time = (value: string) =>
  new Date(value).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
  });

const day = (value: string) =>
  new Date(value).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
    timeZone: "America/New_York",
  });

export interface InboxConnection {
  embedded?: boolean;
  canManageCustomerContext?: boolean;
  onSMSSetup?: () => void;
  rows: Conversation[];
  searchIds?: string[] | null;
  onSearch?: (search: string) => void;
  tenantId: string;
  userId: string;
  people: Record<string, string>;
  deliveryMode: string;
  channels?: { channel: string; connected: boolean }[];
  busy: boolean;
  error: string;
  pending: boolean;
  canRecover?: boolean;
  confirmedDraft?: { key: string; text: string } | null;
  onSelect: (id: string) => void;
  onSend: (
    row: Conversation,
    body: string,
    draftKey: string,
  ) => Promise<boolean>;
  onPatch: (
    row: Conversation,
    patch: { status?: "open" | "resolved"; assignee_id?: string | null },
  ) => void;
  onOlder: (id: string) => void;
  onRecover: () => void;
}
export default function CommunicationsPreview({
  connection,
}: {
  connection?: InboxConnection;
}) {
  const [demoRows, setRows] = useState(createDemoConversations);
  const rows = connection?.rows ?? demoRows;
  const tenantId = connection?.tenantId ?? DEMO_TENANT;
  const userId = connection?.userId ?? DEMO_USER;
  const people = connection?.people ?? demoPeople;
  const [view, setView] = useState<InboxView>("open");
  const [channel, setChannel] = useState<Channel | "all">("all");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState(() => connection ? restoredConversation(connection.rows, tenantId, userId)?.id ?? "01" : "01");
  const [composeChannel, setComposeChannel] = useState<Channel>("sms");
  const [drafts, setDrafts] = useState<Record<string, string>>(() => {
    if (!connection) return {};
    try {
      return JSON.parse(
        localStorage.getItem(`inbox-drafts:${tenantId}:${userId}`) || "{}",
      );
    } catch {
      return {};
    }
  });
  const [showAutomation, setShowAutomation] = useState(true);
  const [showContext, setShowContext] = useState(false);
  const [showConnections, setShowConnections] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [mobileThread, setMobileThread] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [detailsId, setDetailsId] = useState<string | null>(null);
  const [showReplies, setShowReplies] = useState(false);
  const channelSheetRef = useRef<HTMLElement>(null);
  const channelsButtonRef = useRef<HTMLButtonElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const composeRef = useRef<HTMLTextAreaElement>(null);
  const visible = useMemo(
    () =>
      filterConversations(
        rows,
        tenantId,
        view,
        channel,
        connection ? "" : search,
        userId,
      ).filter(
        (row) =>
          !connection?.searchIds || connection.searchIds.includes(row.id),
      ),
    [rows, tenantId, userId, view, channel, search, connection],
  );
  const selected = rows.find((row) => row.id === selectedId) ?? rows[0];
  const composeConversation: Conversation =
    composeChannel === selected.channel
      ? selected
      : {
          ...selected,
          channel: composeChannel,
          channelAccountId: `preview-${composeChannel}`,
          contactIdentityId: `unlinked-${selected.customerId}-${composeChannel}`,
          sendPolicy: { canSend: false, reason: "not_connected" },
        };
  const key = draftKey(tenantId, userId, composeConversation);
  const draft = drafts[key] || "";
  const previousRoute = useRef({ key, thread: selected.id, recipient: selected.contactIdentityId, channel: composeChannel, tenantId, userId });
  const copiedDraftOrigins = useRef<Record<string, string> | null>(null);
  if (copiedDraftOrigins.current === null) {
    try {
      const saved = connection ? JSON.parse(localStorage.getItem(`inbox-draft-origins:${tenantId}:${userId}`) || "{}") : {};
      copiedDraftOrigins.current = Object.fromEntries(Object.entries(saved).filter((entry): entry is [string, string] => typeof entry[1] === "string" && sameDraftRecipient(entry[0], entry[1])));
    } catch {
      copiedDraftOrigins.current = {};
    }
  }
  const maxLength = composeMaxLength(composeConversation);
  const counts = {
    open: rows.filter((r) => r.status === "open").length,
    unread: rows.filter((r) => r.status === "open" && r.unreadCount > 0).length,
    mine: rows.filter((r) => r.status === "open" && r.assigneeId === userId)
      .length,
    resolved: rows.filter((r) => r.status === "resolved").length,
    inquiries: rows.filter((r) => r.tenantId === tenantId && r.status === "open" && r.conversationKind === "inquiry" && r.unreadCount > 0).length,
  };
  const messages = selected.messages.filter(
    (message) => showAutomation || message.source !== "automation",
  );
  const failed = selected.messages.find((message) =>
    ["failed", "undelivered", "unknown"].includes(message.deliveryStatus),
  );
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [selectedId, selected.messages.length, showAutomation, mobileThread]);
  useEffect(() => {
    if (!showConnections) return;
    const opener = channelsButtonRef.current;
    const closeButton =
      channelSheetRef.current?.querySelector<HTMLButtonElement>("button");
    closeButton?.focus();
    const handleKeys = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setShowConnections(false);
      }
      if (event.key === "Tab") {
        event.preventDefault();
        closeButton?.focus();
      }
    };
    document.addEventListener("keydown", handleKeys);
    return () => {
      document.removeEventListener("keydown", handleKeys);
      opener?.focus();
    };
  }, [showConnections]);
  useEffect(() => {
    const before = previousRoute.current;
    previousRoute.current = { key, thread: selected.id, recipient: selected.contactIdentityId, channel: composeChannel, tenantId, userId };
    if (before.key === key || before.thread !== selected.id ||
        before.recipient !== selected.contactIdentityId || before.channel !== composeChannel ||
        before.tenantId !== tenantId || before.userId !== userId) return;
    setDrafts((previous) => {
      const text = previous[before.key];
      const confirmed = connection?.confirmedDraft;
      if (!text || previous[key] || (confirmed?.key === before.key && confirmed.text === text)) return previous;
      copiedDraftOrigins.current![key] = copiedDraftOrigins.current![before.key] ?? before.key;
      return { ...previous, [key]: text };
    });
  }, [key, selected.id, selected.contactIdentityId, composeChannel, tenantId, userId, connection?.confirmedDraft]);
  useEffect(() => {
    if (connection) {
      localStorage.setItem(
        `inbox-drafts:${tenantId}:${userId}`,
        JSON.stringify(drafts),
      );
      localStorage.setItem(`inbox-draft-origins:${tenantId}:${userId}`, JSON.stringify(copiedDraftOrigins.current));
    }
  }, [drafts, tenantId, userId, connection]);
  useEffect(() => {
    const confirmed = connection?.confirmedDraft;
    if (confirmed)
      setDrafts((previous) => {
        const next = { ...previous };
        for (const draftId of Object.keys(next))
          if ((draftId === confirmed.key || (copiedDraftOrigins.current?.[draftId] === confirmed.key && sameDraftRecipient(draftId, confirmed.key))) && next[draftId] === confirmed.text)
            next[draftId] = "";
        return next;
      });
  }, [connection?.confirmedDraft]);
  const onSearch = connection?.onSearch;
  useEffect(() => {
    onSearch?.(search);
  }, [search, onSearch]);
  function updateDraft(value: string) {
    setDrafts((previous) => ({ ...previous, [key]: value }));
  }
  function selectConversation(row: Conversation) {
    if (connection) rememberConversation(row.id, tenantId, userId);
    setSelectedId(row.id);
    setComposeChannel(row.channel);
    setMobileThread(true);
    setShowNew(false);
    setShowContext(false);
    setDetailsId(null);
    if (connection) {
      connection.onSelect(row.id);
      return;
    }
    setRows((previous) =>
      previous.map((item) =>
        item.id === row.id ? { ...item, unreadCount: 0 } : item,
      ),
    );
  }
  async function sendPreview() {
    if (!canCompose(composeConversation, draft)) return;
    if (connection) {
      const submitted = draft;
      if (await connection.onSend(composeConversation, submitted, key)) {
        setDrafts((previous) =>
          previous[key] === submitted ? { ...previous, [key]: "" } : previous,
        );
      }
      return;
    }
    const next: Message = {
      id: crypto.randomUUID(),
      conversationId: selected.id,
      channel: composeChannel,
      direction: "outbound",
      source: "staff",
      body: draft.trim(),
      createdAt: new Date().toISOString(),
      deliveryStatus: "queued",
    };
    setRows((previous) =>
      previous.map((row) =>
        row.id === selected.id
          ? {
              ...row,
              messages: [...row.messages, next],
              preview: next.body,
              lastMessageAt: next.createdAt,
              status: "open",
            }
          : row,
      ),
    );
    updateDraft("");
    setFeedback("Added to the preview. No message was sent.");
    setShowReplies(false);
    composeRef.current?.focus();
  }
  function resolve() {
    const status = selected.status === "open" ? "resolved" : "open";
    if (connection) {
      connection.onPatch(selected, { status });
      return;
    }
    setRows((previous) =>
      previous.map((row) =>
        row.id === selected.id ? { ...row, status, unreadCount: 0 } : row,
      ),
    );
    setFeedback(
      status === "resolved"
        ? "Conversation resolved in this preview."
        : "Conversation reopened in this preview.",
    );
  }
  return (
    <div className={`comms-app${connection ? "" : " communications-surface"}`}>
      {!connection?.embedded && (
        <aside className="app-rail" aria-label="DieselBridge workspace">
          <div className="brand-mark">
            D<span>B</span>
          </div>
          <div className="shop-mark">TP</div>
          <div className="rail-icons">
            <Wrench />
            <Truck />
            <UsersRound />
            <span className="rail-current">
              <MessageSquare />
            </span>
          </div>
          <div className="rail-bottom">
            <span className="rail-avatar">
              {connection ? initials(people[userId] || "Staff") : "AP"}
            </span>
          </div>
        </aside>
      )}
      <main className="comms-workspace">
        {!connection?.embedded && (
          <div className="preview-strip">
            <span>
              <span className="preview-dot" />{" "}
              {connection ? "Connected inbox" : "Interactive prototype"}
            </span>
            <span>
              {connection
                ? connection.deliveryMode === "simulated"
                  ? "Isolated workspace · Simulated SMS"
                  : "Live SMS delivery"
                : "Sample conversations · No messages are sent"}
            </span>
          </div>
        )}
        <header className="page-header">
          <div>
            <div className="breadcrumb">
              {connection ? "Workspace" : "Truck Pit Stop"}{" "}
              <ChevronRight size={12} /> Communication
            </div>
            <h1>
              Messages <span className="heading-count">{counts.open}</span>
            </h1>
          </div>
          <div className="page-actions">
            {connection?.embedded && (
              <a
                className="subtle-button previous-inbox"
                href="/dashboard/messages/previous"
                title="Previous inbox: start new SMS, view archived conversations"
              >
                Previous inbox
              </a>
            )}
            {connection?.onSMSSetup && (
              <button
                className="subtle-button"
                aria-label="SMS setup"
                title="SMS setup"
                onClick={connection.onSMSSetup}
              >
                <Settings2 size={16} /> <span>SMS setup</span>
              </button>
            )}
            <button
              ref={channelsButtonRef}
              aria-label="Channels"
              className="subtle-button"
              onClick={() => setShowConnections(true)}
            >
              <Settings2 size={16} />
              <span>Channels</span>
            </button>
            <button
              className="primary-button"
              aria-label={connection ? "Open conversation" : "New message"}
              title={connection ? "Open conversation" : "New message"}
              onClick={() => {
                setShowNew(!showNew);
                setMobileThread(false);
              }}
            >
              <Plus size={17} />
              <span>{connection ? "Open conversation" : "New message"}</span>
            </button>
          </div>
        </header>
        <div
          className={`inbox-layout ${mobileThread ? "mobile-thread" : ""} ${showContext ? "context-open" : ""}`}
        >
          <section className="conversation-list" aria-label="Conversations">
            <div className="list-tools">
              <div className="view-tabs">
                {(
                  [
                    ["open", "Open"],
                    ["unread", "Unread"],
                    ["mine", "Mine"],
                    ["resolved", "Resolved"],
                    ["inquiries", "New inquiries"],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    aria-pressed={view === value}
                    onClick={() => setView(value)}
                  >
                    {label}
                    <span>{counts[value]}</span>
                  </button>
                ))}
              </div>
              <label className="search-field">
                <Search size={16} />
                <input
                  aria-label="Search conversations"
                  placeholder="Search name, truck, or message"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
                {search && (
                  <button
                    aria-label="Clear search"
                    onClick={() => setSearch("")}
                  >
                    <X size={14} />
                  </button>
                )}
              </label>
              <div className="channel-filters" aria-label="Filter by channel">
                {(["all", "sms", "whatsapp", "telegram"] as const).map(
                  (value) => (
                    <button
                      key={value}
                      aria-pressed={channel === value}
                      onClick={() => setChannel(value)}
                    >
                      {value === "all" ? "All" : channelLabels[value]}
                    </button>
                  ),
                )}
              </div>
            </div>
            {showNew && (
              <div className="new-conversation">
                <div>
                  <strong>
                    {connection
                      ? "Open an existing conversation"
                      : "Choose a sample contact"}
                  </strong>
                  <button
                    aria-label="Close new message"
                    onClick={() => setShowNew(false)}
                  >
                    <X size={16} />
                  </button>
                </div>
                {rows
                  .filter((row) => row.channel === "sms")
                  .map((row) => (
                    <button
                      key={row.id}
                      onClick={() => selectConversation(row)}
                    >
                      <UserRound size={15} />
                      {row.customerName}
                      <ChevronRight size={14} />
                    </button>
                  ))}
              </div>
            )}
            <div className="list-heading">
              <span>
                {view === "mine"
                  ? "ASSIGNED TO YOU"
                  : view === "inquiries" ? "NEW INQUIRIES"
                  : view.toUpperCase() + " CONVERSATIONS"}
              </span>
              <span>{visible.length}</span>
            </div>
            <div className="thread-rows">
              {visible.map((row) => (
                <button
                  className={`thread-row ${row.id === selectedId ? "selected" : ""}`}
                  key={row.id}
                  onClick={() => selectConversation(row)}
                  aria-pressed={row.id === selectedId}
                >
                  <span
                    className={`avatar avatar-${row.id}`}
                    aria-hidden="true"
                  >
                    {initials(row.customerName)}
                    <span className={`channel-mark ${row.channel}`}>
                      {channelIcon(row.channel)}
                    </span>
                  </span>
                  <span className="thread-copy">
                    <span className="thread-top">
                      <strong>{row.customerName}</strong>
                      <span>{time(row.lastMessageAt)}</span>
                    </span>
                    {(row.company || row.conversationKind === "inquiry") && (
                      <span className="thread-company">{row.conversationKind === "inquiry" ? row.identityLabel : row.company}</span>
                    )}
                    <span className="thread-preview">
                      {row.messages.some(
                        (m) => m.deliveryStatus === "undelivered",
                      ) && <AlertCircle size={13} />}
                      {row.preview}
                    </span>
                    <span className="thread-meta">
                      {row.conversationKind === "inquiry" && <span>To {row.context.senderNumber}</span>}
                      {row.context.repairOrderLabel && (
                        <span>{row.context.repairOrderLabel}</span>
                      )}
                      {row.channel !== "sms" && <span>Not connected</span>}
                      {row.sendPolicy.reason === "opted_out" && (
                        <span>Opted out</span>
                      )}
                      {row.unreadCount > 0 && (
                        <b className="unread-dot">{row.unreadCount}</b>
                      )}
                    </span>
                  </span>
                </button>
              ))}
              {!visible.length && (
                <div className="empty-list">
                  <Inbox size={27} />
                  <strong>No conversations here</strong>
                  <span>Try another filter or search.</span>
                  <button
                    onClick={() => {
                      setSearch("");
                      setChannel("all");
                      setView("open");
                    }}
                  >
                    Clear filters
                  </button>
                </div>
              )}
            </div>
            <div className="list-footer">
              <ShieldCheck size={14} />
              <span>
                {connection ? "Shared workspace" : "Preview workspace"}
              </span>
              <span className="connection-dot" />
              SMS
            </div>
          </section>
          <section
            className="conversation"
            aria-label={`Conversation with ${selected.customerName}`}
          >
            <header className="conversation-header">
              <button
                className="mobile-back icon-button"
                aria-label="Back to conversations"
                onClick={() => setMobileThread(false)}
              >
                <ArrowLeft size={20} />
              </button>
              <span className="avatar header-avatar">
                {initials(selected.customerName)}
              </span>
              <div className="conversation-title">
                <h2>{selected.customerName}</h2>
                <span>
                  {(selected.conversationKind === "inquiry" || selected.company) && <>{selected.conversationKind === "inquiry" ? selected.identityLabel : selected.company} <span className="separator">·</span>{" "}</>}
                  {channelLabels[selected.channel]}
                </span>
                {selected.conversationKind === "inquiry" && <span>CallRail · To {selected.context.senderNumber}</span>}
              </div>
              <div className="conversation-actions">
                <button
                  aria-label={
                    selected.status === "resolved" ? "Reopen" : "Resolve"
                  }
                  className={`resolve-button ${selected.status === "resolved" ? "resolved" : ""}`}
                  onClick={resolve}
                  disabled={connection?.busy}
                >
                  {selected.status === "resolved" ? (
                    <RotateCcw size={16} />
                  ) : (
                    <Check size={16} />
                  )}
                  <span>
                    {selected.status === "resolved" ? "Reopen" : "Resolve"}
                  </span>
                </button>
                <button
                  className="icon-button context-toggle"
                  aria-label="Toggle customer details"
                  aria-pressed={showContext}
                  onClick={() => setShowContext(!showContext)}
                >
                  <Info size={19} />
                </button>
              </div>
            </header>
            <div className="conversation-toolbar">
              <span className={`channel-chip ${selected.channel}`}>
                {channelIcon(selected.channel)}
                {channelLabels[selected.channel]}
              </span>
              <label className="assigned-label">
                <UserRound size={14} />
                <InboxSelect label="Assign conversation" value={selected.assigneeId || "unassigned"} disabled={connection?.busy}
                  options={Object.entries(people).map(([value, label]) => ({value, label}))}
                  onChange={(value) => {
                    const assigneeId = value === "unassigned" ? null : value;
                    if (connection)
                      connection.onPatch(selected, { assignee_id: assigneeId });
                    else
                      setRows((previous) =>
                        previous.map((row) =>
                          row.id === selected.id ? { ...row, assigneeId } : row,
                        ),
                      );
                  }} />
              </label>
              {selected.conversationKind !== "inquiry" && <button
                className={`automation-toggle ${showAutomation ? "active" : ""}`}
                aria-pressed={showAutomation}
                onClick={() => setShowAutomation(!showAutomation)}
              >
                <Bell size={13} />
                <span>Service updates</span>
                <span className="switch-track" />
              </button>}
            </div>
            {failed && (
              <div className="delivery-alert">
                <AlertCircle size={16} />
                <span>
                  {failed.deliveryStatus === "unknown"
                    ? "Delivery needs verification"
                    : "One message was not delivered"}
                </span>
                <button
                  onClick={() =>
                    setDetailsId(detailsId === failed.id ? null : failed.id)
                  }
                >
                  Details <ChevronDown size={12} />
                </button>
              </div>
            )}
            <div className="message-scroll">
              <div className="message-stack">
                {connection && selected.messagesHasMore && (
                  <button
                    className="subtle-button"
                    onClick={() => connection.onOlder(selected.id)}
                  >
                    Load older messages
                  </button>
                )}
                {messages.map((message, index) => (
                  <Fragment key={message.id}>
                    {(index === 0 ||
                      day(messages[index - 1].createdAt) !==
                        day(message.createdAt)) && (
                      <div className="day-divider">
                        <span>{day(message.createdAt)}</span>
                      </div>
                    )}
                    <div
                      className={`message-line ${message.direction} ${message.source === "automation" ? "automated" : ""}`}
                    >
                      {message.source === "automation" ? (
                        <div className="service-event">
                          <span>
                            <Bell size={13} />
                            Service update<span>{time(message.createdAt)}</span>
                          </span>
                          <p>{message.body}</p>
                          <button
                            className="delivery-detail"
                            onClick={() =>
                              setDetailsId(
                                detailsId === message.id ? null : message.id,
                              )
                            }
                          >
                            <DeliveryStatus status={message.deliveryStatus} />
                            {message.deliveryStatus}
                            <ChevronDown size={11} />
                          </button>
                        </div>
                      ) : (
                        <>
                          <div className="message-bubble">
                            {connection && message.hasAttachments && message.direction === "inbound" ? (
                              <MessageAttachments tenantId={tenantId} message={message} />
                            ) : message.body}
                          </div>
                          <div className="message-meta">
                            {message.direction === "outbound" && (
                              <>
                                <span>{connection ? "Team" : "Alex"}</span>
                                <span>·</span>
                                <DeliveryStatus
                                  status={message.deliveryStatus}
                                />
                              </>
                            )}
                            {time(message.createdAt)}
                            {message.direction === "outbound" && (
                              <span>
                                {!connection &&
                                message.deliveryStatus === "queued"
                                  ? "Preview only"
                                  : message.deliveryStatus}
                              </span>
                            )}
                          </div>
                        </>
                      )}
                      {detailsId === message.id && (
                        <div className="message-details">
                          <strong>Delivery details</strong>
                          <span>Status: {message.deliveryStatus}</span>
                          <span>
                            {message.errorCode
                              ? `Provider code: ${message.errorCode}${connection ? "" : " (sample)"}`
                              : connection
                                ? "No provider error code"
                                : "Sample delivery event"}
                          </span>
                          <p>
                            Check the recipient and provider record before
                            retrying. Uncertain messages must not be resent.
                          </p>
                        </div>
                      )}
                    </div>
                  </Fragment>
                ))}
                {!messages.length && (
                  <div className="empty-channel">
                    {channelIcon(selected.channel)}
                    <h3>
                      {connection
                        ? "No messages yet"
                        : `${channelLabels[selected.channel]} is next`}
                    </h3>
                    <p>
                      {selected.channel === "telegram"
                        ? "Customers will start a chat with your shop bot, then replies will appear here."
                        : "Connect a business sender to receive customer messages in this inbox."}
                    </p>
                    <button onClick={() => setShowConnections(true)}>
                      View channel setup <ArrowUpRight size={14} />
                    </button>
                  </div>
                )}
                <div ref={endRef} />
              </div>
            </div>
            <div className="composer-area">
              {connection?.error && (
                <div className="compose-restriction" role="alert">
                  {connection.error}
                </div>
              )}
              {connection?.pending && (
                <div className="compose-restriction">
                  <span>
                    A send request needs confirmation. Your original message is
                    preserved.
                  </span>
                  <button
                    className="subtle-button"
                    disabled={
                      connection.busy || connection.canRecover === false
                    }
                    onClick={connection.onRecover}
                  >
                    Check original send
                  </button>
                </div>
              )}
              <div className="composer-heading">
                <label>
                  Reply via{" "}
                  <span className="channel-select">
                    {channelIcon(composeChannel)}
                    <InboxSelect label="Reply channel" value={composeChannel} onChange={value => setComposeChannel(value as Channel)}
                      options={(["sms", "whatsapp", "telegram"] as const).map(value => ({value, label: channelLabels[value]}))} />
                  </span>
                </label>
                {composeChannel !== selected.channel && <span>Not connected</span>}
              </div>
              {composeChannel === "sms" && (selected.context.senderNumber || selected.context.senderMode === "unavailable") && (
                <p className="sms-sender" aria-label="SMS sender">
                  {selected.context.senderMode === "unavailable"
                    ? "Reply number unavailable"
                    : `${selected.context.senderMode === "initiation" ? "Sending" : "Replying"} from ${selected.context.senderNumber}`}
                </p>
              )}
              {composeConversation.sendPolicy.reason && (
                <div className="compose-restriction" role="status">
                  <Info size={15} />
                  {restrictionLabels[composeConversation.sendPolicy.reason] ??
                    "SMS connection or consent requires review."}
                </div>
              )}
              <div className="composer-box">
                <textarea
                  ref={composeRef}
                  aria-label="Message draft"
                  value={draft}
                  onChange={(event) => updateDraft(event.target.value)}
                  placeholder={
                    composeConversation.sendPolicy.canSend
                      ? "Write a reply…"
                      : "Draft a message for later…"
                  }
                  rows={2}
                  onKeyDown={(event) => {
                    if (
                      (event.metaKey || event.ctrlKey) &&
                      event.key === "Enter"
                    ) {
                      event.preventDefault();
                      sendPreview();
                    }
                  }}
                />
                <div className="composer-controls">
                  <div className="reply-options">
                    <button
                      aria-expanded={showReplies}
                      onClick={() => setShowReplies(!showReplies)}
                    >
                      <MessageSquare size={15} />
                      Saved replies
                      <ChevronDown size={12} />
                    </button>
                    <span className={draft.trim().length > maxLength ? "over-limit" : ""}>
                      {draft.length}/{maxLength}
                    </span>
                  </div>
                  <button
                    className="primary-button send-button"
                    disabled={
                      !canCompose(composeConversation, draft) ||
                      connection?.busy ||
                      connection?.pending
                    }
                    onClick={sendPreview}
                  >
                    <Send size={15} />
                    {connection ? "Send SMS" : "Send preview"}
                  </button>
                </div>
                {showReplies && (
                  <div className="saved-replies">
                    {[
                      "The truck is ready for pickup. What time should we expect your driver?",
                      "We’re checking on the parts ETA and will update you shortly.",
                      "Thanks for the update. I’ll pass this along to the technician.",
                    ].map((reply) => (
                      <button
                        key={reply}
                        onClick={() => {
                          updateDraft(draft ? `${draft}\n${reply}` : reply);
                          setShowReplies(false);
                          composeRef.current?.focus();
                        }}
                      >
                        {reply}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="composer-footnote">
                <span>Enter for a new line · ⌘/Ctrl + Enter to send</span>
                <span>Drafts stay with this contact and channel</span>
              </div>
            </div>
          </section>
          <aside className="customer-context" aria-label="Customer details">
            <header>
              <h3>Contact details</h3>
              <button
                className="icon-button close-context"
                aria-label="Close customer details"
                onClick={() => setShowContext(false)}
              >
                <X size={17} />
              </button>
            </header>
            <div className="customer-context-scroll">
            {!connection?.canManageCustomerContext && <>
            {connection && selected.customerId && selected.conversationKind !== "inquiry" && (
              <SMSConsentPanel
                key={`${connection.tenantId}:${connection.userId}:${selected.customerId}`}
                customerId={selected.customerId}
              />
            )}
            </>}
            {!connection?.canManageCustomerContext && <div className="contact-profile">
              <span className="avatar context-avatar">{initials(selected.customerName)}</span>
              <strong>{selected.customerName}</strong>
              {selected.company && <span>{selected.company}</span>}
              <p className="identity-value">{selected.identityLabel}</p>
              {selected.sendPolicy.reason === "opted_out" && <p className="context-warning">SMS opted out</p>}
            </div>}
            {connection?.canManageCustomerContext ? <CustomerRepairContext
              key={`${tenantId}:${userId}:${selected.id}`}
              conversation={selected}
              sessionKey={`${tenantId}:${userId}`}
              beforeNavigate={() => {
                rememberConversation(selected.id, tenantId, userId);
                localStorage.setItem(`inbox-drafts:${tenantId}:${userId}`, JSON.stringify(drafts));
              }}
            >
            {connection && selected.customerId && selected.conversationKind !== "inquiry" && (
              <SMSConsentPanel
                key={`${connection.tenantId}:${connection.userId}:${selected.customerId}`}
                customerId={selected.customerId}
              />
            )}
            </CustomerRepairContext> : !connection && <section>
              <h4>Current repair</h4>
              {selected.context.repairOrderLabel ? (
                <>
                  <div className="order-title">
                    <Wrench size={16} />
                    <strong>{selected.context.repairOrderLabel}</strong>
                  </div>
                  <span className="repair-status">
                    {selected.context.repairStatus}
                  </span>
                  <div className="vehicle-context">
                    <Truck size={17} />
                    <span>{selected.context.vehicleLabel}</span>
                  </div>
                  <p className="concern">{selected.context.concern}</p>
                </>
              ) : (
                <p className="muted">No repair order linked</p>
              )}
            </section>}
            <div className="context-note">
              <CircleHelp size={15} />
              <p>
                Repair approvals stay on the repair order. A chat reply does not
                approve work.
              </p>
            </div>
            </div>
            <footer className="customer-context-footer" aria-label="Conversation details">
              <dl>
                <div>
                  <dt>Assigned to</dt>
                  <dd>{people[selected.assigneeId || "unassigned"]}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{selected.status === "open" ? "Open" : "Resolved"}</dd>
                </div>
                <div>
                  <dt>Channel</dt>
                  <dd>{channelLabels[selected.channel]}</dd>
                </div>
              </dl>
            </footer>
          </aside>
        </div>
        <div className="feedback" role="status" aria-live="polite">
          {feedback && (
            <>
              <Check size={15} />
              {feedback}
              <button
                aria-label="Dismiss notification"
                onClick={() => setFeedback("")}
              >
                <X size={14} />
              </button>
            </>
          )}
        </div>
      </main>
      {showConnections && (
        <div
          className="sheet-backdrop"
          onClick={() => setShowConnections(false)}
        >
          <section
            ref={channelSheetRef}
            className="connections-sheet"
            role="dialog"
            aria-modal="true"
            aria-label="Channel connections"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === "Escape") setShowConnections(false);
            }}
          >
            <header>
              <div>
                <h2>Channel connections</h2>
                <p>One inbox. Every conversation in context.</p>
              </div>
              <button
                autoFocus
                className="icon-button"
                aria-label="Close channel connections"
                onClick={() => setShowConnections(false)}
              >
                <X size={20} />
              </button>
            </header>
            {(["sms", "whatsapp", "telegram"] as const).map((value) => (
              <div className="connection-row" key={value}>
                <span className={`channel-chip ${value}`}>
                  {channelIcon(value)}
                </span>
                <div>
                  <h3>{channelLabels[value]}</h3>
                  <p>
                    {value === "sms"
                      ? connection
                        ? `SMS delivery: ${connection.deliveryMode}`
                        : "Existing Twilio connection · Sample data in this preview"
                      : value === "whatsapp"
                        ? "Business sender and approved templates required"
                        : "Shop bot and customer-started conversation required"}
                  </p>
                </div>
                <span
                  className={`connection-state ${value === "sms" && (!connection || connection.channels?.some((c) => c.channel === value && c.connected)) ? "ready" : ""}`}
                >
                  {value === "sms"
                    ? connection
                      ? connection.channels?.some(
                          (c) => c.channel === value && c.connected,
                        )
                        ? "Connected"
                        : "Unavailable"
                      : "Preview active"
                    : "Planned"}
                </span>
              </div>
            ))}
            <div className="connection-summary">
              <ShieldCheck size={18} />
              <p>
                {connection
                  ? "New channels require setup and approval before messages can be sent."
                  : "Provider setup and live messaging are separate from this prototype. No account changes are made here."}
              </p>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
function DeliveryStatus({ status }: { status: Message["deliveryStatus"] }) {
  if (status === "delivered") return <CheckCheck size={13} />;
  if (status === "failed" || status === "undelivered" || status === "unknown")
    return <AlertCircle size={13} />;
  if (status === "sent") return <Check size={13} />;
  return <Clock3 size={13} />;
}
