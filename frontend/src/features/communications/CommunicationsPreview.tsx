import { useEffect, useMemo, useRef, useState } from "react";
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

const people: Record<string, string> = {
  alex: "Alex · You",
  nina: "Nina",
  unassigned: "Unassigned",
};
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

export default function CommunicationsPreview() {
  const [rows, setRows] = useState(createDemoConversations);
  const [view, setView] = useState<InboxView>("open");
  const [channel, setChannel] = useState<Channel | "all">("all");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState("01");
  const [composeChannel, setComposeChannel] = useState<Channel>("sms");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
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
      filterConversations(rows, DEMO_TENANT, view, channel, search, DEMO_USER),
    [rows, view, channel, search],
  );
  const selected = rows.find((row) => row.id === selectedId)!;
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
  const key = draftKey(DEMO_TENANT, DEMO_USER, composeConversation);
  const draft = drafts[key] || "";
  const counts = {
    open: rows.filter((r) => r.status === "open").length,
    unread: rows.filter((r) => r.status === "open" && r.unreadCount > 0).length,
    mine: rows.filter((r) => r.status === "open" && r.assigneeId === DEMO_USER)
      .length,
    resolved: rows.filter((r) => r.status === "resolved").length,
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
  function updateDraft(value: string) {
    setDrafts((previous) => ({ ...previous, [key]: value }));
  }
  function selectConversation(row: Conversation) {
    setSelectedId(row.id);
    setComposeChannel(row.channel);
    setMobileThread(true);
    setShowNew(false);
    setShowContext(false);
    setDetailsId(null);
    setRows((previous) =>
      previous.map((item) =>
        item.id === row.id ? { ...item, unreadCount: 0 } : item,
      ),
    );
  }
  function sendPreview() {
    if (!canCompose(composeConversation, draft)) return;
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
    <div className="comms-app">
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
          <span className="rail-avatar">AP</span>
        </div>
      </aside>
      <main className="comms-workspace">
        <div className="preview-strip">
          <span>
            <span className="preview-dot" /> Interactive prototype
          </span>
          <span>Sample conversations · No messages are sent</span>
        </div>
        <header className="page-header">
          <div>
            <div className="breadcrumb">
              Truck Pit Stop <ChevronRight size={12} /> Communication
            </div>
            <h1>
              Messages <span className="heading-count">{counts.open}</span>
            </h1>
          </div>
          <div className="page-actions">
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
              onClick={() => {
                setShowNew(!showNew);
                setMobileThread(false);
              }}
            >
              <Plus size={17} />
              New message
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
                  <strong>Choose a sample contact</strong>
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
                    <span className="thread-company">{row.company}</span>
                    <span className="thread-preview">
                      {row.messages.some(
                        (m) => m.deliveryStatus === "undelivered",
                      ) && <AlertCircle size={13} />}
                      {row.preview}
                    </span>
                    <span className="thread-meta">
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
              <span>Preview workspace</span>
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
                  {selected.company} <span className="separator">·</span>{" "}
                  {channelLabels[selected.channel]}
                </span>
              </div>
              <div className="conversation-actions">
                <button
                  aria-label={
                    selected.status === "resolved" ? "Reopen" : "Resolve"
                  }
                  className={`resolve-button ${selected.status === "resolved" ? "resolved" : ""}`}
                  onClick={resolve}
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
                <select
                  aria-label="Assign conversation"
                  value={selected.assigneeId || "unassigned"}
                  onChange={(event) =>
                    setRows((previous) =>
                      previous.map((row) =>
                        row.id === selected.id
                          ? {
                              ...row,
                              assigneeId:
                                event.target.value === "unassigned"
                                  ? null
                                  : event.target.value,
                            }
                          : row,
                      ),
                    )
                  }
                >
                  {Object.entries(people).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <ChevronDown size={12} />
              </label>
              <button
                className={`automation-toggle ${showAutomation ? "active" : ""}`}
                aria-pressed={showAutomation}
                onClick={() => setShowAutomation(!showAutomation)}
              >
                <Bell size={13} />
                <span>Service updates</span>
                <span className="switch-track" />
              </button>
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
              <div className="day-divider">
                <span>Friday, October 16</span>
              </div>
              <div className="message-stack">
                {messages.map((message) => (
                  <div
                    key={message.id}
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
                        <div className="message-bubble">{message.body}</div>
                        <div className="message-meta">
                          {message.direction === "outbound" && (
                            <>
                              <span>Alex</span>
                              <span>·</span>
                              <DeliveryStatus status={message.deliveryStatus} />
                            </>
                          )}
                          {time(message.createdAt)}
                          {message.direction === "outbound" && (
                            <span>
                              {message.deliveryStatus === "queued"
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
                            ? `Provider code: ${message.errorCode} (sample)`
                            : "Sample delivery event"}
                        </span>
                        <p>
                          Check the recipient and provider record before
                          retrying. This preview does not resend messages.
                        </p>
                      </div>
                    )}
                  </div>
                ))}
                {!messages.length && (
                  <div className="empty-channel">
                    {channelIcon(selected.channel)}
                    <h3>{channelLabels[selected.channel]} is next</h3>
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
              <div className="composer-heading">
                <label>
                  Reply via{" "}
                  <span className="channel-select">
                    {channelIcon(composeChannel)}
                    <select
                      aria-label="Reply channel"
                      value={composeChannel}
                      onChange={(event) =>
                        setComposeChannel(event.target.value as Channel)
                      }
                    >
                      {(["sms", "whatsapp", "telegram"] as const).map(
                        (value) => (
                          <option value={value} key={value}>
                            {channelLabels[value]}
                          </option>
                        ),
                      )}
                    </select>
                    <ChevronDown size={12} />
                  </span>
                </label>
                <span>
                  {composeChannel === selected.channel
                    ? selected.identityLabel
                    : "Not connected"}
                </span>
              </div>
              {composeConversation.sendPolicy.reason && (
                <div className="compose-restriction" role="status">
                  <Info size={15} />
                  {restrictionLabels[composeConversation.sendPolicy.reason]}
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
                    <span className={draft.length > 1600 ? "over-limit" : ""}>
                      {draft.length}/1600
                    </span>
                  </div>
                  <button
                    className="primary-button send-button"
                    disabled={!canCompose(composeConversation, draft)}
                    onClick={sendPreview}
                  >
                    <Send size={15} />
                    Send preview
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
            <div className="contact-profile">
              <span className="avatar context-avatar">
                {initials(selected.customerName)}
              </span>
              <strong>{selected.customerName}</strong>
              <span>{selected.company}</span>
            </div>
            <section>
              <h4>Contact</h4>
              <div className="identity-row">
                <span className={`channel-chip ${selected.channel}`}>
                  {channelIcon(selected.channel)}
                  {channelLabels[selected.channel]}
                </span>
                <span>
                  {selected.channel === "sms"
                    ? "Sample identity"
                    : "Not linked"}
                </span>
              </div>
              <p className="identity-value">{selected.identityLabel}</p>
              {selected.sendPolicy.reason === "opted_out" && (
                <p className="context-warning">SMS opted out</p>
              )}
            </section>
            <section>
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
            </section>
            <section>
              <h4>Conversation</h4>
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
            </section>
            <div className="context-note">
              <CircleHelp size={15} />
              <p>
                Repair approvals stay on the repair order. A chat reply does not
                approve work.
              </p>
            </div>
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
                      ? "Existing Twilio connection · Sample data in this preview"
                      : value === "whatsapp"
                        ? "Business sender and approved templates required"
                        : "Shop bot and customer-started conversation required"}
                  </p>
                </div>
                <span
                  className={`connection-state ${value === "sms" ? "ready" : ""}`}
                >
                  {value === "sms" ? "Preview active" : "Planned"}
                </span>
              </div>
            ))}
            <div className="connection-summary">
              <ShieldCheck size={18} />
              <p>
                Provider setup and live messaging are separate from this
                prototype. No account changes are made here.
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
