import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import ConnectedInbox from "./ConnectedInbox";
import { getAuthenticatedSessionIdentity, useAuthStore } from "../../stores/authStore";

/** Existing dashboard authorization and session lifecycle own this surface. */
export default function DashboardInboxPage() {
  const client = useQueryClient();
  const identity = useAuthStore(getAuthenticatedSessionIdentity);
  const updateUnread = useCallback(
    (count: number) => {
      if (!identity || getAuthenticatedSessionIdentity(useAuthStore.getState()) !== identity) return;
      client.setQueryData(["messages-unread-summary", identity], {
        unread_count_staff: count,
      });
    },
    [client, identity],
  );
  return <ConnectedInbox embedded onUnreadCountChange={updateUnread} />;
}
