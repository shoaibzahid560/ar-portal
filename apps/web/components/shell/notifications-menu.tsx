"use client";

import { Bell } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { NotificationList } from "@/components/notifications/notification-list";
import { api, type NotificationPage } from "@/lib/api";
import { useClickOutside } from "./use-click-outside";

const POLL_MS = 60_000;

/** The bell: unread count, checked every minute and on every page change, and the latest notifications. */
export function NotificationsMenu() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [page, setPage] = useState<NotificationPage | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useClickOutside(ref, close, open);

  const refreshCount = useCallback(() => {
    api<{ unread: number }>("/notifications/unread-count")
      .then((r) => setUnread(r.unread))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    refreshCount();
    const timer = window.setInterval(refreshCount, POLL_MS);
    return () => window.clearInterval(timer);
  }, [refreshCount, pathname]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    api<NotificationPage>("/notifications?limit=20")
      .then((p) => {
        if (cancelled) return;
        setPage(p);
        setUnread(p.unread);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [open]);

  async function markAll() {
    await api("/notifications/read-all", { method: "POST" }).catch(
      () => undefined,
    );
    setUnread(0);
    setPage((p) =>
      p ? { unread: 0, items: p.items.map((i) => ({ ...i, read: true })) } : p,
    );
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={
          unread ? `Notifications, ${unread} unread` : "Notifications"
        }
        className="relative flex size-9 items-center justify-center rounded-full bg-white text-navy"
      >
        <Bell size={17} strokeWidth={2} />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-full border-2 border-navy bg-danger px-1 text-[10px] font-extrabold text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute top-12 right-0 z-50 w-[360px] max-w-[calc(100vw-24px)] overflow-hidden rounded-[10px] border border-line bg-white text-ink shadow-[0_18px_50px_rgba(0,0,0,0.18)]">
          <div className="flex items-center gap-2 border-b border-line px-3.5 py-3">
            <p className="font-bold">Notifications</p>
            {unread > 0 && (
              <button
                type="button"
                onClick={() => void markAll()}
                className="ml-auto text-[11px] font-semibold text-brand"
              >
                Mark all as read
              </button>
            )}
          </div>
          <div className="max-h-[420px] overflow-auto">
            {page ? (
              <NotificationList
                items={page.items}
                compact
                onOpened={() => {
                  close();
                  refreshCount();
                }}
              />
            ) : (
              <p className="px-3.5 py-6 text-center text-[12px] text-muted">
                Loading…
              </p>
            )}
          </div>
          <Link
            href="/notifications"
            onClick={close}
            className="block border-t border-line px-3.5 py-2.5 text-center text-[12px] font-semibold text-brand"
          >
            See all notifications
          </Link>
        </div>
      )}
    </div>
  );
}
