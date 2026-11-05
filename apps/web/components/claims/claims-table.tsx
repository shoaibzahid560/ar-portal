"use client";

import { AlertTriangle } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { StatusPill } from "@/components/data/status-pill";
import { Table, Td, Th } from "@/components/data/table";
import { Button } from "@/components/ui/button";
import { inputClass, selectClass } from "@/components/ui/form";
import {
  api,
  type Assignee,
  type ClaimListItem,
  type Priority,
  type ClaimPage,
  type Lists,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { formatDate, formatMoney } from "@/lib/format";
import { getModule, resolveView } from "@/lib/navigation";
import { claimStatusTone, PRIORITIES, WORK_STATES } from "@/lib/status";
import { useApi } from "@/lib/use-api";

const PAGE_SIZE = 100;

/**
 * The claims list, used by both the Claims and Follow-ups screens. The view comes from the URL
 * (?view=overdue), so every list can be bookmarked and the back button works.
 */
export function ClaimsTable({
  moduleKey,
}: {
  moduleKey: "claims" | "followups";
}) {
  const router = useRouter();
  const params = useSearchParams();
  const view = resolveView(getModule(moduleKey), params.get("view")).slug;
  const uploadId = params.get("upload");
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [submitted, setSubmitted] = useState(params.get("q") ?? "");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const lists = useApi<Lists>("/lists");
  const { permissions } = useAuth();
  const canAssign = permissions.includes("claims.assign");
  const canPrioritize = permissions.includes("claims.prioritize");
  // Rows can be selected for any bulk action the person may take.
  const canSelect = canAssign || canPrioritize;

  const search = new URLSearchParams({
    view,
    limit: String(PAGE_SIZE),
    offset: String(offset),
  });
  if (submitted) search.set("q", submitted);
  if (status) search.set("claim_status", status);
  if (uploadId) search.set("upload_id", uploadId);
  const path = `/claims?${search}`;

  const [result, setResult] = useState<{
    path: string;
    page: ClaimPage | null;
    error: string | null;
  } | null>(null);
  useEffect(() => {
    let cancelled = false;
    api<ClaimPage>(path)
      .then((page) => !cancelled && setResult({ path, page, error: null }))
      .catch(
        (e: unknown) =>
          !cancelled &&
          setResult({
            path,
            page: null,
            error: e instanceof Error ? e.message : "Could not load claims.",
          }),
      );
    return () => {
      cancelled = true;
    };
  }, [path, refresh]); // refresh: reload after a bulk assignment

  const current = result?.path === path ? result : null;
  const page = current?.page;
  // Selection belongs to the list on screen; it clears when the list changes.
  const visibleIds = new Set(page?.claims.map((c) => c.id) ?? []);
  const chosen = selected.filter((id) => visibleIds.has(id));
  const toggle = (id: string) =>
    setSelected((s) =>
      s.includes(id) ? s.filter((x) => x !== id) : [...s, id],
    );
  const allChosen =
    page !== undefined &&
    page !== null &&
    page.claims.length > 0 &&
    chosen.length === page.claims.length;

  return (
    <>
      <form
        className="mb-3 flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setOffset(0);
          setSubmitted(query.trim());
        }}
      >
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search patient, subscriber ID, payer or claim number..."
          aria-label="Search claims"
          className={cn(inputClass, "min-w-[300px]")}
        />
        <select
          value={status}
          onChange={(e) => {
            setOffset(0);
            setStatus(e.target.value);
          }}
          aria-label="Claim status"
          className={selectClass}
        >
          <option value="">All claim statuses</option>
          <option value="__none__">No status yet</option>
          {(lists.data?.claim_status ?? []).map((o) => (
            <option key={o.id} value={o.value}>
              {o.value}
            </option>
          ))}
        </select>
        <Button type="submit">Search</Button>
        {(submitted || status || uploadId) && (
          <Button
            type="button"
            onClick={() => {
              setQuery("");
              setSubmitted("");
              setStatus("");
              setOffset(0);
              router.replace(`/${moduleKey}?view=${view}`);
            }}
          >
            Clear
          </Button>
        )}
        {uploadId && (
          <span className="text-[12px] text-muted">
            Showing claims created by one upload.
          </span>
        )}
      </form>

      {notice && (
        <p
          role="status"
          className="mb-3 rounded-[9px] bg-ok-soft px-3 py-2.5 text-[12px] text-ok-ink"
        >
          {notice}
        </p>
      )}
      {canSelect && page && chosen.length > 0 && (
        <BulkAssignBar
          canAssign={canAssign}
          canPrioritize={canPrioritize}
          claims={page.claims.filter((c) => chosen.includes(c.id))}
          onClear={() => setSelected([])}
          onDone={(message) => {
            setSelected([]);
            setNotice(message);
            setRefresh((r) => r + 1);
          }}
        />
      )}

      <Panel flush>
        {current?.error ? (
          <EmptyState
            title="Claims could not be loaded"
            description={current.error}
          />
        ) : !page ? (
          <p className="p-6 text-muted">Loading claims…</p>
        ) : page.claims.length === 0 ? (
          <EmptyState
            title="No claims in this view"
            description="Claims appear here once an AR sheet is uploaded and, for associates, once a claim is assigned to you."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                {canSelect && (
                  <Th className="w-8 pl-[15px]">
                    <input
                      type="checkbox"
                      aria-label="Select every claim on this page"
                      checked={allChosen}
                      onChange={() =>
                        setSelected(
                          allChosen ? [] : page.claims.map((c) => c.id),
                        )
                      }
                      className="size-4 accent-brand"
                    />
                  </Th>
                )}
                <Th className={canSelect ? "" : "pl-[15px]"}>Claim</Th>
                <Th>Patient</Th>
                <Th>Practice</Th>
                <Th>Insurance carrier</Th>
                <Th>Service date</Th>
                <Th className="text-right">Billed</Th>
                <Th>Aging</Th>
                <Th>Claim status</Th>
                <Th>Follow-up</Th>
                <Th className="pr-[15px]">Assigned to</Th>
              </tr>
            </thead>
            <tbody>
              {page.claims.map((c) => (
                <tr
                  key={c.id}
                  className={cn(
                    "cursor-pointer hover:bg-[#fafbfc]",
                    chosen.includes(c.id) && "bg-brand-soft/40",
                  )}
                  onClick={() => router.push(`/claims/${c.id}`)}
                >
                  {canSelect && (
                    <Td
                      className="pl-[15px]"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        aria-label={`Select ${c.number}`}
                        checked={chosen.includes(c.id)}
                        onChange={() => toggle(c.id)}
                        className="size-4 accent-brand"
                      />
                    </Td>
                  )}
                  <Td
                    className={cn(
                      "font-bold whitespace-nowrap",
                      !canSelect && "pl-[15px]",
                    )}
                  >
                    <Link
                      href={`/claims/${c.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="hover:text-brand"
                    >
                      {c.number}
                    </Link>
                    {c.needs_review && (
                      <span
                        title="Needs review"
                        className="ml-1 inline-flex align-[-2px] text-warn"
                      >
                        <AlertTriangle size={13} aria-label="Needs review" />
                      </span>
                    )}
                    {(c.priority === "high" || c.priority === "urgent") && (
                      <span className="ml-1.5">
                        <StatusPill
                          label={PRIORITIES[c.priority].label}
                          tone={PRIORITIES[c.priority].tone}
                        />
                      </span>
                    )}
                  </Td>
                  <Td>{c.patient_name}</Td>
                  <Td>{c.practice.name}</Td>
                  <Td className="max-w-[220px] truncate">
                    {c.insurance_carrier}
                  </Td>
                  <Td className="whitespace-nowrap">
                    {formatDate(c.service_date)}
                  </Td>
                  <Td className="text-right">{formatMoney(c.billed)}</Td>
                  <Td className="whitespace-nowrap">{c.aging_bucket}</Td>
                  <Td>
                    <StatusPill
                      label={c.claim_status ?? "No status"}
                      tone={claimStatusTone(c.claim_status)}
                    />
                    {c.work_state !== "open" && (
                      <span className="ml-1">
                        <StatusPill
                          label={WORK_STATES[c.work_state].label}
                          tone={WORK_STATES[c.work_state].tone}
                        />
                      </span>
                    )}
                    {c.work_state === "open" && c.returned && (
                      <span className="ml-1">
                        <StatusPill label="Returned" tone="danger" />
                      </span>
                    )}
                  </Td>
                  <Td className="whitespace-nowrap">
                    {formatDate(c.followup_date)}
                  </Td>
                  <Td
                    className={cn("pr-[15px]", !c.assigned_to && "text-muted")}
                  >
                    {c.assigned_to?.name ?? "Unassigned"}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      {page && page.total > 0 && (
        <div className="mt-2 flex items-center gap-2 text-[11px] text-muted">
          <span>
            {offset + 1}–{offset + page.claims.length} of {page.total} claims
          </span>
          <span className="ml-auto flex gap-2">
            <Button
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </Button>
            <Button
              type="button"
              disabled={offset + PAGE_SIZE >= page.total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </Button>
          </span>
        </div>
      )}
    </>
  );
}

/** Shown while claims are ticked: assign them all to one person in a single step. */
function BulkAssignBar({
  canAssign,
  canPrioritize,
  claims,
  onClear,
  onDone,
}: {
  canAssign: boolean;
  canPrioritize: boolean;
  claims: ClaimListItem[];
  onClear: () => void;
  onDone: (message: string) => void;
}) {
  const practiceIds = [...new Set(claims.map((c) => c.practice.id))].sort();
  const people = useApi<Assignee[]>(
    canAssign
      ? `/claims/assignees?${practiceIds.map((id) => `practice_id=${id}`).join("&")}`
      : null,
  );
  const [priority, setPriority] = useState("");

  async function prioritize() {
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ updated: number }>("/claims/bulk-priority", {
        method: "POST",
        body: { claim_ids: claims.map((c) => c.id), priority },
      });
      onDone(
        `${result.updated} claim(s) set to ${PRIORITIES[priority as Priority].label} priority.`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }
  const [assignee, setAssignee] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function assign() {
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ updated: number }>("/claims/bulk-assign", {
        method: "POST",
        body: {
          claim_ids: claims.map((c) => c.id),
          assigned_user_id: assignee === "none" ? null : assignee,
        },
      });
      const who =
        assignee === "none"
          ? "nobody (unassigned)"
          : people.data?.find((p) => p.id === assignee)?.name;
      onDone(
        `${result.updated} claim(s) assigned to ${who}.${result.updated < claims.length ? " The rest already were." : ""}`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not assign.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-3 rounded-[9px] border border-brand bg-brand-soft/40 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[12px] font-bold">{claims.length} selected</span>
        {canAssign && (
          <>
            <span className="text-[12px] text-muted">Assign to</span>
            <select
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
              aria-label="Assign the selected claims to"
              className={selectClass}
              disabled={busy}
            >
              <option value="">Choose a person…</option>
              {(people.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.role})
                </option>
              ))}
              <option value="none">Nobody (unassign)</option>
            </select>
            <Button
              variant="primary"
              onClick={() => void assign()}
              disabled={busy || !assignee}
            >
              {busy ? "Assigning…" : "Assign"}
            </Button>
          </>
        )}
        {canPrioritize && (
          <>
            <span className="text-[12px] text-muted">Priority</span>
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              aria-label="Set the priority of the selected claims"
              className={selectClass}
              disabled={busy}
            >
              <option value="">Choose…</option>
              {Object.entries(PRIORITIES).map(([key, p]) => (
                <option key={key} value={key}>
                  {p.label}
                </option>
              ))}
            </select>
            <Button
              onClick={() => void prioritize()}
              disabled={busy || !priority}
            >
              Set priority
            </Button>
          </>
        )}
        <Button onClick={onClear} disabled={busy}>
          Clear selection
        </Button>
        {practiceIds.length > 1 && (
          <span className="text-[11px] text-muted">
            Only people who work in all {practiceIds.length} selected practices
            are listed.
          </span>
        )}
      </div>
      {error && (
        <p role="alert" className="mt-2 text-[12px] text-danger-ink">
          {error}
        </p>
      )}
      {people.error && (
        <p role="alert" className="mt-2 text-[12px] text-danger-ink">
          {people.error}
        </p>
      )}
    </div>
  );
}
