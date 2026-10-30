"use client";

import { AlertTriangle, FileText } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { StatusPill } from "@/components/data/status-pill";
import { Button } from "@/components/ui/button";
import {
  Field,
  FormError,
  inputClass,
  selectClass,
} from "@/components/ui/form";
import {
  api,
  apiForm,
  type Assignee,
  type AuditEvent,
  type ClaimDetail,
  type ListKey,
  type Lists,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDate, formatDateTime, formatMoney } from "@/lib/format";
import { claimStatusTone } from "@/lib/status";
import { useApi } from "@/lib/use-api";

/** The AR sheet's work columns, in the sheet's order. */
const LIST_FIELDS: { key: ListKey; label: string }[] = [
  { key: "claim_status", label: "Claim status" },
  { key: "pay_status", label: "Pay status" },
  { key: "check_status", label: "Check status" },
  { key: "action_taken", label: "Action taken" },
];
const MONEY_FIELDS = [
  { key: "allowed_amount", label: "Allowed amount" },
  { key: "recovered_amount", label: "Recovered amount" },
  { key: "patient_responsibility", label: "Patient responsibility" },
] as const;
const DATE_FIELDS = [
  { key: "cashed_date", label: "Cashed date" },
  { key: "payment_posted_date", label: "Payment posted date" },
  { key: "followup_date", label: "Follow-up / worked date" },
] as const;

type FormKey =
  | ListKey
  | (typeof MONEY_FIELDS)[number]["key"]
  | (typeof DATE_FIELDS)[number]["key"]
  | "assigned_user_id";
type FormState = Record<FormKey, string>;

const MONEY = /^\d{1,7}(\.\d{1,2})?$/;

function initialForm(claim: ClaimDetail): FormState {
  return {
    claim_status: claim.claim_status ?? "",
    pay_status: claim.pay_status ?? "",
    check_status: claim.check_status ?? "",
    action_taken: claim.action_taken ?? "",
    allowed_amount: claim.allowed_amount ?? "",
    recovered_amount: claim.recovered_amount ?? "",
    patient_responsibility: claim.patient_responsibility ?? "",
    cashed_date: claim.cashed_date ?? "",
    payment_posted_date: claim.payment_posted_date ?? "",
    followup_date: claim.followup_date ?? "",
    assigned_user_id: claim.assigned_to?.id ?? "",
  };
}

export function ClaimWork() {
  const { claimId } = useParams<{ claimId: string }>();
  const claim = useApi<ClaimDetail>(`/claims/${claimId}`);
  const history = useApi<AuditEvent[]>(`/claims/${claimId}/history`);
  const lists = useApi<Lists>("/lists");
  const assignees = useApi<Assignee[]>(
    claim.data?.can_work ? `/claims/${claimId}/assignees` : null,
  );

  if (claim.error)
    return <EmptyState title="Claim not available" description={claim.error} />;
  if (!claim.data || !lists.data)
    return <p className="text-muted">Loading the claim…</p>;
  const c = claim.data;
  const refresh = () => {
    claim.reload();
    history.reload();
  };

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-[16px] font-bold">{c.number}</h2>
        <StatusPill
          label={c.claim_status ?? "No status"}
          tone={claimStatusTone(c.claim_status)}
        />
        <StatusPill
          label={`Aging ${c.aging_bucket} (${c.aging_days} days)`}
          tone="info"
        />
        <span className="text-[12px] text-muted">
          {c.practice.name} · from{" "}
          <Link href={`/uploads/${c.upload.id}`} className="text-brand">
            {c.upload.number}
          </Link>
        </span>
      </div>

      {c.needs_review && <ReviewBanner claim={c} onDone={refresh} />}

      <div className="grid grid-cols-[minmax(0,2fr)_minmax(280px,1fr)] items-start gap-3 max-[1100px]:grid-cols-1">
        <div className="grid gap-3">
          <Panel title="From the upload">
            <dl className="grid grid-cols-4 gap-x-4 gap-y-3 max-[800px]:grid-cols-2">
              <Detail label="Patient">{c.patient_name}</Detail>
              <Detail label="Service date">{formatDate(c.service_date)}</Detail>
              <Detail label="Subscriber ID">{c.subscriber_id}</Detail>
              <Detail label="Patient DOB">{formatDate(c.patient_dob)}</Detail>
              <Detail label="Insurance carrier">{c.insurance_carrier}</Detail>
              <Detail label="Subscriber">{c.subscriber_name ?? "—"}</Detail>
              <Detail label="Subscriber DOB">
                {formatDate(c.subscriber_dob)}
              </Detail>
              <Detail label="Billed">{formatMoney(c.billed)}</Detail>
            </dl>
          </Panel>

          <WorkForm
            key={c.updated_at}
            claim={c}
            lists={lists.data}
            assignees={assignees.data ?? []}
            onSaved={refresh}
          />
          <EobPanel claim={c} onSaved={refresh} />
        </div>

        <div className="grid gap-3">
          <NotesPanel claim={c} onSaved={refresh} />
          <HistoryPanel
            events={history.data}
            assignees={assignees.data ?? []}
          />
        </div>
      </div>
    </>
  );
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] text-muted">{label}</dt>
      <dd
        className="mt-0.5 truncate font-semibold"
        title={typeof children === "string" ? children : undefined}
      >
        {children}
      </dd>
    </div>
  );
}

