"use client";

import { useEffect, useState } from "react";
import { api } from "./api";
import { useAuth } from "./auth";
import { allowed } from "./navigation";

/** Which API answers the badge counts for each module's views, and the permission it needs. */
const CLAIM_VIEWERS = [
  "claims.view",
  "claims.view_team",
  "claims.view_practice",
];
const SOURCES: Record<string, { path: string; permission: string | string[] }> =
  {
    claims: { path: "/claims/counts", permission: CLAIM_VIEWERS },
    followups: { path: "/claims/counts", permission: CLAIM_VIEWERS },
    review: { path: "/claims/counts", permission: "claims.review" },
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
  const permitted =
    source !== undefined && allowed(source.permission, permissions);
  const [counts, setCounts] = useState<{
    key: string;
    values: Record<string, number>;
  } | null>(null);

  useEffect(() => {
    if (!permitted) return;
    let cancelled = false;
    api<Record<string, number>>(source.path)
      .then((values) => !cancelled && setCounts({ key: moduleKey, values }))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [permitted, source, moduleKey, refreshKey]);

  return permitted && counts?.key === moduleKey ? counts.values : null;
}
