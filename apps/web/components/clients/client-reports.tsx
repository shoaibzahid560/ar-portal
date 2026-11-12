"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { StatusPill } from "@/components/data/status-pill";
import { Table, Td, Th } from "@/components/data/table";
import { ResultTable } from "@/components/reports/run-report";
import { Button } from "@/components/ui/button";
import {
  Field,
  FormError,
  inputClass,
  selectClass,
} from "@/components/ui/form";
import {
  api,
  type ClientCatalogueItem,
  type ClientContext,
  type NamedRef,
  type ReportExport,
  type ReportRun,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { getModule, resolveView } from "@/lib/navigation";
import { useApi } from "@/lib/use-api";
import { ClientAccounts } from "./clients-admin";

const AGING = ["0 - 15", "16 - 30", "31 - 60", "61 - 90", "91 - 120", "120+"];
const FORMAT_LABEL = { csv: "CSV", xlsx: "Excel", pdf: "PDF" } as const;
type ClientFilters = {
  date_from?: string;
  date_to?: string;
  practice_ids?: string[];
  payer?: string;
  aging_buckets?: string[];
};

/** What a client account sees: its approved reports, its own downloads, and its users when delegated. */
export function ClientReportsSection() {
  const view = resolveView(
    getModule("client-reports"),
    useSearchParams().get("view"),
  ).slug;
  const context = useApi<ClientContext>("/client-portal/context");
  if (context.error)
    return (
      <EmptyState
        title="Client reports are not available"
        description={context.error}
      />
    );
  if (!context.data) return <p className="text-muted">Loading…</p>;
  const c = context.data;
  return (
    <>
      <p className="mb-3 text-[12px] text-muted">
        <span className="font-bold text-ink">{c.organisation.name}</span>:{" "}
        {c.practices.map((p) => p.name).join(", ")}
        {c.patient_detail
          ? ""
          : ". Reports leave out patient names and subscriber IDs."}
      </p>
      {view === "downloads" ? (
        <ClientDownloads />
      ) : view === "users" && c.can_manage_users ? (
        <ClientAccounts
          base="/client-portal"
          practices={c.practices}
          canAddAdmin={false}
        />
      ) : (
        <ClientRunner practices={c.practices} />
      )}
    </>
  );
}

function ClientRunner({ practices }: { practices: NamedRef[] }) {
  const router = useRouter();
  const params = useSearchParams();
  const catalogue = useApi<ClientCatalogueItem[]>("/client-portal/catalogue");
  if (catalogue.error)
    return (
      <EmptyState
        title="Reports could not be loaded"
        description={catalogue.error}
      />
    );
  if (!catalogue.data) return <p className="text-muted">Loading…</p>;
  if (catalogue.data.length === 0) {
    return (
      <EmptyState
        title="No reports yet"
        description="Your account manager hasn't approved any reports yet."
      />
    );
  }
  const key = params.get("report") ?? catalogue.data[0].key;
  const report = catalogue.data.find((r) => r.key === key) ?? catalogue.data[0];
  return (
    <>
      <div className="mb-3 grid grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-2">
        {catalogue.data.map((r) => (
          <button
            key={r.key}
            type="button"
            aria-pressed={r.key === report.key}
            onClick={() =>
              router.replace(`/client-reports?view=reports&report=${r.key}`)
            }
            className={cn(
              "rounded-[9px] border bg-white px-3 py-2.5 text-left",
              r.key === report.key
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
      <ClientReport key={report.key} report={report} practices={practices} />
    </>
  );
}

function ClientReport({
  report,
  practices,
}: {
  report: ClientCatalogueItem;
  practices: NamedRef[];
}) {
  const { permissions } = useAuth();
  const canDownload = permissions.includes("client_reports.download");
  const [filters, setFilters] = useState<ClientFilters>({});
  const [result, setResult] = useState<ReportRun | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [made, setMade] = useState<ReportExport | null>(null);
  const dated = report.key !== "aging";

  async function run(f: ClientFilters) {
    setBusy("run");
    setError(null);
    try {
      setResult(
        await api<ReportRun>(`/client-portal/reports/${report.key}/run`, {
          method: "POST",
          body: clean(f),
        }),
      );
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not run the report.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function download(format: "csv" | "xlsx" | "pdf") {
    setBusy(format);
    setError(null);
    try {
      const exported = await api<ReportExport>(
        `/client-portal/reports/${report.key}/exports`,
        {
          method: "POST",
          body: { format, filters: clean(filters) },
        },
      );
      setMade(exported);
      const link = document.createElement("a");
      link.href = `/api/client-portal/exports/${exported.id}/download`;
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

  useEffect(() => {
    const first = setTimeout(() => void run({}), 0);
    return () => clearTimeout(first);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const set = (patch: Partial<ClientFilters>) =>
    setFilters({ ...filters, ...patch });
  return (
    <>
      <Panel
        title={report.title}
        action={<span className="text-muted">Dates: {report.date_basis}</span>}
      >
        <div className="grid grid-cols-4 gap-3 max-[1100px]:grid-cols-2 max-[600px]:grid-cols-1">
          {dated && (
            <>
              <Field label="From">
                <input
                  type="date"
                  className={cn(inputClass, "w-full")}
                  value={filters.date_from ?? ""}
                  onChange={(e) =>
                    set({ date_from: e.target.value || undefined })
                  }
                />
              </Field>
              <Field label="To">
                <input
                  type="date"
                  className={cn(inputClass, "w-full")}
                  value={filters.date_to ?? ""}
                  onChange={(e) =>
                    set({ date_to: e.target.value || undefined })
                  }
                />
              </Field>
            </>
          )}
          {practices.length > 1 && (
            <Field label="Practice">
              <select
                className={cn(selectClass, "w-full")}
                value={filters.practice_ids?.[0] ?? ""}
                onChange={(e) =>
                  set({ practice_ids: e.target.value ? [e.target.value] : [] })
                }
              >
                <option value="">All my practices</option>
                {practices.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <Field label="Payer contains">
            <input
              className={cn(inputClass, "w-full")}
              value={filters.payer ?? ""}
              maxLength={120}
              onChange={(e) => set({ payer: e.target.value })}
            />
          </Field>
          <Field label="Aging (days)">
            <select
              className={cn(selectClass, "w-full")}
              value={filters.aging_buckets?.[0] ?? ""}
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
        </div>
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
          {canDownload && (
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
        {made && (
          <p role="status" className="mt-2 text-[12px] text-muted">
            {made.number} ({FORMAT_LABEL[made.format]}, {made.row_count} rows)
            is downloading. It stays under My Downloads until{" "}
            {formatDateTime(made.expires_at)}.
          </p>
        )}
        <FormError message={error} />
      </Panel>
      {result && <ResultTable result={result} />}
    </>
  );
}

function clean(f: ClientFilters): ClientFilters {
  return Object.fromEntries(
    Object.entries(f).filter(
      ([, v]) =>
        v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0),
    ),
  ) as ClientFilters;
}

function ClientDownloads() {
  const exports = useApi<ReportExport[]>("/client-portal/exports");
  return (
    <Panel flush>
      {!exports.data ? (
        <p className="p-6 text-muted">Loading…</p>
      ) : exports.data.length === 0 ? (
        <EmptyState
          title="No downloads yet"
          description="Run a report and choose CSV, Excel or PDF."
        />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th className="pl-[15px]">File</Th>
              <Th>Report</Th>
              <Th>Format</Th>
              <Th className="text-right">Rows</Th>
              <Th>Filters</Th>
              <Th>Generated</Th>
              <Th className="pr-[15px] text-right">Download</Th>
            </tr>
          </thead>
          <tbody>
            {exports.data.map((e) => (
              <tr key={e.id}>
                <Td className="pl-[15px] font-bold">{e.number}</Td>
                <Td>{e.report_title.replace(/ \(client:.*\)$/, "")}</Td>
                <Td>{FORMAT_LABEL[e.format]}</Td>
                <Td className="text-right">{e.row_count}</Td>
                <Td className="text-[11px]">
                  {e.filters_label.join("; ") || "No filters"}
                </Td>
                <Td className="text-[12px]">{formatDateTime(e.created_at)}</Td>
                <Td className="pr-[15px] text-right">
                  {e.can_download ? (
                    <a
                      href={`/api/client-portal/exports/${e.id}/download`}
                      className="font-semibold text-brand"
                    >
                      Download
                    </a>
                  ) : (
                    <StatusPill label="Expired" tone="neutral" />
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Panel>
  );
}
