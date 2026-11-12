"use client";

import { useState } from "react";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { StatusPill } from "@/components/data/status-pill";
import { Table, Td, Th } from "@/components/data/table";
import type { ReportExport } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/use-api";

/** Every report file generated: who, what, filters, scope, downloads, expiry (brief section 10). */
export function ExportHistory() {
  const { permissions } = useAuth();
  const oversight = permissions.includes("notifications.oversight");
  const [show, setShow] = useState<"mine" | "everyone">("mine");
  const exports = useApi<ReportExport[]>(`/reports/exports?show=${show}`);

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {oversight && (
          <div role="tablist" aria-label="Whose exports" className="flex gap-1">
            {(["mine", "everyone"] as const).map((s) => (
              <button
                key={s}
                role="tab"
                type="button"
                aria-selected={show === s}
                onClick={() => setShow(s)}
                className={cn(
                  "rounded-[7px] border px-2.5 py-1.5 text-[12px]",
                  show === s
                    ? "border-brand bg-brand-soft font-semibold text-brand"
                    : "border-line bg-white",
                )}
              >
                {s === "mine" ? "My exports" : "Everyone's exports"}
              </button>
            ))}
          </div>
        )}
        <p className="text-[12px] text-muted">
          Files can be downloaded again by the person who generated them until
          they expire. Every download is recorded.
        </p>
      </div>
      <Panel flush>
        {exports.error ? (
          <EmptyState
            title="Exports could not be loaded"
            description={exports.error}
          />
        ) : !exports.data ? (
          <p className="p-6 text-muted">Loading…</p>
        ) : exports.data.length === 0 ? (
          <EmptyState
            title="No exports yet"
            description="Run a report and choose CSV, Excel or PDF."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="pl-[15px]">Export</Th>
                <Th>Report</Th>
                <Th>Format</Th>
                <Th className="text-right">Rows</Th>
                <Th>Filters and scope</Th>
                <Th>Generated</Th>
                <Th>Downloads</Th>
                <Th className="pr-[15px] text-right">File</Th>
              </tr>
            </thead>
            <tbody>
              {exports.data.map((e) => (
                <tr key={e.id} className="align-top">
                  <Td className="pl-[15px] font-bold">{e.number}</Td>
                  <Td>
                    <p>{e.report_title}</p>
                    {e.contains_phi && (
                      <p className="text-[10px] font-semibold text-danger-ink">
                        Patient information
                      </p>
                    )}
                  </Td>
                  <Td>{e.format.toUpperCase()}</Td>
                  <Td className="text-right">
                    {e.row_count.toLocaleString("en-US")}
                  </Td>
                  <Td className="max-w-[280px] text-[11px]">
                    <p>{e.filters_label.join("; ") || "No filters"}</p>
                    <p className="text-muted">{e.scope.join(", ")}</p>
                  </Td>
                  <Td className="whitespace-nowrap">
                    <p>{e.requested_by.name}</p>
                    <p className="text-[11px] text-muted">
                      {formatDateTime(e.created_at)}
                    </p>
                  </Td>
                  <Td className="whitespace-nowrap text-[11px]">
                    <p>{e.download_count} time(s)</p>
                    {e.last_downloaded_at && (
                      <p className="text-muted">
                        last {formatDateTime(e.last_downloaded_at)}
                      </p>
                    )}
                  </Td>
                  <Td className="pr-[15px] text-right">
                    {e.expired ? (
                      <StatusPill label="Expired" tone="neutral" />
                    ) : e.can_download ? (
                      <a
                        href={`/api/reports/exports/${e.id}/download`}
                        className="font-semibold text-brand"
                      >
                        Download
                      </a>
                    ) : (
                      <span className="text-[11px] text-muted">
                        Until {formatDateTime(e.expires_at)}
                      </span>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
    </>
  );
}
