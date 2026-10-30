"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { StatusPill } from "@/components/data/status-pill";
import { Table, Td, Th } from "@/components/data/table";
import { Button } from "@/components/ui/button";
import { inputClass, selectClass } from "@/components/ui/form";
import { api, type AuditEvent, type AuditPage } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { getModule, resolveView } from "@/lib/navigation";
import type { Tone } from "@/lib/status";

export const ACTIONS: Record<string, { label: string; tone: Tone }> = {
  "auth.login": { label: "Signed in", tone: "ok" },
  "auth.logout": { label: "Signed out", tone: "neutral" },
  "auth.login_denied": { label: "Sign-in refused", tone: "danger" },
  "user.created": { label: "User added", tone: "info" },
  "user.updated": { label: "User changed", tone: "info" },
  "user.deactivated": { label: "User deactivated", tone: "danger" },
  "user.practices_changed": { label: "Practices changed", tone: "info" },
  "user.teams_changed": { label: "Teams changed", tone: "info" },
  "practice.created": { label: "Practice added", tone: "info" },
  "practice.updated": { label: "Practice changed", tone: "info" },
  "team.created": { label: "Team added", tone: "info" },
  "team.updated": { label: "Team changed", tone: "info" },
  "role.permissions_changed": { label: "Permissions changed", tone: "warn" },
  "list.option_added": { label: "Dropdown option added", tone: "info" },
  "list.option_retired": { label: "Dropdown option retired", tone: "warn" },
  "list.option_restored": { label: "Dropdown option restored", tone: "info" },
  "upload.completed": { label: "Sheet uploaded", tone: "ok" },
  "upload.failed": { label: "Upload failed", tone: "danger" },
  "upload.downloaded": { label: "Upload file downloaded", tone: "warn" },
  "claim.imported": { label: "Claim imported", tone: "neutral" },
  "claim.updated": { label: "Claim changed", tone: "info" },
  "claim.assigned": { label: "Claim assigned", tone: "info" },
  "claim.note_added": { label: "Note added", tone: "neutral" },
  "claim.eob_attached": { label: "EOB attached", tone: "info" },
  "claim.eob_downloaded": { label: "EOB opened", tone: "warn" },
  "claim.reviewed": { label: "Claim reviewed", tone: "ok" },
};

/** Which actions each Audit view shows. "admin" covers every change made through the admin screens. */
const VIEW_ACTIONS: Record<string, string[]> = {
  access: ["auth."],
  admin: ["user.", "practice.", "team.", "role.", "list."],
  work: ["upload.", "claim."],
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "none";
  if (Array.isArray(value))
    return value.length === 1 ? "1 item" : `${value.length} items`;
  const text = String(value);
  return UUID.test(text) ? `${text.slice(0, 8)}…` : text;
}

/** One line per changed field, in plain words. IDs are summarised rather than shown. */
function describe(event: AuditEvent): string[] {
  const after = event.after ?? {};
  const before = event.before ?? {};
  return Object.keys(after).map((key) => {
    const label = key
      .replace(/_ids$/, "s")
      .replace(/_user_id$|_id$/, "")
      .replace(/_/g, " ");
    return key in before
      ? `${label}: ${show(before[key])} → ${show(after[key])}`
      : `${label}: ${show(after[key])}`;
  });
}

type Filters = { prefixes: string[]; dateFrom: string; dateTo: string };
type Loaded = {
  key: string;
  events: AuditEvent[];
  nextBefore: number | null;
  error: string | null;
};

/** Fetches one page. Several prefixes (the Admin Changes view) are fetched separately and merged newest-first. */
async function fetchPage(
  filters: Filters,
  before: number | null,
): Promise<{ events: AuditEvent[]; nextBefore: number | null }> {
  const pages = await Promise.all(
    filters.prefixes.map((prefix) => {
      const params = new URLSearchParams({ limit: "50" });
      if (prefix) params.set("action", prefix);
      if (filters.dateFrom) params.set("date_from", filters.dateFrom);
      if (filters.dateTo) params.set("date_to", filters.dateTo);
      if (before) params.set("before_id", String(before));
      return api<AuditPage>(`/audit-events?${params}`);
    }),
  );
  const all = pages.flatMap((p) => p.events).sort((a, b) => b.id - a.id);
  const events = all.slice(0, 50);
  const more = pages.some((p) => p.next_before_id !== null) || all.length > 50;
  return {
    events,
    nextBefore: more && events.length ? events[events.length - 1].id : null,
  };
}

