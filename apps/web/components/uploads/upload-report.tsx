"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { EmptyState } from "@/components/data/empty-state";
import { MetricCard } from "@/components/data/metric-card";
import { Panel } from "@/components/data/panel";
import { StatusPill } from "@/components/data/status-pill";
import { Table, Td, Th } from "@/components/data/table";
import type { UploadDetail } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { UPLOAD_STATUSES } from "@/lib/status";
import { useApi } from "@/lib/use-api";

const linkClass =
  "rounded-[7px] border border-line bg-white px-3 py-2 text-[12px] font-semibold hover:bg-hover";

/** The itemised result of one upload: totals that add up, and every row problem by row number. */
export function UploadReport() {
  const { uploadId } = useParams<{ uploadId: string }>();
  const upload = useApi<UploadDetail>(`/uploads/${uploadId}`);

  if (upload.error)
    return <EmptyState title="Upload not found" description={upload.error} />;
  if (!upload.data) return <p className="text-muted">Loading the upload…</p>;
  const u = upload.data;
  const status = UPLOAD_STATUSES[u.status];

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-[16px] font-bold">{u.number}</h2>
        <StatusPill label={status.label} tone={status.tone} />
        <span className="text-[12px] text-muted">
          {u.practice.name} · {u.file_name} · uploaded by {u.uploaded_by.name}{" "}
          on {formatDateTime(u.created_at)}
        </span>
        <span className="ml-auto flex flex-wrap gap-2">
          {u.created_claims > 0 && (
            <Link
              href={`/claims?view=all&upload=${u.id}`}
              className={linkClass}
            >
              View its claims
            </Link>
          )}
          <a href={`/api/uploads/${u.id}/file`} className={linkClass}>
            Download original file
          </a>
        </span>
      </div>

      {u.status === "failed" ? (
        <p
          role="alert"
          className="mb-3 rounded-[9px] bg-danger-soft px-3 py-2.5 text-[12px] text-danger-ink"
        >
          This file couldn’t be used: {u.failure_reason} Fix the file and upload
          it again.
        </p>
      ) : (
        <>
          <section className="mb-3 grid grid-cols-5 gap-2.5 max-[1100px]:grid-cols-3 max-[640px]:grid-cols-2">
            <MetricCard
              label="Rows in the file"
              value={String(u.total_rows)}
              meta="Blank lines aren’t counted"
            />
            <MetricCard
              label="New claims"
              value={String(u.created_claims)}
              meta="Created from this file"
            />
            <MetricCard
              label="Already in the system"
              value={String(u.duplicate_rows)}
              meta="Same line uploaded before; skipped"
            />
            <MetricCard
              label="Rows with errors"
              value={String(u.error_rows)}
              meta="Not imported; listed below"
            />
            <MetricCard
              label="Needs review"
              value={String(u.review_rows)}
              meta="Imported, but may be a changed line"
            />
          </section>
          <p className="mb-3 text-[11px] text-muted">
            Check: {u.created_claims} new + {u.duplicate_rows} already in system
            + {u.error_rows} with errors ={" "}
            {u.created_claims + u.duplicate_rows + u.error_rows} of{" "}
            {u.total_rows} rows.
          </p>
        </>
      )}

      {u.errors.length > 0 && (
        <Panel
          flush
          title={`Row problems (${u.errors.length})`}
          action={
            <a
              href={`/api/uploads/${u.id}/errors.csv`}
              className="font-semibold text-brand"
            >
              Download error report
            </a>
          }
        >
          <Table>
            <thead>
              <tr>
                <Th className="pl-[15px]">Row in the file</Th>
                <Th>Column</Th>
                <Th className="pr-[15px]">Problem</Th>
              </tr>
            </thead>
            <tbody>
              {u.errors.map((e, i) => (
                <tr key={`${e.row_number}-${i}`}>
                  <Td className="pl-[15px] font-bold">{e.row_number}</Td>
                  <Td>{e.column}</Td>
                  <Td className="pr-[15px]">{e.message}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      )}
    </>
  );
}
