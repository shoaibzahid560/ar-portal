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

export type NavView = { slug: string; label: string };

export type NavModule = {
  key: string;
  /** Short label under the rail icon */
  label: string;
  /** Heading of the secondary panel */
  title: string;
  href: string;
  icon: LucideIcon;
  /** Permission needed to see this module. The rail is filtered by /api/auth/me in M0. */
  permission: string;
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
    permission: "uploads.view",
    placement: "main",
    views: [
      { slug: "all", label: "All Uploads" },
      { slug: "processing", label: "Processing" },
      { slug: "needs-review", label: "Needs Review" },
      { slug: "failed", label: "Failed" },
    ],
  },
  {
    key: "review",
    label: "Review",
    title: "Review Queue",
    href: "/review",
    icon: GitCompareArrows,
    permission: "reconciliation.review",
    placement: "main",
    views: [
      { slug: "ambiguous", label: "Ambiguous Matches" },
      { slug: "conflicts", label: "Conflicts" },
    ],
  },
  {
    key: "claims",
    label: "Claims",
    title: "Claims",
    href: "/claims",
    icon: FileText,
    permission: "claims.view",
    placement: "main",
    views: [
      { slug: "all", label: "All Claims" },
      { slug: "mine", label: "My Claims" },
      { slug: "unassigned", label: "Unassigned" },
      { slug: "followup-due", label: "Follow-up Due" },
      { slug: "overdue", label: "Overdue" },
      { slug: "returned", label: "Returned" },
      { slug: "pending-review", label: "Pending Review" },
      { slug: "closed", label: "Closed" },
    ],
  },
  {
    key: "followups",
    label: "Follow-ups",
    title: "Follow-ups",
    href: "/followups",
    icon: CalendarClock,
    permission: "claims.view",
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
    permission: "reports.view",
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
    views: [
      { slug: "claim-timelines", label: "Claim Timelines" },
      { slug: "field-changes", label: "Field Changes" },
      { slug: "access", label: "Access" },
      { slug: "exports", label: "Exports" },
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
      { slug: "general", label: "General" },
      { slug: "security", label: "Security" },
      { slug: "retention", label: "Retention" },
    ],
  },
];

export function findModule(pathname: string): NavModule | undefined {
  return NAV_MODULES.find((m) => pathname === m.href || pathname.startsWith(`${m.href}/`));
}

export function getModule(key: string): NavModule {
  const found = NAV_MODULES.find((m) => m.key === key);
  if (!found) throw new Error(`Unknown module: ${key}`);
  return found;
}

/** Resolves ?view= to a known view, falling back to the module's default view. */
export function resolveView(module: NavModule, slug: string | null | undefined): NavView {
  return module.views.find((v) => v.slug === slug) ?? module.views[0];
}

export function viewHref(module: NavModule, view: NavView): string {
  return view.slug === module.views[0].slug ? module.href : `${module.href}?view=${view.slug}`;
}
