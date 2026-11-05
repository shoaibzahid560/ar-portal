import {
  BarChart3,
  Building2,
  CalendarClock,
  FileText,
  GitCompareArrows,
  LayoutDashboard,
  Settings,
  ShieldCheck,
  Upload,
  Users,
  type LucideIcon,
} from "lucide-react";

/** A saved view in the side panel. With `permission`, it's shown only to people holding it. */
export type NavView = {
  slug: string;
  label: string;
  permission?: string | string[];
};

/** Any of these lets a person see claims (their own, their teams', or their practices'). */
const CLAIM_VIEWERS = [
  "claims.view",
  "claims.view_team",
  "claims.view_practice",
];

/** True if the person holds the permission, or any one of a list of permissions. */
export function allowed(
  permission: string | string[] | null,
  held: string[],
): boolean {
  if (permission === null) return true;
  return (Array.isArray(permission) ? permission : [permission]).some((p) =>
    held.includes(p),
  );
}

export type NavModule = {
  key: string;
  /** Short label under the rail icon */
  label: string;
  /** Heading of the secondary panel */
  title: string;
  href: string;
  icon: LucideIcon;
  /**
   * Permission needed to see this module. null means visible to everyone until the module that
   * builds it adds its permission (review in M2, reports in M6).
   */
  permission: string | string[] | null;
  placement: "main" | "admin";
  views: NavView[];
};

/**
 * Single source of truth for the rail and the secondary panel.
 * The first view of each module is its default (no ?view= in the URL).
 */
export const NAV_MODULES: NavModule[] = [
  {
    key: "dashboard",
    label: "Dashboard",
    title: "Dashboard",
    href: "/dashboard",
    icon: LayoutDashboard,
    permission: "dashboard.view",
    placement: "main",
    views: [
      { slug: "overview", label: "Overview" },
      { slug: "exceptions", label: "Exceptions" },
      { slug: "today", label: "Today" },
      { slug: "this-week", label: "This Week" },
    ],
  },
  {
    key: "uploads",
    label: "Uploads",
    title: "Uploads",
    href: "/uploads",
    icon: Upload,
    permission: ["uploads.view", "uploads.create"],
    placement: "main",
    views: [
      { slug: "all", label: "All Uploads" },
      { slug: "awaiting", label: "Waiting for Approval" },
      { slug: "previews", label: "Previews" },
      { slug: "with-errors", label: "With Errors" },
      { slug: "failed", label: "Failed" },
      { slug: "reversed", label: "Reversed" },
    ],
  },
  {
    key: "review",
    label: "Review",
    title: "Review Queue",
    href: "/review",
    icon: GitCompareArrows,
    permission: "claims.review",
    placement: "main",
    views: [
      { slug: "open", label: "Needs Review" },
      { slug: "merged", label: "Merged Lines" },
    ],
  },
  {
    key: "claims",
    label: "Claims",
    title: "Claims",
    href: "/claims",
    icon: FileText,
    permission: CLAIM_VIEWERS,
    placement: "main",
    views: [
      { slug: "all", label: "All Claims" },
      { slug: "mine", label: "My Claims" },
      { slug: "unassigned", label: "Unassigned" },
      { slug: "due-today", label: "Follow-up Due" },
      { slug: "overdue", label: "Overdue" },
      { slug: "high-priority", label: "High Priority" },
      { slug: "awaiting-completion", label: "Awaiting Completion" },
      { slug: "returned", label: "Returned" },
      { slug: "needs-review", label: "Needs Review" },
      { slug: "closed", label: "Closed" },
    ],
  },
  {
    key: "followups",
    label: "Follow-ups",
    title: "Follow-ups",
    href: "/followups",
    icon: CalendarClock,
    permission: CLAIM_VIEWERS,
    placement: "main",
    views: [
      { slug: "due-today", label: "Due Today" },
      { slug: "tomorrow", label: "Tomorrow" },
      { slug: "overdue", label: "Overdue" },
    ],
  },
  {
    key: "reports",
    label: "Reports",
    title: "Reports",
    href: "/reports",
    icon: BarChart3,
    permission: null,
    placement: "main",
    views: [
      { slug: "performance", label: "Performance" },
      { slug: "data-quality", label: "Uploads & Data Quality" },
      { slug: "exports", label: "Exports" },
    ],
  },
  {
    key: "audit",
    label: "Audit",
    title: "Audit",
    href: "/audit",
    icon: ShieldCheck,
    permission: "audit.view",
    placement: "main",
    // Each claim's own timeline is on the claim screen. Export logs are added with reports (M6).
    views: [
      { slug: "all", label: "All Events" },
      { slug: "work", label: "Uploads & Claims" },
      { slug: "access", label: "Sign-ins & Refusals" },
      { slug: "admin", label: "Admin Changes" },
    ],
  },
  {
    key: "users",
    label: "Users",
    title: "Users",
    href: "/admin/users",
    icon: Users,
    permission: "users.view",
    placement: "admin",
    views: [
      { slug: "all", label: "All Users" },
      { slug: "active", label: "Active" },
      { slug: "paused", label: "Paused" },
      { slug: "deactivated", label: "Deactivated" },
      {
        slug: "grants",
        label: "Access Grants",
        permission: ["grants.manage", "grants.approve"],
      },
    ],
  },
  {
    key: "practices",
    label: "Practices",
    title: "Practices",
    href: "/admin/practices",
    icon: Building2,
    permission: "practices.view",
    placement: "admin",
    views: [
      { slug: "all", label: "All Practices" },
      { slug: "active", label: "Active" },
      { slug: "paused", label: "Paused" },
      { slug: "teams", label: "Teams" },
    ],
  },
  {
    key: "settings",
    label: "Settings",
    title: "Settings",
    href: "/admin/settings",
    icon: Settings,
    permission: "settings.manage",
    placement: "admin",
    views: [
      { slug: "roles", label: "Roles & Permissions" },
      { slug: "lists", label: "Dropdown Lists" },
      { slug: "general", label: "General" },
    ],
  },
];

export function findModule(pathname: string): NavModule | undefined {
  return NAV_MODULES.find(
    (m) => pathname === m.href || pathname.startsWith(`${m.href}/`),
  );
}

export function getModule(key: string): NavModule {
  const found = NAV_MODULES.find((m) => m.key === key);
  if (!found) throw new Error(`Unknown module: ${key}`);
  return found;
}

/** Resolves ?view= to a known view, falling back to the module's default view. */
export function resolveView(
  module: NavModule,
  slug: string | null | undefined,
): NavView {
  return module.views.find((v) => v.slug === slug) ?? module.views[0];
}

export function viewHref(module: NavModule, view: NavView): string {
  return view.slug === module.views[0].slug
    ? module.href
    : `${module.href}?view=${view.slug}`;
}
