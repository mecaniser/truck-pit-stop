import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import ConnectedInbox from "./ConnectedInbox";

/** Existing dashboard authorization and session lifecycle own this surface. */
export default function DashboardInboxPage() {
  const client = useQueryClient();
  const updateUnread = useCallback(
    (count: number) => {
      client.setQueryData(["messages-unread-summary"], {
        unread_count_staff: count,
      });
    },
    [client],
  );
  return <ConnectedInbox embedded onUnreadCountChange={updateUnread} />;
}