function ReviewBanner({
  claim,
  onDone,
}: {
  claim: ClaimDetail;
  onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <div
      role="status"
      className="mb-3 flex flex-wrap items-center gap-3 rounded-[9px] bg-warn-soft px-3 py-2.5 text-[12px] text-warn-ink"
    >
      <AlertTriangle size={16} aria-hidden />
      <p className="min-w-0 flex-1">{claim.review_reason}</p>
      {claim.can_work && (
        <Button
          disabled={busy}
          onClick={() => {
            setBusy(true);
            void api(`/claims/${claim.id}`, {
              method: "PATCH",
              body: { needs_review: false },
            }).finally(onDone);
          }}
        >
          Mark as reviewed
        </Button>
      )}
    </div>
  );
}

function WorkForm({
  claim,
  lists,
  assignees,
  onSaved,
}: {
  claim: ClaimDetail;
  lists: Lists;
  assignees: Assignee[];
  onSaved: () => void;
}) {
  const start = initialForm(claim);
  const [form, setForm] = useState<FormState>(start);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const readOnly = !claim.can_work;
  const changed = (Object.keys(form) as FormKey[]).filter(
    (k) => form[k] !== start[k],
  );
  const set = (key: FormKey, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  async function save() {
    const bad = MONEY_FIELDS.find(
      (f) => form[f.key] !== "" && !MONEY.test(form[f.key]),
    );
    if (bad)
      return setError(
        `${bad.label}: enter an amount like 125.50 (no $ sign or commas).`,
      );
    setSaving(true);
    setError(null);
    try {
      const body = Object.fromEntries(
        changed.map((k) => [k, form[k] === "" ? null : form[k]]),
      );
      await api(`/claims/${claim.id}`, { method: "PATCH", body });
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
      setSaving(false);
    }
  }

  // A retired option, or a person no longer assignable, stays visible while it's the current value.
  const optionsFor = (key: ListKey) => {
    const values = lists[key].filter((o) => o.active).map((o) => o.value);
    return start[key] && !values.includes(start[key])
      ? [...values, start[key]]
      : values;
  };
  const people =
    claim.assigned_to && !assignees.some((a) => a.id === claim.assigned_to?.id)
      ? [
          ...assignees,
          {
            id: claim.assigned_to.id,
            name: claim.assigned_to.name,
            role: claim.assigned_to.role ?? "",
          },
        ]
      : assignees;

  return (
    <Panel
      title="Work on this claim"
      action={readOnly ? <span className="text-muted">View only</span> : null}
    >
      <fieldset
        disabled={readOnly || saving}
        className="grid grid-cols-3 gap-3 max-[900px]:grid-cols-2 max-[560px]:grid-cols-1"
      >
        {LIST_FIELDS.map(({ key, label }) => (
          <Field key={key} label={label}>
            <select
              className={cn(selectClass, "w-full")}
              value={form[key]}
              onChange={(e) => set(key, e.target.value)}
            >
              <option value="">—</option>
              {optionsFor(key).map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </Field>
        ))}
        <Field label="Assigned to">
          <select
            className={cn(selectClass, "w-full")}
            value={form.assigned_user_id}
            onChange={(e) => set("assigned_user_id", e.target.value)}
          >
            <option value="">Unassigned</option>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.role ? ` (${p.role})` : ""}
              </option>
            ))}
          </select>
        </Field>
        {DATE_FIELDS.map(({ key, label }) => (
          <Field key={key} label={label}>
            <input
              type="date"
              className={cn(inputClass, "w-full")}
              value={form[key]}
              onChange={(e) => set(key, e.target.value)}
            />
          </Field>
        ))}
        {MONEY_FIELDS.map(({ key, label }) => (
          <Field key={key} label={label}>
            <input
              inputMode="decimal"
              placeholder="0.00"
              className={cn(inputClass, "w-full")}
              value={form[key]}
              onChange={(e) => set(key, e.target.value.trim())}
            />
          </Field>
        ))}
      </fieldset>
      <FormError message={error} />
      {!readOnly && (
        <div className="mt-3 flex items-center justify-end gap-2">
          {changed.length > 0 && (
            <span className="mr-auto text-[11px] text-muted">
              {changed.length} unsaved change(s)
            </span>
          )}
          <Button
            onClick={() => setForm(start)}
            disabled={saving || changed.length === 0}
          >
            Discard
          </Button>
          <Button
            variant="primary"
            onClick={() => void save()}
            disabled={saving || changed.length === 0}
          >
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      )}
    </Panel>
  );
}

