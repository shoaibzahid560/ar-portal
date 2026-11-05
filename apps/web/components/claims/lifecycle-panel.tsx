"use client";

import { useState } from "react";
import { Panel } from "@/components/data/panel";
import { StatusPill } from "@/components/data/status-pill";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import {
  Field,
  FormError,
  inputClass,
  selectClass,
} from "@/components/ui/form";
import { api, type ClaimDetail, type Priority } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { PRIORITIES, WORK_STATES } from "@/lib/status";

type Step =
  | "request-completion"
  | "approve-completion"
  | "return"
  | "continue"
  | "close"
  | "reopen";

const STEPS: Record<
  Step,
  {
    title: string;
    button: string;
    help: string;
    reason: "required" | "optional";
  }
> = {
  "request-completion": {
    title: "Mark this claim complete",
    button: "Mark complete",
    help: "A reviewer then approves and closes it, returns it for correction, or asks you to continue. Until then its fields are locked.",
    reason: "optional",
  },
  "approve-completion": {
    title: "Approve and close",
    button: "Approve and close",
    help: "The claim closes and leaves the work queues. It can be reopened later if needed.",
    reason: "optional",
  },
  return: {
    title: "Return for correction",
    button: "Return",
    help: "The claim goes back to the person working it, marked Returned, with your reason.",
    reason: "required",
  },
  continue: {
    title: "Continue follow-up",
    button: "Continue",
    help: "Not finished yet: the claim goes back to open with a new follow-up date.",
    reason: "optional",
  },
  close: {
    title: "Close this claim",
    button: "Close",
    help: "For example, found already paid or written off. It leaves the work queues and can be reopened.",
    reason: "required",
  },
  reopen: {
    title: "Reopen this claim",
    button: "Reopen",
    help: "The claim goes back to the work queues.",
    reason: "required",
  },
};

/**
 * Where the work on a claim stands (Open, Awaiting completion, Closed, Returned), the latest step with its
 * reason, the steps this person may take now, and the claim's priority.
 */
export function LifecyclePanel({
  claim: c,
  onSaved,
}: {
  claim: ClaimDetail;
  onSaved: () => void;
}) {
  const [step, setStep] = useState<Step | null>(null);
  const [error, setError] = useState<string | null>(null);
  const state = WORK_STATES[c.work_state];
  const live = !c.withdrawn && !c.merged_into;

  async function setPriority(priority: Priority) {
    setError(null);
    try {
      await api(`/claims/${c.id}`, { method: "PATCH", body: { priority } });
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
    }
  }

  const latest =
    c.state_changed_by &&
    {
      open: c.returned
        ? `Returned for correction by ${c.state_changed_by.name}`
        : `Last changed by ${c.state_changed_by.name}`,
      pending_completion: `Marked complete by ${c.completion_requested_by?.name ?? c.state_changed_by.name}`,
      closed: `Closed by ${c.state_changed_by.name}`,
    }[c.work_state];

  if (!live) return null;
  return (
    <Panel
      title="Work status"
      action={
        <span className="flex items-center gap-2">
          <span className="text-[11px] text-muted">Priority</span>
          {c.can_prioritize ? (
            <select
              aria-label="Priority"
              className={cn(selectClass, "h-8")}
              value={c.priority}
              onChange={(e) => void setPriority(e.target.value as Priority)}
            >
              {Object.entries(PRIORITIES).map(([key, p]) => (
                <option key={key} value={key}>
                  {p.label}
                </option>
              ))}
            </select>
          ) : (
            <StatusPill
              label={PRIORITIES[c.priority].label}
              tone={PRIORITIES[c.priority].tone}
            />
          )}
        </span>
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill label={state.label} tone={state.tone} />
        {c.work_state === "open" && c.returned && (
          <StatusPill label="Returned for correction" tone="danger" />
        )}
        {latest && (
          <span className="text-[12px] text-muted">
            {latest}
            {c.state_changed_at
              ? `, ${formatDateTime(c.state_changed_at)}`
              : ""}
          </span>
        )}
      </div>
      {c.state_reason && (
        <p
          className={cn(
            "mt-2 rounded-[9px] px-3 py-2 text-[12px]",
            c.returned && c.work_state === "open"
              ? "bg-danger-soft text-danger-ink"
              : "bg-neutral-soft",
          )}
        >
          {c.state_reason}
        </p>
      )}
      {c.work_state === "pending_completion" && !c.can_review_completion && (
        <p className="mt-2 text-[12px] text-muted">
          Waiting for a reviewer. Its fields are locked until it’s approved,
          returned or continued; notes can still be added.
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {c.can_request_completion && (
          <Button
            variant="primary"
            onClick={() => setStep("request-completion")}
          >
            Mark complete…
          </Button>
        )}
        {c.can_review_completion && (
          <>
            <Button
              variant="primary"
              onClick={() => setStep("approve-completion")}
            >
              Approve and close…
            </Button>
            <Button onClick={() => setStep("return")}>
              Return for correction…
            </Button>
            <Button onClick={() => setStep("continue")}>
              Continue follow-up…
            </Button>
          </>
        )}
        {c.can_close && (
          <Button onClick={() => setStep("close")}>Close…</Button>
        )}
        {c.can_reopen && (
          <Button onClick={() => setStep("reopen")}>Reopen…</Button>
        )}
      </div>
      <FormError message={error} />

      {step && (
        <StepDialog
          claim={c}
          step={step}
          onClose={() => setStep(null)}
          onSaved={() => {
            setStep(null);
            onSaved();
          }}
        />
      )}
    </Panel>
  );
}

function StepDialog({
  claim,
  step,
  onClose,
  onSaved,
}: {
  claim: ClaimDetail;
  step: Step;
  onClose: () => void;
  onSaved: () => void;
}) {
  const info = STEPS[step];
  const [reason, setReason] = useState("");
  const [followup, setFollowup] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const blocked =
    saving ||
    (info.reason === "required" && reason.trim().length < 3) ||
    (step === "continue" && !followup);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { reason: reason.trim() || null };
      if (step === "continue") body.followup_date = followup;
      await api(`/claims/${claim.id}/${step}`, { method: "POST", body });
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
      setSaving(false);
    }
  }

  return (
    <Dialog
      open
      title={`${info.title}: ${claim.number}`}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => void save()}
            disabled={blocked}
          >
            {saving ? "Saving…" : info.button}
          </Button>
        </>
      }
    >
      <p className="mb-3 text-[12px]">{info.help}</p>
      {step === "continue" && (
        <Field label="New follow-up date">
          <input
            type="date"
            className={cn(inputClass, "w-full")}
            value={followup}
            onChange={(e) => setFollowup(e.target.value)}
          />
        </Field>
      )}
      <Field
        label={
          step === "request-completion"
            ? "Note for the reviewer (optional)"
            : info.reason === "required"
              ? "Reason (required, recorded)"
              : "Note (optional, recorded)"
        }
      >
        <textarea
          className={cn(inputClass, "h-auto min-h-20 w-full py-2")}
          value={reason}
          maxLength={1000}
          onChange={(e) => setReason(e.target.value)}
        />
      </Field>
      <FormError message={error} />
    </Dialog>
  );
}
