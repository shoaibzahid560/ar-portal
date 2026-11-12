"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { StatusPill } from "@/components/data/status-pill";
import { Table, Td, Th } from "@/components/data/table";
import { Button } from "@/components/ui/button";
import {
  Field,
  FormError,
  inputClass,
  selectClass,
} from "@/components/ui/form";
import {
  api,
  type CatalogueItem,
  type Lists,
  type NamedRef,
  type Practice,
  type ReportExport,
  type ReportFilters,
  type ReportRun,
  type Team,
  type Upload,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { formatCell, NUMERIC } from "./report-format";

const AGING = ["0 - 15", "16 - 30", "31 - 60", "61 - 90", "91 - 120", "120+"];
const FORMAT_LABEL = { csv: "CSV", xlsx: "Excel", pdf: "PDF" } as const;

/**
 * Pick a report, set filters, see it on screen (first 500 rows, totals over all), and download it as
 * CSV, Excel or PDF. With `fixed`, the page shows one report (Team Productivity, Uploads & Data Quality).
 */
export function RunReport({ fixed }: { fixed?: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const catalogue = useApi<CatalogueItem[]>("/reports/catalogue");
  const key = fixed ?? params.get("report") ?? "statement";

  if (catalogue.error)
    return (
      <EmptyState
        title="Reports could not be loaded"
        description={catalogue.error}
      />
    );
  if (!catalogue.data) return <p className="text-muted">Loading…</p>;
  const report = catalogue.data.find((r) => r.key === key);
  if (!report) return <EmptyState title="This report isn't available to you" />;

  return (
    <>
      {!fixed && (
        <div className="mb-3 grid grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-2">
          {catalogue.data
            .filter((r) => !r.staff)
            .map((r) => (
              <button
                key={r.key}
                type="button"
                aria-pressed={r.key === key}
                onClick={() =>
                  router.replace(`/reports?view=run&report=${r.key}`)
                }
                className={cn(
                  "rounded-[9px] border bg-white px-3 py-2.5 text-left",
                  r.key === key
                    ? "border-brand ring-1 ring-brand"
                    : "border-line hover:bg-hover",
                )}
              >
                <span className="block text-[13px] font-bold">{r.title}</span>
                <span className="mt-0.5 block text-[11px] text-muted">
                  {r.description}
                </span>
              </button>
            ))}
        </div>
      )}
      {/* A new report starts fresh: no filters, no result, nothing downloaded yet. */}
      <ReportRunner key={report.key} report={report} />
    </>
  );
}

function ReportRunner({ report }: { report: CatalogueItem }) {
  const { permissions } = useAuth();
  const canExport = permissions.includes("reports.export");
  const [filters, setFilters] = useState<ReportFilters>({});
  const [result, setResult] = useState<ReportRun | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [made, setMade] = useState<ReportExport | null>(null);

  async function run(f: ReportFilters) {
    setBusy("run");
    setError(null);
    try {
      setResult(
        await api<ReportRun>(`/reports/${report.key}/run`, {
          method: "POST",
          body: clean(f),
        }),
      );
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not run the report.",
      );
      setResult(null);
    } finally {
      setBusy(null);
    }
  }

  async function download(format: "csv" | "xlsx" | "pdf") {
    setBusy(format);
    setError(null);
    try {
      const exported = await api<ReportExport>(
        `/reports/${report.key}/exports`,
        {
          method: "POST",
          body: { format, filters: clean(filters) },
        },
      );
      setMade(exported);
      const link = document.createElement("a");
      link.href = `/api/reports/exports/${exported.id}/download`;
      link.download = exported.file_name;
      document.body.append(link);
      link.click();
      link.remove();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not generate the file.",
      );
    } finally {
      setBusy(null);
    }
  }

  // Run once on arrival, with no filters (after the first paint, so the screen shows straight away).
  useEffect(() => {
    const first = setTimeout(() => void run({}), 0);
    return () => clearTimeout(first);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <Panel
        title={report.title}
        action={<span className="text-muted">Dates: {report.date_basis}</span>}
      >
        <FilterForm report={report} value={filters} onChange={setFilters} />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            disabled={busy !== null}
            onClick={() => void run(filters)}
          >
            {busy === "run" ? "Running…" : "Run report"}
          </Button>
          <Button
            disabled={busy !== null}
            onClick={() => {
              setFilters({});
              void run({});
            }}
          >
            Clear filters
          </Button>
          {canExport && (
            <span className="ml-auto flex flex-wrap items-center gap-2">
              <span className="text-[12px] text-muted">Download</span>
              {(["csv", "xlsx", "pdf"] as const).map((format) => (
                <Button
                  key={format}
                  disabled={busy !== null}
                  onClick={() => void download(format)}
                >
                  {busy === format ? "Preparing…" : FORMAT_LABEL[format]}
                </Button>
              ))}
            </span>
          )}
        </div>
        {report.contains_phi && (
          <p className="mt-2 text-[11px] text-danger-ink">
            Contains patient information. Downloads are recorded, and Management
            is notified.
          </p>
        )}
        {made && (
          <p role="status" className="mt-2 text-[12px] text-muted">
            {made.number} ({FORMAT_LABEL[made.format]}, {made.row_count} rows)
            is downloading. You can download it again from{" "}
            <a
              href="/reports?view=exports"
              className="font-semibold text-brand"
            >
              Export History
            </a>{" "}
            until {formatDateTime(made.expires_at)}.
          </p>
        )}
        <FormError message={error} />
      </Panel>

      {result && <ResultTable result={result} />}
    </>
  );
}

function clean(f: ReportFilters): ReportFilters {
  return Object.fromEntries(
    Object.entries(f).filter(
      ([, v]) =>
        v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0),
    ),
  ) as ReportFilters;
}

