"use client";

import { ChevronLeft, ChevronRight, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { APP_MONOGRAM, APP_NAME } from "@/lib/config";
import { NotificationsMenu } from "./notifications-menu";
import { ProfileMenu } from "./profile-menu";

const roundButton =
  "flex size-[34px] items-center justify-center rounded-full bg-white/12 text-white hover:bg-white/20";

export function TopBar() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const q = query.trim();
    if (q) router.push(`/claims?q=${encodeURIComponent(q)}`);
  }

  return (
    <header className="flex h-16 shrink-0 items-center gap-3.5 bg-linear-to-r from-navy to-navy-2 px-3.5 text-white">
      <Link
        href="/dashboard"
        className="flex items-center gap-2.5 text-[18px] font-bold tracking-[-0.2px] whitespace-nowrap"
      >
        <span className="flex size-10 items-center justify-center rounded-[9px] bg-white text-[15px] font-extrabold text-navy shadow-[0_2px_8px_rgba(0,0,0,0.22)]">
          {APP_MONOGRAM}
        </span>
        <span className="max-[760px]:hidden">{APP_NAME}</span>
      </Link>

      <div className="flex gap-1.5 max-[560px]:hidden">
        <button
          type="button"
          onClick={() => router.back()}
          aria-label="Go back"
          className={roundButton}
        >
          <ChevronLeft size={18} />
        </button>
        <button
          type="button"
          onClick={() => router.forward()}
          aria-label="Go forward"
          className={roundButton}
        >
          <ChevronRight size={18} />
        </button>
      </div>

      <form
        role="search"
        onSubmit={handleSearch}
        className="flex h-9 max-w-[470px] min-w-0 flex-1 items-center gap-2 rounded-full bg-white/14 px-3.5"
      >
        <Search size={14} className="shrink-0 text-white/70" aria-hidden />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search claims, patients, payers, practices..."
          aria-label="Search claims"
          className="w-full min-w-0 bg-transparent text-white outline-none placeholder:text-white/70"
        />
      </form>

      <div className="ml-auto flex items-center gap-2">
        <NotificationsMenu />
        <Link
          href="/uploads"
          aria-label="New upload"
          title="New upload"
          className="flex size-9 items-center justify-center rounded-full bg-white text-navy max-[560px]:hidden"
        >
          <Plus size={18} />
        </Link>
        <ProfileMenu />
      </div>
    </header>
  );
}
