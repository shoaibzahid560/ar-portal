"use client";

import { useState } from "react";
import { Panel } from "@/components/data/panel";
import { Button } from "@/components/ui/button";
import { Field, FormError, inputClass } from "@/components/ui/form";
import { api, type ReportTargets as Targets } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useApi } from "@/lib/use-api";

const FIELDS: {
  key: keyof Targets;
  label: string;
  hint: string;
  suffix: string;
}[] = [
  {
    key: "claims_worked_per_day",
    label: "Claims worked per working day",
    hint: "Team Productivity flags people below this.",
    suffix: "claims",
  },
  {
    key: "first_pass_quality_pct",
    label: "First-pass rate",
    hint: "Share of claims approved without being returned for correction.",
    suffix: "%",
  },
  {
    key: "overdue_followups_per_person",
    label: "Overdue follow-ups per person, at most",
    hint: "The dashboard warns when someone has more.",
    suffix: "follow-ups",
  },
  {
    key: "aging_over_90_pct",
    label: "Open claims over 90 days, at most",
    hint: "The dashboard warns above this share.",
    suffix: "%",
  },
  {
    key: "export_retention_days",
    label: "Keep downloaded report files for",
    hint: "After this, a file must be generated again. The export log is kept.",
    suffix: "days",
  },
];

/** Targets and alert thresholds used by reports and the dashboard (management decision #7). */
export function ReportTargetsForm() {
  const saved = useApi<Targets>("/reports/targets");
  const [draft, setDraft] = useState<Targets | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const value = draft ?? saved.data;

  async function save() {
    if (!value) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await api("/reports/targets", { method: "PUT", body: value });
      setDraft(null);
      saved.reload();
      setMessage(
        "Targets saved. Reports and the dashboard use them straight away.",
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Panel title="Report targets">
      <p className="mb-3 text-[12px] text-muted">
        Starting values until management agrees the targets. Every change is
        recorded in the audit log.
      </p>
      {!value ? (
        <p className="text-muted">Loading…</p>
      ) : (
        <div className="grid max-w-[640px] gap-3">
          {FIELDS.map((f) => (
            <Field key={f.key} label={`${f.label} (${f.suffix})`} hint={f.hint}>
              <input
                type="number"
                min={0}
                className={cn(inputClass, "w-28")}
                value={value[f.key]}
                onChange={(e) =>
                  setDraft({ ...value, [f.key]: Number(e.target.value) })
                }
              />
            </Field>
          ))}
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              onClick={() => void save()}
              disabled={saving || draft === null}
            >
              {saving ? "Saving…" : "Save targets"}
            </Button>
            {draft && (
              <Button onClick={() => setDraft(null)} disabled={saving}>
                Discard changes
              </Button>
            )}
          </div>
          {message && (
            <p role="status" className="text-[12px] text-ok-ink">
              {message}
            </p>
          )}
          <FormError message={error} />
        </div>
      )}
    </Panel>
  );
}
