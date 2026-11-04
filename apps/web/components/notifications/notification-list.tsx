"use client";

import { useRouter } from "next/navigation";
import { api, type AppNotification } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";

/** A list of notifications. Opening one marks it read and goes to the record it's about. */
export function NotificationList({
  items,
  onOpened,
  compact = false,
}: {
  items: AppNotification[];
  onOpened?: () => void;
  compact?: boolean;
}) {
  const router = useRouter();

  async function open(item: AppNotification) {
    if (!item.read)
      await api(`/notifications/${item.id}/read`, { method: "POST" }).catch(
        () => undefined,
      );
    onOpened?.();
    if (item.link) router.push(item.link);
  }

  if (items.length === 0) {
    return (
      <p className="px-3.5 py-6 text-center text-[12px] text-muted">
        No notifications yet.
      </p>
    );
  }
  return (
    <ul>
      {items.map((item) => (
        <li key={item.id} className="border-b border-[#f0f1f3] last:border-b-0">
          <button
            type="button"
            onClick={() => void open(item)}
            className={cn(
              "flex w-full gap-2.5 px-3.5 text-left hover:bg-[#f7f9fc]",
              compact ? "py-2.5" : "py-3",
            )}
          >
            <span
              aria-hidden
              className={cn(
                "mt-1.5 size-2 shrink-0 rounded-full",
                item.read ? "bg-transparent" : "bg-brand",
              )}
            />
            <span className="min-w-0">
              <span
                className={cn("block text-[12px]", !item.read && "font-bold")}
              >
                {!item.read && <span className="sr-only">Unread: </span>}
                {item.title}
              </span>
              {item.body && (
                <span className="mt-0.5 block text-[11px] text-muted">
                  {item.body}
                </span>
              )}
              <span className="mt-0.5 block text-[10px] text-[#8a94a3]">
                {formatDateTime(item.created_at)}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
