"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import {
  allowed,
  findModule,
  resolveView,
  viewHref,
  type NavModule,
} from "@/lib/navigation";
import { useViewCounts } from "@/lib/use-view-counts";

const panelClass =
  "flex w-[280px] shrink-0 flex-col border-r border-line bg-white max-[1100px]:w-[230px] max-[760px]:hidden";

export function SecondaryPanel() {
  const pathname = usePathname();
  const navModule = findModule(pathname);
  if (!navModule) return null;
  // `key` resets the filter box when switching modules.
  return <PanelContent key={navModule.key} navModule={navModule} />;
}

function PanelContent({ navModule }: { navModule: NavModule }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const active = resolveView(navModule, searchParams.get("view"));
  // Refreshed on every navigation, so counts follow uploads and claim changes.
  const counts = useViewCounts(
    navModule.key,
    `${pathname}?${searchParams.toString()}`,
  );
  const [filter, setFilter] = useState("");
  const { permissions } = useAuth();
  const views = navModule.views.filter(
    (v) =>
      allowed(v.permission ?? null, permissions) &&
      v.label.toLowerCase().includes(filter.trim().toLowerCase()),
  );

  return (
    <aside aria-label={`${navModule.title} views`} className={panelClass}>
      <div className="flex h-[58px] shrink-0 items-center border-b border-line px-4">
        <h2 className="text-[19px] font-bold">{navModule.title}</h2>
      </div>
      <div className="border-b border-line px-3 py-2.5">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={`Filter ${navModule.title}`}
          aria-label={`Filter ${navModule.title} views`}
          className="w-full rounded-lg border border-line bg-[#fafbfc] px-2.5 py-2 outline-none placeholder:text-muted focus:border-brand"
        />
      </div>
      <p className="px-3.5 pt-3 pb-1.5 text-[10px] font-extrabold tracking-[0.08em] text-[#8a909b] uppercase">
        Views
      </p>
      <ul className="min-h-0 overflow-auto px-2 pb-3.5">
        {views.map((view) => {
          const isActive = view.slug === active.slug;
          const count = counts?.[view.slug] ?? null;
          return (
            <li key={view.slug}>
              <Link
                href={viewHref(navModule, view)}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "my-0.5 flex items-center gap-2.5 rounded-lg px-[9px] py-[9px] text-[#39404c] hover:bg-hover",
                  isActive && "bg-hover font-bold text-selected",
                )}
              >
                <span
                  className={cn(
                    "size-[9px] shrink-0 rounded-full",
                    isActive ? "bg-ok" : "bg-[#a6abb5]",
                  )}
                />
                {view.label}
                {count !== null && (
                  <span className="ml-auto min-w-5 rounded-[10px] bg-[#eceef3] px-1.5 py-0.5 text-center text-[10px] font-normal text-[#596170]">
                    {count}
                  </span>
                )}
              </Link>
            </li>
          );
        })}
        {views.length === 0 && (
          <li className="px-3 py-4 text-muted">No views match “{filter}”.</li>
        )}
      </ul>
    </aside>
  );
}

/** Same footprint as the panel, shown while the URL is read on first load. */
export function SecondaryPanelFallback() {
  return <aside aria-hidden className={panelClass} />;
}
