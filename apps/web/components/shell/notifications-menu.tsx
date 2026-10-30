"use client";

import { Bell } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { useClickOutside } from "./use-click-outside";

/** The notification centre is built in M5. Until then the bell explains what will appear here. */
export function NotificationsMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useClickOutside(ref, close, open);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="Notifications"
        className="relative flex size-9 items-center justify-center rounded-full bg-white text-navy"
      >
        <Bell size={17} strokeWidth={2} />
      </button>

      {open && (
        <div className="absolute top-12 right-0 z-50 w-[320px] max-w-[calc(100vw-24px)] overflow-hidden rounded-[10px] border border-line bg-white text-ink shadow-[0_18px_50px_rgba(0,0,0,0.18)]">
          <p className="border-b border-line px-3.5 py-3 font-bold">
            Notifications
          </p>
          <p className="px-3.5 py-6 text-center text-[12px] text-muted">
            Notifications for new assignments, due follow-ups and upload
            problems arrive in a later update.
          </p>
        </div>
      )}
    </div>
  );
}
