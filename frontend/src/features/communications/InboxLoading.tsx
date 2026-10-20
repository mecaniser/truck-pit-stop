import { MessageSquare } from "lucide-react";
import "./inbox-loading.css";

/** Shared by the route chunk and data waits, so the inbox opens in one frame. */
export default function InboxLoading() {
  return (
    <section className="inbox-loading" aria-busy="true" aria-label="Messages">
      <header className="inbox-loading__header">
        <span className="inbox-loading__mark" aria-hidden="true">
          <MessageSquare size={24} />
        </span>
        <div>
          <h1>Messages</h1>
          <p role="status">Loading your inbox…</p>
        </div>
      </header>
      <div className="inbox-loading__workspace" aria-hidden="true">
        <div className="inbox-loading__list">
          <span className="inbox-loading__search" />
          {Array.from({ length: 5 }, (_, i) => (
            <div className="inbox-loading__contact" key={i}>
              <span className="inbox-loading__avatar" />
              <div className="inbox-loading__lines">
                <span /><span />
              </div>
            </div>
          ))}
        </div>
        <div className="inbox-loading__conversation">
          <div className="inbox-loading__contact inbox-loading__recipient">
            <span className="inbox-loading__avatar" />
            <div className="inbox-loading__lines"><span /><span /></div>
          </div>
          <div className="inbox-loading__messages">
            <span /><span /><span />
          </div>
          <div className="inbox-loading__composer" />
        </div>
      </div>
    </section>
  );
}
