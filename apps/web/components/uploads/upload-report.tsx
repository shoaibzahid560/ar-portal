"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import { EmptyState } from "@/components/data/empty-state";
import { MetricCard } from "@/components/data/metric-card";
import { Panel } from "@/components/data/panel";
import { StatusPill } from "@/components/data/status-pill";
import { Table, Td, Th } from "@/components/data/table";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, FormError, inputClass } from "@/components/ui/form";
import {
  api,
  type LineValues,
  type UploadDetail,
  type UploadRow,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDate, formatDateTime, formatMoney } from "@/lib/format";
import { UPLOAD_STATUSES } from "@/lib/status";
import { useApi } from "@/lib/use-api";

const FIELDS: { key: string; label: string; kind?: "date" | "money" }[] = [
  { key: "patient_name", label: "Patient" },
  { key: "service_date", label: "Service date", kind: "date" },
  { key: "subscriber_id", label: "Subscriber ID" },
  { key: "patient_dob", label: "Patient DOB", kind: "date" },
  { key: "insurance_carrier", label: "Insurance carrier" },
  { key: "subscriber_name", label: "Subscriber" },
  { key: "subscriber_dob", label: "Subscriber DOB", kind: "date" },
  { key: "billed", label: "Billed", kind: "money" },
];

function show(
  values: LineValues | null,
  field: (typeof FIELDS)[number],
): string {
  const value = values?.[field.key] ?? null;
  if (value === null || value === "") return "—";
  if (field.kind === "date") return formatDate(value);
  if (field.kind === "money") return formatMoney(value);
  return value;
}

const linkClass =
  "rounded-[7px] border border-line bg-white px-3 py-2 text-[12px] font-semibold hover:bg-hover";
type Tab = "needs-decision" | "new" | "duplicate" | "errors";

/**
 * One import batch: the preview (what the file contains, before anything is created), the decisions on lines
 * that match existing claims, and submit, approve and commit, turn down, discard or reverse.
 */
