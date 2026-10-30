"use client";

import { useEffect, useState } from "react";
import { api } from "./api";
import { useAuth } from "./auth";

/** Which API answers the badge counts for each module's views, and the permission it needs. */
const SOURCES: Record<string, { path: string; permission: string }> = {
  claims: { path: "/claims/counts", permission: "claims.view" },
  followups: { path: "/claims/counts", permission: "claims.view" },
  uploads: { path: "/uploads/counts", permission: "uploads.view" },
};

/**
 * Badge counts for the secondary panel. `refreshKey` changes whenever the person navigates,
 * so counts stay current after uploads and claim changes.
 */
export function useViewCounts(
  moduleKey: string,
  refreshKey: string,
): Record<string, number> | null {
  const { permissions } = useAuth();
  const source = SOURCES[moduleKey];
  const allowed =
    source !== undefined && permissions.includes(source.permission);
  const [counts, setCounts] = useState<{
    key: string;
    values: Record<string, number>;
  } | null>(null);

  useEffect(() => {
    if (!allowed) return;
    let cancelled = false;
    api<Record<string, number>>(source.path)
      .then((values) => !cancelled && setCounts({ key: moduleKey, values }))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [allowed, source, moduleKey, refreshKey]);

  return allowed && counts?.key === moduleKey ? counts.values : null;
}
