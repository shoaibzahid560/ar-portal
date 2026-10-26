"use client";

import { Bell } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { SAMPLE_NOTIFICATIONS } from "@/lib/sample-data";
import { useClickOutside } from "./use-click-outside";

export function NotificationsMenu() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState(SAMPLE_NOTIFICATIONS);
  const ref = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useClickOutside(ref, close, open);

  const unread = items.filter((n) => n.unread).length;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        className="relative flex size-9 items-center justify-center rounded-full bg-white text-navy"
      >
        <Bell size={17} strokeWidth={2} />
        {unread > 0 && (
          <span className="absolute -top-1 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#d64545] px-1 text-[9px] font-bold text-white">
            {unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute top-12 right-0 z-50 w-[360px] max-w-[calc(100vw-24px)] overflow-hidden rounded-[10px] border border-line bg-white text-ink shadow-[0_18px_50px_rgba(0,0,0,0.18)]">
          <div className="flex items-center justify-between border-b border-line px-3.5 py-3">
            <p className="font-bold">Notifications</p>
            <button
              type="button"
              onClick={() => setItems((all) => all.map((n) => ({ ...n, unread: false })))}
              className="rounded-[7px] border border-line px-2.5 py-1.5 text-[12px] font-semibold text-[#3d4450] hover:bg-[#f7f8fa]"
            >
              Mark all read
            </button>
          </div>
          <ul className="max-h-[420px] overflow-auto">
            {items.map((n) => (
              <li key={n.id} className={cn("border-b border-[#edf0f4] px-3.5 py-2.5 last:border-b-0", n.unread && "bg-[#eef7ff]")}>
                <p className="text-[12px] font-bold">{n.title}</p>
                <p className="mt-0.5 text-[11px] text-[#68707c]">{n.message}</p>
                <p className="mt-0.5 text-[11px] text-[#68707c]">{n.when}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
