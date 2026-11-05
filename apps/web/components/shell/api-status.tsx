"use client";

import { useEffect, useState } from "react";
import { StatusPill } from "@/components/data/status-pill";
import type { Tone } from "@/lib/status";

type Health = {
  status: "ok";
  database: "ok" | "unavailable" | "not_configured" | "needs_update";
};

type State =
  { kind: "checking" } | { kind: "down" } | { kind: "up"; health: Health };

function describe(state: State): { label: string; tone: Tone } {
  if (state.kind === "checking")
    return { label: "Checking API…", tone: "neutral" };
  if (state.kind === "down")
    return { label: "API not reachable", tone: "danger" };
  switch (state.health.database) {
    case "ok":
      return { label: "API and database connected", tone: "ok" };
    case "not_configured":
      return { label: "API connected, no database yet", tone: "info" };
    case "needs_update":
      return {
        label: "Database needs updating: run alembic upgrade head",
        tone: "danger",
      };
    default:
      return { label: "API connected, database unavailable", tone: "warn" };
  }
}

/**
 * Calls GET /api/health through the Next.js rewrite to prove web -> API -> database works.
 * Shown on the dashboard during M0; it moves to Admin › Settings once sign-in exists.
 */
export function ApiStatus() {
  const [state, setState] = useState<State>({ kind: "checking" });

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/health", { signal: controller.signal, cache: "no-store" })
      .then((response) =>
        response.ok
          ? response.json()
          : Promise.reject(new Error(String(response.status))),
      )
      .then((health: Health) => setState({ kind: "up", health }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: "down" });
      });
    return () => controller.abort();
  }, []);

  const { label, tone } = describe(state);
  return (
    <span role="status" className="flex items-center">
      <StatusPill label={label} tone={tone} />
    </span>
  );
}
