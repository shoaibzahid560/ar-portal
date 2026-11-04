"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form";
import { api, type ClaimDetail } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDate, formatMoney } from "@/lib/format";
import { useApi } from "@/lib/use-api";

type Row = {
  label: string;
  value: (c: ClaimDetail) => string;
  uploaded?: boolean;
};

const ROWS: Row[] = [
  { label: "Patient", value: (c) => c.patient_name, uploaded: true },
  {
    label: "Service date",
    value: (c) => formatDate(c.service_date),
    uploaded: true,
  },
  { label: "Subscriber ID", value: (c) => c.subscriber_id, uploaded: true },
  {
    label: "Insurance carrier",
    value: (c) => c.insurance_carrier,
    uploaded: true,
  },
  { label: "Billed", value: (c) => formatMoney(c.billed), uploaded: true },
  {
    label: "Patient DOB",
    value: (c) => formatDate(c.patient_dob),
    uploaded: true,
  },
  {
    label: "Subscriber",
    value: (c) => c.subscriber_name ?? "—",
    uploaded: true,
  },
  {
    label: "Subscriber DOB",
    value: (c) => formatDate(c.subscriber_dob),
    uploaded: true,
  },
  { label: "From upload", value: (c) => c.upload.number },
  { label: "Claim status", value: (c) => c.claim_status ?? "—" },
  { label: "Assigned to", value: (c) => c.assigned_to?.name ?? "Unassigned" },
  { label: "Follow-up", value: (c) => formatDate(c.followup_date) },
  { label: "Notes", value: (c) => String(c.notes.length) },
];

/** The new line next to each earlier claim it may belong to, with the two possible decisions. */
export function ReviewCompare() {
  const router = useRouter();
  const { claimId } = useParams<{ claimId: string }>();
  const line = useApi<ClaimDetail>(`/claims/${claimId}`);
  const candidates = useApi<ClaimDetail[]>(
    line.data?.can_review ? `/claims/${claimId}/matches` : null,
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (line.error)
    return <EmptyState title="Line not available" description={line.error} />;
  if (!line.data) return <p className="text-muted">Loading…</p>;
  const l = line.data;
  if (!l.can_review) {
    return (
      <Panel>
        <EmptyState
          title="This line doesn’t need review"
          description={
            l.merged_into
              ? `It was merged into ${l.merged_into.number}.`
              : "It has already been decided, or you don’t have permission to resolve review items."
          }
        />
        <div className="mt-2 flex justify-center gap-2">
          <Link href="/review" className="text-[12px] font-semibold text-brand">
            Back to the review queue
          </Link>
        </div>
      </Panel>
    );
  }
  const others = candidates.data ?? [];

  async function decide(decision: "same" | "separate", targetId?: string) {
    setBusy(true);
    setError(null);
    try {
      await api(`/claims/${l.id}/resolve`, {
        method: "POST",
        body: { decision, target_id: targetId ?? null },
      });
      router.push("/review?view=open");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not save the decision.",
      );
      setBusy(false);
    }
  }

  return (
    <>
      <p className="mb-3 text-[12px] text-muted">
        <strong className="text-ink">{l.number}</strong> came in with{" "}
        <Link href={`/uploads/${l.upload.id}`} className="text-brand">
          {l.upload.number}
        </Link>
        . An earlier claim exists for the same patient, subscriber ID and
        service date. Highlighted cells differ from the new line.
      </p>
      <FormError message={error} />
      <Panel flush className="mt-3">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[12px]">
            <thead>
              <tr>
                <th className="w-40 border-b border-line px-3 py-2.5 text-left text-[10px] font-semibold tracking-[0.04em] text-[#7b818c] uppercase">
                  Field
                </th>
                <Head title={`${l.number} · new line`} accent />
                {others.map((c) => (
                  <Head key={c.id} title={`${c.number} · earlier claim`} />
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => (
                <tr key={row.label}>
                  <td className="border-b border-[#f0f1f3] px-3 py-2 text-muted">
                    {row.label}
                  </td>
                  <Cell>{row.value(l)}</Cell>
                  {others.map((c) => (
                    <Cell
                      key={c.id}
                      differs={row.uploaded && row.value(c) !== row.value(l)}
                    >
                      {row.value(c)}
                    </Cell>
                  ))}
                </tr>
              ))}
              <tr>
                <td className="px-3 py-3" />
                <td className="px-3 py-3 align-top">
                  <Button
                    onClick={() => void decide("separate")}
                    disabled={busy}
                  >
                    Separate claim: keep both
                  </Button>
                </td>
                {others.map((c) => (
                  <td key={c.id} className="px-3 py-3 align-top">
                    <Button
                      variant="primary"
                      onClick={() => void decide("same", c.id)}
                      disabled={busy}
                    >
                      Same claim: update {c.number}
                    </Button>
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </Panel>
      {candidates.data && others.length === 0 && (
        <p className="mt-3 text-[12px] text-muted">
          The earlier claim is no longer available (it may have been merged).
          Keep this line as a separate claim.
        </p>
      )}
      <p className="mt-3 text-[11px] text-muted">
        <strong>Same claim:</strong> the earlier claim takes the new line’s
        uploaded values (such as a corrected amount) and keeps all its work,
        notes and history; the new line is folded into it.{" "}
        <strong>Separate claim:</strong> both stay as claims. Either decision is
        recorded in the audit log.
      </p>
    </>
  );
}

function Head({ title, accent = false }: { title: string; accent?: boolean }) {
  return (
    <th
      className={cn(
        "border-b border-line px-3 py-2.5 text-left text-[11px] font-bold",
        accent && "bg-warn-soft text-warn-ink",
      )}
    >
      {title}
    </th>
  );
}

function Cell({
  children,
  differs = false,
}: {
  children: ReactNode;
  differs?: boolean;
}) {
  return (
    <td
      className={cn(
        "border-b border-[#f0f1f3] px-3 py-2",
        differs && "bg-warn-soft font-bold text-warn-ink",
      )}
    >
      {children}
    </td>
  );
}