export function UploadReport() {
  const { uploadId } = useParams<{ uploadId: string }>();
  const upload = useApi<UploadDetail>(`/uploads/${uploadId}`);
  const [tab, setTab] = useState<Tab>("needs-decision");
  const [asking, setAsking] = useState<"reject" | "reverse" | "discard" | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (upload.error)
    return <EmptyState title="Upload not found" description={upload.error} />;
  if (!upload.data) return <p className="text-muted">Loading the upload…</p>;
  const u = upload.data;
  const status = UPLOAD_STATUSES[u.status];
  const committedLike = u.status === "committed" || u.status === "reversed";

  async function act(path: string, body?: unknown) {
    setBusy(true);
    setError(null);
    try {
      await api(`/uploads/${u.id}/${path}`, {
        method: "POST",
        body: body ?? {},
      });
      setAsking(null);
      upload.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

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
          {committedLike && u.created_claims > 0 && (
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

      <History upload={u} />

      {u.status === "failed" && (
        <Banner tone="danger">
          This file couldn’t be used: {u.failure_reason} Fix the file and upload
          it again.
        </Banner>
      )}
      {u.mapping_warning && u.status !== "failed" && (
        <Banner tone="warn">{u.mapping_warning}</Banner>
      )}
      {u.status === "rejected" && (
        <Banner tone="neutral">
          Turned down by {u.decided_by?.name}
          {u.decision_reason ? `: ${u.decision_reason}` : "."} Nothing was
          created.
        </Banner>
      )}
      {u.status === "discarded" && (
        <Banner tone="neutral">Discarded. Nothing was created.</Banner>
      )}
      {u.status === "reversed" && (
        <Banner tone="danger">
          Reversed by {u.reversed_by?.name} on {formatDateTime(u.reversed_at)}:{" "}
          {u.reverse_reason} Its new claims were withdrawn and updated claims
          got their earlier values back.
        </Banner>
      )}

      {u.status !== "failed" && (
        <>
          {committedLike ? (
            <section className="mb-2 grid grid-cols-4 gap-2.5 max-[900px]:grid-cols-2">
              <MetricCard
                label="New claims created"
                value={String(u.created_claims)}
                meta="Confirmed new lines"
              />
              <MetricCard
                label="Existing claims updated"
                value={String(u.updated_claims)}
                meta="Same claim, new values"
              />
              <MetricCard
                label="Lines skipped"
                value={String(u.skipped_rows)}
                meta="Already in the system, or skipped"
              />
              <MetricCard
                label="Rows with errors"
                value={String(u.error_rows)}
                meta="Not imported"
              />
            </section>
          ) : (
            <section className="mb-2 grid grid-cols-6 gap-2.5 max-[1200px]:grid-cols-3 max-[640px]:grid-cols-2">
              <MetricCard
                label="Rows in the file"
                value={String(u.total_rows)}
                meta="Blank lines aren’t counted"
              />
              <MetricCard
                label="New"
                value={String(u.new_rows)}
                meta="Will become new claims"
              />
              <MetricCard
                label="Already in the system"
                value={String(u.duplicate_rows)}
                meta="Will be skipped"
              />
              <MetricCard
                label="Possible changes"
                value={String(u.changed_rows)}
                meta="To an existing claim: decide"
              />
              <MetricCard
                label="Repeated in the file"
                value={String(u.repeat_rows)}
                meta="Same line twice: decide"
              />
              <MetricCard
                label="Rows with errors"
                value={String(u.error_rows)}
                meta="Won’t be imported"
              />
            </section>
          )}
          <p className="mb-3 text-[11px] text-muted">
            Check: {u.new_rows} new + {u.duplicate_rows} already in system +{" "}
            {u.changed_rows} possible changes + {u.repeat_rows} repeated +{" "}
            {u.error_rows} with errors ={" "}
            {u.new_rows +
              u.duplicate_rows +
              u.changed_rows +
              u.repeat_rows +
              u.error_rows}{" "}
            of {u.total_rows} rows.
          </p>
        </>
      )}

      <ActionBar
        upload={u}
        busy={busy}
        onSubmit={() => void act("submit")}
        onCommit={() => void act("commit")}
        onAsk={setAsking}
      />
      <FormError message={error} />

      {u.status !== "failed" && (
        <>
          <div
            role="tablist"
            aria-label="Lines"
            className="mt-3 mb-2 flex flex-wrap gap-1"
          >
            {(
              [
                [
                  "needs-decision",
                  `Needs a decision (${u.changed_rows + u.repeat_rows})`,
                ],
                ["new", `New (${u.new_rows})`],
                ["duplicate", `Already in the system (${u.duplicate_rows})`],
                ["errors", `Row errors (${u.errors.length})`],
              ] as [Tab, string][]
            ).map(([key, label]) => (
              <button
                key={key}
                role="tab"
                type="button"
                aria-selected={tab === key}
                onClick={() => setTab(key)}
                className={cn(
                  "rounded-[7px] border px-2.5 py-1.5 text-[12px]",
                  tab === key
                    ? "border-brand bg-brand-soft font-semibold text-brand"
                    : "border-line bg-white",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          {tab === "errors" ? (
            <ErrorsTable upload={u} />
          ) : (
            <Lines
              key={`${tab}-${u.status}`}
              upload={u}
              tab={tab}
              onDecided={upload.reload}
            />
          )}
        </>
      )}

      {asking && (
        <ReasonDialog
          kind={asking}
          busy={busy}
          error={error}
          onClose={() => setAsking(null)}
          onConfirm={(reason) =>
            void act(
              asking === "discard" ? "discard" : asking,
              asking === "discard" ? undefined : { reason },
            )
          }
        />
      )}
    </>
  );
}

function Banner({
  tone,
  children,
}: {
  tone: "warn" | "danger" | "neutral";
  children: ReactNode;
}) {
  const styles = {
    warn: "bg-warn-soft text-warn-ink",
    danger: "bg-danger-soft text-danger-ink",
    neutral: "bg-neutral-soft",
  }[tone];
  return (
    <p className={cn("mb-3 rounded-[9px] px-3 py-2.5 text-[12px]", styles)}>
      {children}
    </p>
  );
}

function History({ upload: u }: { upload: UploadDetail }) {
  const steps = [
    u.submitted_by &&
      `Submitted by ${u.submitted_by.name}, ${formatDateTime(u.submitted_at)}`,
    u.status === "committed" || u.status === "reversed"
      ? u.decided_by &&
        `Approved and committed by ${u.decided_by.name}, ${formatDateTime(u.decided_at)}`
      : null,
  ].filter(Boolean);
  if (steps.length === 0) return null;
  return <p className="mb-3 text-[11px] text-muted">{steps.join(" · ")}</p>;
}

function ActionBar({
  upload: u,
  busy,
  onSubmit,
  onCommit,
  onAsk,
}: {
  upload: UploadDetail;
  busy: boolean;
  onSubmit: () => void;
  onCommit: () => void;
  onAsk: (kind: "reject" | "reverse" | "discard") => void;
}) {
  const a = u.actions;
  const any =
    a.can_submit ||
    a.can_commit ||
    a.can_reject ||
    a.can_discard ||
    a.can_reverse ||
    a.commit_blocked_because;
  if (!any) return null;
  return (
    <div className="mb-1 flex flex-wrap items-center gap-2 rounded-[9px] border border-line bg-white px-3 py-2.5">
      {u.status === "preview" && (
        <p className="mr-auto text-[12px] text-muted">
          Nothing has been created yet. Check the lines below, then submit them
          for approval by a second person.
        </p>
      )}
      {u.status === "submitted" && (
        <p className="mr-auto text-[12px] text-muted">
          {a.commit_blocked_because ??
            "Ready to approve. Committing creates the new claims and applies the updates."}
        </p>
      )}
      {u.status === "committed" && (
        <p className="mr-auto text-[12px] text-muted">
          Reversing withdraws this upload’s new claims and restores updated
          ones, as long as none has been worked.
        </p>
      )}
      {a.can_discard && (
        <Button disabled={busy} onClick={() => onAsk("discard")}>
          Discard
        </Button>
      )}
      {a.can_submit && (
        <Button variant="primary" disabled={busy} onClick={onSubmit}>
          Submit for approval
        </Button>
      )}
      {a.can_reject && (
        <Button disabled={busy} onClick={() => onAsk("reject")}>
          Turn down…
        </Button>
      )}
      {(a.can_commit ||
        (u.status === "submitted" && a.commit_blocked_because)) && (
        <Button
          variant="primary"
          disabled={busy || !a.can_commit}
          onClick={onCommit}
        >
          {busy ? "Committing…" : "Approve and commit"}
        </Button>
      )}
      {a.can_reverse && (
        <Button
          className="text-danger-ink"
          disabled={busy}
          onClick={() => onAsk("reverse")}
        >
          Reverse…
        </Button>
      )}
    </div>
  );
}

function Lines({
  upload: u,
  tab,
  onDecided,
}: {
  upload: UploadDetail;
  tab: Tab;
  onDecided: () => void;
}) {
  const rows = useApi<UploadRow[]>(`/uploads/${u.id}/rows?show=${tab}`);
  if (rows.error)
    return (
      <EmptyState title="Lines could not be loaded" description={rows.error} />
    );
  if (!rows.data) return <p className="text-muted">Loading…</p>;
  if (rows.data.length === 0)
    return (
      <Panel>
        <EmptyState title="No lines here" />
      </Panel>
    );

  if (tab === "needs-decision") {
    return (
      <div className="grid gap-3">
        {rows.data.map((row) => (
          <DecisionCard
            key={row.id}
            upload={u}
            row={row}
            onDecided={() => {
              rows.reload();
              onDecided();
            }}
          />
        ))}
      </div>
    );
  }
  return (
    <Panel flush>
      <Table>
        <thead>
          <tr>
            <Th className="pl-[15px]">Row</Th>
            {FIELDS.filter((f) =>
              [
                "patient_name",
                "service_date",
                "subscriber_id",
                "insurance_carrier",
                "billed",
              ].includes(f.key),
            ).map((f) => (
              <Th
                key={f.key}
                className={f.kind === "money" ? "text-right" : undefined}
              >
                {f.label}
              </Th>
            ))}
            <Th className="pr-[15px]">
              {tab === "duplicate" ? "Matches" : "Claim"}
            </Th>
          </tr>
        </thead>
        <tbody>
          {rows.data.map((row) => {
            const claim =
              row.result_claim ??
              (row.candidates[0]
                ? { id: row.candidates[0].id, name: row.candidates[0].number }
                : null);
            return (
              <tr key={row.id}>
                <Td className="pl-[15px] font-bold">{row.row_number}</Td>
                {FIELDS.filter((f) =>
                  [
                    "patient_name",
                    "service_date",
                    "subscriber_id",
                    "insurance_carrier",
                    "billed",
                  ].includes(f.key),
                ).map((f) => (
                  <Td
                    key={f.key}
                    className={f.kind === "money" ? "text-right" : undefined}
                  >
                    {row.values ? (
                      show(row.values, f)
                    ) : (
                      <span className="text-muted">cleared</span>
                    )}
                  </Td>
                ))}
                <Td className="pr-[15px]">
                  {claim ? (
                    <Link
                      href={`/claims/${claim.id}`}
                      className="font-semibold text-brand"
                    >
                      {claim.name}
                    </Link>
                  ) : (
                    <span className="text-muted">
                      {tab === "new" ? "Created when committed" : "—"}
                    </span>
                  )}
                </Td>
              </tr>
            );
          })}
        </tbody>
      </Table>
      {rows.data.some((r) => !r.values) && (
        <p className="border-t border-line px-[15px] py-2 text-[11px] text-muted">
          Line values are cleared once a batch is decided; the claims hold them.
        </p>
      )}
    </Panel>
  );
}

function DecisionCard({
  upload: u,
  row,
  onDecided,
}: {
  upload: UploadDetail;
  row: UploadRow;
  onDecided: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const changed = row.classification === "changed";
  const editable = u.actions.can_decide;

  async function decide(
    decision: "create" | "update" | "skip",
    target?: string,
  ) {
    setError(null);
    try {
      await api(`/uploads/${u.id}/rows/${row.id}`, {
        method: "PATCH",
        body: { decision, target_claim_id: target ?? null },
      });
      onDecided();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
    }
  }

  const choice = (label: string, active: boolean, onClick: () => void) => (
    <button
      type="button"
      disabled={!editable}
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-[7px] border px-2.5 py-1.5 text-[12px]",
        active ? "border-brand bg-brand text-white" : "border-line bg-white",
        !editable && "opacity-70",
      )}
    >
      {label}
    </button>
  );

  return (
    <Panel
      title={`Row ${row.row_number}: ${changed ? "possible change to an existing claim" : "repeated in the file"}`}
      action={
        row.decision ? (
          <span className="text-[11px] text-muted">
            Decided by {row.decided_by}
          </span>
        ) : (
          <StatusPill label="Needs a decision" tone="warn" />
        )
      }
    >
      {row.values ? (
        <div className="mb-3 overflow-x-auto">
          <table className="w-full border-collapse text-[12px]">
            <thead>
              <tr>
                <th className="w-36 border-b border-line py-1.5 text-left text-[10px] font-semibold text-[#7b818c] uppercase">
                  Field
                </th>
                <th className="border-b border-line bg-warn-soft px-2 py-1.5 text-left text-[11px] font-bold text-warn-ink">
                  This line
                </th>
                {row.candidates.map((c) => (
                  <th
                    key={c.id}
                    className="border-b border-line px-2 py-1.5 text-left text-[11px] font-bold"
                  >
                    {c.number} · existing
                    <span className="block text-[10px] font-normal text-muted">
                      {c.claim_status ?? "No status"} ·{" "}
                      {c.assigned_to ?? "Unassigned"}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {FIELDS.map((f) => (
                <tr key={f.key}>
                  <td className="border-b border-[#f0f1f3] py-1.5 text-muted">
                    {f.label}
                  </td>
                  <td className="border-b border-[#f0f1f3] px-2 py-1.5">
                    {show(row.values, f)}
                  </td>
                  {row.candidates.map((c) => {
                    const differs = show(c.values, f) !== show(row.values, f);
                    return (
                      <td
                        key={c.id}
                        className={cn(
                          "border-b border-[#f0f1f3] px-2 py-1.5",
                          differs && "bg-warn-soft font-bold text-warn-ink",
                        )}
                      >
                        {show(c.values, f)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mb-3 text-[12px] text-muted">
          Line values were cleared when the batch was decided.
          {row.result_claim && (
            <>
              {" "}
              Result:{" "}
              <Link
                href={`/claims/${row.result_claim.id}`}
                className="font-semibold text-brand"
              >
                {row.result_claim.name}
              </Link>
            </>
          )}
        </p>
      )}
      <div className="flex flex-wrap gap-1.5">
        {changed &&
          row.candidates.map((c) =>
            choice(
              `Same claim: update ${c.number}`,
              row.decision === "update" && row.target_claim_id === c.id,
              () => void decide("update", c.id),
            ),
          )}
        {choice(
          changed ? "A new claim: create it" : "A separate claim: create it",
          row.decision === "create",
          () => void decide("create"),
        )}
        {choice(
          changed ? "Skip this line" : "Skip: it’s the same line twice",
          row.decision === "skip",
          () => void decide("skip"),
        )}
      </div>
      {!editable && !row.decision && (
        <p className="mt-2 text-[11px] text-muted">
          A reviewer for this practice decides these lines.
        </p>
      )}
      <FormError message={error} />
    </Panel>
  );
}

function ErrorsTable({ upload: u }: { upload: UploadDetail }) {
  if (u.errors.length === 0) {
    return (
      <Panel>
        <EmptyState title="No row errors" />
      </Panel>
    );
  }
  return (
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
  );
}

function ReasonDialog({
  kind,
  busy,
  error,
  onClose,
  onConfirm,
}: {
  kind: "reject" | "reverse" | "discard";
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  const text = {
    reject: {
      title: "Turn down this upload",
      body: "Nothing will be created, and the uploader is told why.",
      button: "Turn down",
    },
    reverse: {
      title: "Reverse this upload",
      body: "Its new claims are withdrawn and updated claims get their earlier values back. This is recorded in the audit log.",
      button: "Reverse",
    },
    discard: {
      title: "Discard this upload",
      body: "Nothing will be created. You can upload the file again later.",
      button: "Discard",
    },
  }[kind];
  const needsReason = kind === "reverse";
  return (
    <Dialog
      open
      title={text.title}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={busy || (needsReason && reason.trim().length < 5)}
            onClick={() => onConfirm(reason)}
          >
            {text.button}
          </Button>
        </>
      }
    >
      <p className="mb-3 text-[12px]">{text.body}</p>
      {kind !== "discard" && (
        <Field
          label={
            needsReason ? "Reason (required)" : "Reason (shown to the uploader)"
          }
        >
          <textarea
            className={cn(inputClass, "h-auto min-h-20 w-full py-2")}
            value={reason}
            maxLength={500}
            onChange={(e) => setReason(e.target.value)}
          />
        </Field>
      )}
      <FormError message={error} />
    </Dialog>
  );
}