export function AuditLog() {
  const view = resolveView(
    getModule("audit"),
    useSearchParams().get("view"),
  ).slug;
  const [action, setAction] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  // The view picks a set of action prefixes; the dropdown narrows to one action within it.
  const filters: Filters = {
    prefixes: action ? [action] : (VIEW_ACTIONS[view] ?? [""]),
    dateFrom,
    dateTo,
  };
  const key = JSON.stringify(filters);
  const actionOptions = Object.entries(ACTIONS).filter(
    ([name]) =>
      !VIEW_ACTIONS[view] || VIEW_ACTIONS[view].some((p) => name.startsWith(p)),
  );

  useEffect(() => {
    let cancelled = false;
    fetchPage(JSON.parse(key) as Filters, null)
      .then((page) => !cancelled && setLoaded({ key, ...page, error: null }))
      .catch(
        (reason: unknown) =>
          !cancelled &&
          setLoaded({
            key,
            events: [],
            nextBefore: null,
            error:
              reason instanceof Error
                ? reason.message
                : "Could not load the audit log.",
          }),
      );
    return () => {
      cancelled = true;
    };
  }, [key]);

  const current = loaded?.key === key ? loaded : null;
  const loading = current === null || loadingMore;
  const events = current?.events ?? [];
  const error = current?.error ?? null;
  const nextBefore = current?.nextBefore ?? null;

  async function loadOlder() {
    if (!current || nextBefore === null) return;
    setLoadingMore(true);
    try {
      const page = await fetchPage(filters, nextBefore);
      setLoaded({
        ...current,
        events: [...current.events, ...page.events],
        nextBefore: page.nextBefore,
      });
    } catch (reason) {
      setLoaded({
        ...current,
        error:
          reason instanceof Error ? reason.message : "Could not load more.",
      });
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <>
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <label className="text-[11px] text-[#6d7480]">
          <span className="mb-1 block font-semibold">Action</span>
          <select
            className={selectClass}
            value={action}
            onChange={(e) => setAction(e.target.value)}
            aria-label="Filter by action"
          >
            <option value="">All in this view</option>
            {actionOptions.map(([key, meta]) => (
              <option key={key} value={key}>
                {meta.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-[11px] text-[#6d7480]">
          <span className="mb-1 block font-semibold">From</span>
          <input
            type="date"
            className={inputClass}
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
        </label>
        <label className="text-[11px] text-[#6d7480]">
          <span className="mb-1 block font-semibold">To</span>
          <input
            type="date"
            className={inputClass}
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
        </label>
        <p className="ml-auto text-[11px] text-muted">
          Dates are UTC days. Records can’t be edited or deleted.
        </p>
      </div>

      <Panel flush>
        {error ? (
          <EmptyState
            title="The audit log could not be loaded"
            description={error}
          />
        ) : !loading && events.length === 0 ? (
          <EmptyState
            title="No events match"
            description="Try another view, action or date range."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="pl-[15px]">When</Th>
                <Th>Who</Th>
                <Th>What</Th>
                <Th>Item</Th>
                <Th className="pr-[15px]">Details</Th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => {
                const meta = ACTIONS[e.action] ?? {
                  label: e.action,
                  tone: "neutral" as Tone,
                };
                return (
                  <tr key={e.id} className="align-top">
                    <Td className="pl-[15px] whitespace-nowrap">
                      {formatDateTime(e.occurred_at)}
                    </Td>
                    <Td>
                      {e.actor ? (
                        <>
                          <p className="font-semibold">{e.actor.name}</p>
                          <p className="text-muted">{e.actor.email}</p>
                        </>
                      ) : (
                        <span className="text-muted">System / unknown</span>
                      )}
                    </Td>
                    <Td>
                      <StatusPill label={meta.label} tone={meta.tone} />
                    </Td>
                    <Td>
                      <p className="capitalize">{e.entity_type}</p>
                      <p
                        className="font-mono text-[10px] text-muted"
                        title={e.entity_id}
                      >
                        {e.entity_id.length > 24
                          ? `${e.entity_id.slice(0, 8)}…`
                          : e.entity_id}
                      </p>
                    </Td>
                    <Td className="pr-[15px]">
                      {describe(e).map((line) => (
                        <p key={line} className="text-[11px]">
                          {line}
                        </p>
                      ))}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
        {loading && (
          <p
            className={cn(
              "p-4 text-muted",
              events.length > 0 && "border-t border-line",
            )}
          >
            Loading…
          </p>
        )}
      </Panel>
      {nextBefore && !loading && (
        <div className="mt-3 flex justify-center">
          <Button onClick={() => void loadOlder()}>Load older events</Button>
        </div>
      )}
    </>
  );
}