function FilterForm({
  report,
  value,
  onChange,
}: {
  report: CatalogueItem;
  value: ReportFilters;
  onChange: (f: ReportFilters) => void;
}) {
  const has = (name: string) => report.filters.includes(name);
  const practices = useApi<Practice[]>(
    has("practice_ids") ? "/practices?status=active" : null,
  );
  const people = useApi<NamedRef[]>(
    has("assigned_user_id") ? "/reports/people" : null,
  );
  const teams = useApi<Team[]>(has("team_id") ? "/teams" : null);
  const uploads = useApi<Upload[]>(
    has("upload_id") ? "/uploads?view=all&limit=100" : null,
  );
  const lists = useApi<Lists>(has("claim_statuses") ? "/lists" : null);
  const set = (patch: Partial<ReportFilters>) =>
    onChange({ ...value, ...patch });
  const one = (list: string[] | undefined) => list?.[0] ?? "";

  return (
    <div className="grid grid-cols-4 gap-3 max-[1100px]:grid-cols-2 max-[600px]:grid-cols-1">
      {has("date_from") && (
        <Field label="From">
          <input
            type="date"
            className={cn(inputClass, "w-full")}
            value={value.date_from ?? ""}
            onChange={(e) => set({ date_from: e.target.value || undefined })}
          />
        </Field>
      )}
      {has("date_to") && (
        <Field label="To">
          <input
            type="date"
            className={cn(inputClass, "w-full")}
            value={value.date_to ?? ""}
            onChange={(e) => set({ date_to: e.target.value || undefined })}
          />
        </Field>
      )}
      {has("practice_ids") && (
        <Field label="Practice">
          <select
            className={cn(selectClass, "w-full")}
            value={one(value.practice_ids)}
            onChange={(e) =>
              set({ practice_ids: e.target.value ? [e.target.value] : [] })
            }
          >
            <option value="">All my practices</option>
            {(practices.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
      )}
      {has("payer") && (
        <Field label="Payer contains">
          <input
            className={cn(inputClass, "w-full")}
            value={value.payer ?? ""}
            maxLength={120}
            onChange={(e) => set({ payer: e.target.value })}
          />
        </Field>
      )}
      {has("claim_statuses") && (
        <Field label="Claim status">
          <select
            className={cn(selectClass, "w-full")}
            value={one(value.claim_statuses)}
            onChange={(e) =>
              set({ claim_statuses: e.target.value ? [e.target.value] : [] })
            }
          >
            <option value="">Any</option>
            <option value="No status">No status</option>
            {(lists.data?.claim_status ?? []).map((o) => (
              <option key={o.value} value={o.value}>
                {o.value}
              </option>
            ))}
          </select>
        </Field>
      )}
      {has("work_states") && (
        <Field label="Work status">
          <select
            className={cn(selectClass, "w-full")}
            value={one(value.work_states)}
            onChange={(e) =>
              set({
                work_states: e.target.value ? [e.target.value as "open"] : [],
              })
            }
          >
            <option value="">Any</option>
            <option value="open">Open</option>
            <option value="pending_completion">Awaiting completion</option>
            <option value="closed">Closed</option>
          </select>
        </Field>
      )}
      {has("assigned_user_id") && (
        <Field label="Person">
          <select
            className={cn(selectClass, "w-full")}
            value={value.assigned_user_id ?? ""}
            onChange={(e) =>
              set({ assigned_user_id: e.target.value || undefined })
            }
          >
            <option value="">Anyone</option>
            {(people.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
      )}
      {has("team_id") && teams.data && teams.data.length > 0 && (
        <Field label="Team">
          <select
            className={cn(selectClass, "w-full")}
            value={value.team_id ?? ""}
            onChange={(e) => set({ team_id: e.target.value || undefined })}
          >
            <option value="">Any team</option>
            {teams.data.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </Field>
      )}
      {has("upload_id") && uploads.data && (
        <Field label="Upload">
          <select
            className={cn(selectClass, "w-full")}
            value={value.upload_id ?? ""}
            onChange={(e) => set({ upload_id: e.target.value || undefined })}
          >
            <option value="">Any upload</option>
            {uploads.data.map((u) => (
              <option key={u.id} value={u.id}>
                {u.number}, {u.practice.name}
              </option>
            ))}
          </select>
        </Field>
      )}
      {has("aging_buckets") && (
        <Field label="Aging (days)">
          <select
            className={cn(selectClass, "w-full")}
            value={one(value.aging_buckets)}
            onChange={(e) =>
              set({ aging_buckets: e.target.value ? [e.target.value] : [] })
            }
          >
            <option value="">Any</option>
            {AGING.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </Field>
      )}
      {has("priorities") && (
        <Field label="Priority">
          <select
            className={cn(selectClass, "w-full")}
            value={one(value.priorities)}
            onChange={(e) =>
              set({
                priorities: e.target.value ? [e.target.value as "high"] : [],
              })
            }
          >
            <option value="">Any</option>
            <option value="urgent">Urgent</option>
            <option value="high">High</option>
            <option value="normal">Normal</option>
            <option value="low">Low</option>
          </select>
        </Field>
      )}
    </div>
  );
}

export function ResultTable({ result: r }: { result: ReportRun }) {
  return (
    <Panel
      flush
      className="mt-3"
      title={`${r.row_count.toLocaleString("en-US")} rows`}
      action={
        <span className="flex items-center gap-2 text-muted">
          {r.contains_phi && (
            <StatusPill label="Patient information" tone="danger" />
          )}
          {r.period}
        </span>
      }
    >
      <p className="border-b border-line px-[15px] py-2 text-[11px] text-muted">
        {r.filters_label.length > 0 && (
          <>Filters: {r.filters_label.join("; ")}. </>
        )}
        Scope: {r.scope.join(", ")}.
      </p>
      {r.rows.length === 0 ? (
        <EmptyState title="No rows match these filters" />
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <thead>
              <tr>
                {r.columns.map((c, i) => (
                  <Th
                    key={c.key}
                    className={cn(
                      NUMERIC.has(c.kind) && "text-right",
                      i === 0 && "pl-[15px]",
                    )}
                  >
                    {c.label}
                  </Th>
                ))}
              </tr>
            </thead>
            <tbody>
              {r.rows.map((row, index) => (
                <tr key={index}>
                  {r.columns.map((c, i) => (
                    <Td
                      key={c.key}
                      className={cn(
                        "whitespace-nowrap",
                        NUMERIC.has(c.kind) && "text-right tabular-nums",
                        i === 0 && "pl-[15px] font-semibold",
                        c.key === "flags" &&
                          Boolean(row[c.key]) &&
                          "font-semibold text-danger-ink",
                      )}
                    >
                      {formatCell(c, row[c.key])}
                    </Td>
                  ))}
                </tr>
              ))}
              {Object.keys(r.totals).length > 0 && (
                <tr className="border-t-2 border-navy font-bold">
                  {r.columns.map((c, i) => (
                    <Td
                      key={c.key}
                      className={cn(
                        NUMERIC.has(c.kind) && "text-right tabular-nums",
                        i === 0 && "pl-[15px]",
                      )}
                    >
                      {i === 0
                        ? `Total (${r.row_count})`
                        : c.key in r.totals
                          ? formatCell(c, r.totals[c.key])
                          : ""}
                    </Td>
                  ))}
                </tr>
              )}
            </tbody>
          </Table>
        </div>
      )}
      <div className="border-t border-line px-[15px] py-2 text-[11px] text-muted">
        {r.shown < r.row_count && (
          <p className="font-semibold">
            Showing the first {r.shown} of {r.row_count} rows; totals cover all
            of them. Download for every row.
          </p>
        )}
        {r.notes.map((n) => (
          <p key={n}>{n}</p>
        ))}
      </div>
    </Panel>
  );
}
