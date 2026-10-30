"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { NAV_MODULES, type NavModule } from "@/lib/navigation";

function RailLink({
  navModule,
  active,
}: {
  navModule: NavModule;
  active: boolean;
}) {
  const Icon = navModule.icon;
  return (
    <Link
      href={navModule.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex min-h-[58px] w-[68px] flex-col items-center justify-center gap-1 rounded-lg px-0.5 py-2 text-center text-[10px] leading-tight max-[760px]:w-[58px]",
        active
          ? "bg-brand-soft font-bold text-navy"
          : "text-[#555d6b] hover:bg-hover",
      )}
    >
      <Icon size={22} strokeWidth={1.75} aria-hidden />
      {navModule.label}
    </Link>
  );
}

export function NavRail() {
  const pathname = usePathname();
  const { permissions } = useAuth();
  const isActive = (m: NavModule) =>
    pathname === m.href || pathname.startsWith(`${m.href}/`);

  // Only what the signed-in person's role allows. The API enforces the same rules on every request.
  const visible = NAV_MODULES.filter(
    (m) => m.permission === null || permissions.includes(m.permission),
  );
  const main = visible.filter((m) => m.placement === "main");
  const admin = visible.filter((m) => m.placement === "admin");

  return (
    <nav
      aria-label="Main"
      className="flex w-[76px] shrink-0 flex-col items-center gap-0.5 overflow-y-auto border-r border-line bg-rail py-2 max-[760px]:w-16"
    >
      {main.map((m) => (
        <RailLink key={m.key} navModule={m} active={isActive(m)} />
      ))}
      <div className="min-h-4 flex-1" />
      {admin.map((m) => (
        <RailLink key={m.key} navModule={m} active={isActive(m)} />
      ))}
    </nav>
  );
}
