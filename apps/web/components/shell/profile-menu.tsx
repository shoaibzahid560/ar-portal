"use client";

import { useCallback, useRef, useState } from "react";
import { signOut, useAuth } from "@/lib/auth";
import { useClickOutside } from "./use-click-outside";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export function ProfileMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useClickOutside(ref, close, open);

  const { user, role } = useAuth();

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="Account menu"
        className="flex size-9 items-center justify-center rounded-full bg-[#d84c54] text-[13px] font-extrabold text-white"
      >
        {initials(user.full_name)}
      </button>

      {open && (
        <div className="absolute top-[46px] right-0 z-50 w-[280px] rounded-[14px] border border-[#dfe4ea] bg-white p-2 text-ink shadow-[0_18px_45px_rgba(10,30,55,0.18)]">
          <div className="mb-1.5 border-b border-[#edf0f4] px-3 pt-3 pb-2.5">
            <p className="font-extrabold text-navy">{user.full_name}</p>
            <p className="mt-0.5 text-[12px] break-all text-[#6b7280]">{user.email}</p>
            <p className="mt-1.5 text-[11px] text-[#8a94a3]">{role.name}</p>
          </div>
          <button type="button" className="w-full rounded-[9px] px-3 py-2.5 text-left text-[#243244] hover:bg-[#f3f6fa]">
            My profile
          </button>
          <div className="my-1 h-px bg-[#edf0f4]" />
          <button
            type="button"
            onClick={() => void signOut()}
            className="w-full rounded-[9px] px-3 py-2.5 text-left text-[#b4232d] hover:bg-[#f3f6fa]"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
