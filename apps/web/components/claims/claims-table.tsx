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
import { api, type ClaimPage, type Lists } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDate, formatMoney } from "@/lib/format";
import { getModule, resolveView } from "@/lib/navigation";
import { claimStatusTone } from "@/lib/status";
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
  const lists = useApi<Lists>("/lists");

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
  }, [path]);

  const current = result?.path === path ? result : null;
  const page = current?.page;

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
                <Th className="pl-[15px]">Claim</Th>
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
                  className="cursor-pointer hover:bg-[#fafbfc]"
                  onClick={() => router.push(`/claims/${c.id}`)}
                >
                  <Td className="pl-[15px] font-bold whitespace-nowrap">
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
