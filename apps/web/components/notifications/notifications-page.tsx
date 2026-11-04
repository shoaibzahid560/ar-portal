"use client";

import { Panel } from "@/components/data/panel";
import { Button } from "@/components/ui/button";
import { api, type NotificationPage } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { NotificationList } from "./notification-list";

export function NotificationsPage() {
  const page = useApi<NotificationPage>("/notifications?limit=200");
  return (
    <>
      <div className="mb-3 flex items-center gap-2">
        <p className="text-[12px] text-muted">
          {page.data
            ? `${page.data.unread} unread · showing the latest ${page.data.items.length}`
            : ""}
        </p>
        {page.data && page.data.unread > 0 && (
          <Button
            className="ml-auto"
            onClick={() =>
              void api("/notifications/read-all", { method: "POST" }).then(
                page.reload,
              )
            }
          >
            Mark all as read
          </Button>
        )}
      </div>
      <Panel flush>
        {page.error ? (
          <p className="p-6 text-muted">{page.error}</p>
        ) : page.data ? (
          <NotificationList items={page.data.items} onOpened={page.reload} />
        ) : (
          <p className="p-6 text-muted">Loading…</p>
        )}
      </Panel>
    </>
  );
}