function EobPanel({
  claim,
  onSaved,
}: {
  claim: ClaimDetail;
  onSaved: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [inputKey, setInputKey] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function attach() {
    if (!file) return setError("Choose the EOB file first.");
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      await apiForm(`/claims/${claim.id}/eob`, form);
      setFile(null);
      setInputKey((k) => k + 1);
      onSaved();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not attach the EOB.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="EOB">
      {claim.eob ? (
        <p className="mb-2 flex items-center gap-2 text-[12px]">
          <FileText size={15} aria-hidden className="text-muted" />
          <a
            href={`/api/claims/${claim.id}/eob`}
            target="_blank"
            rel="noreferrer"
            className="font-semibold text-brand"
          >
            {claim.eob.file_name}
          </a>
          <span className="text-muted">
            attached {formatDateTime(claim.eob.uploaded_at)}
          </span>
        </p>
      ) : (
        <p className="mb-2 text-[12px] text-muted">No EOB attached yet.</p>
      )}
      {claim.can_work && (
        <div className="flex flex-wrap items-center gap-2">
          <input
            key={inputKey}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.webp"
            aria-label={claim.eob ? "Replace the EOB" : "Attach an EOB"}
            className={cn(inputClass, "py-1.5")}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Button onClick={() => void attach()} disabled={busy || !file}>
            {busy ? "Attaching…" : claim.eob ? "Replace EOB" : "Attach EOB"}
          </Button>
        </div>
      )}
      <FormError message={error} />
    </Panel>
  );
}

function NotesPanel({
  claim,
  onSaved,
}: {
  claim: ClaimDetail;
  onSaved: () => void;
}) {
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function add() {
    if (!body.trim()) return setError("Write a note first.");
    setBusy(true);
    setError(null);
    try {
      await api(`/claims/${claim.id}/notes`, {
        method: "POST",
        body: { body },
      });
      setBody("");
      onSaved();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not add the note.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title={`Notes (${claim.notes.length})`}>
      {claim.can_work && (
        <div className="mb-3">
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={3}
            maxLength={2000}
            aria-label="New note"
            placeholder="Called the payer; claim in process, reference 48211"
            className={cn(inputClass, "h-auto w-full py-2")}
          />
          <FormError message={error} />
          <div className="mt-2 flex justify-end">
            <Button onClick={() => void add()} disabled={busy || !body.trim()}>
              {busy ? "Adding…" : "Add note"}
            </Button>
          </div>
        </div>
      )}
      {claim.notes.length === 0 ? (
        <p className="text-[12px] text-muted">No notes yet.</p>
      ) : (
        <ul className="grid gap-2.5">
          {claim.notes.map((n) => (
            <li key={n.id} className="border-l-2 border-line pl-2.5">
              <p className="text-[12px] whitespace-pre-wrap">{n.body}</p>
              <p className="mt-0.5 text-[10px] text-muted">
                {n.author.name} · {formatDateTime(n.created_at)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

const HISTORY_LABELS: Record<string, string> = {
  "claim.imported": "Imported from an upload",
  "claim.updated": "Changed",
  "claim.assigned": "Assignment changed",
  "claim.note_added": "Note added",
  "claim.eob_attached": "EOB attached",
  "claim.eob_downloaded": "EOB opened",
  "claim.reviewed": "Marked as reviewed",
};

function HistoryPanel({
  events,
  assignees,
}: {
  events: AuditEvent[] | null;
  assignees: Assignee[];
}) {
  const names = new Map(assignees.map((a) => [a.id, a.name]));
  const show = (key: string, value: unknown) => {
    if (value === null || value === undefined || value === "") return "empty";
    if (key === "assigned_user_id")
      return names.get(String(value)) ?? "another person";
    return String(value);
  };
  return (
    <Panel title="History">
      {!events ? (
        <p className="text-[12px] text-muted">Loading…</p>
      ) : (
        <ul className="grid gap-2.5">
          {events.map((e) => (
            <li key={e.id} className="text-[12px]">
              <p className="font-semibold">
                {HISTORY_LABELS[e.action] ?? e.action}
              </p>
              {(e.action === "claim.updated" ||
                e.action === "claim.assigned") &&
                Object.keys(e.after ?? {}).map((k) => (
                  <p key={k} className="text-[11px]">
                    {k.replace(/_user_id$/, "").replace(/_/g, " ")}:{" "}
                    {show(k, e.before?.[k])} → {show(k, e.after?.[k])}
                  </p>
                ))}
              <p className="text-[10px] text-muted">
                {e.actor?.name ?? "System"} · {formatDateTime(e.occurred_at)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
