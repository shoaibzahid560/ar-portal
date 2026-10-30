"use client";

import { useState } from "react";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { Button } from "@/components/ui/button";
import { FormError, inputClass } from "@/components/ui/form";
import { api, type ListKey, type Lists } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { useApi } from "@/lib/use-api";

const LISTS: { key: ListKey; label: string }[] = [
  { key: "claim_status", label: "Claim Status" },
  { key: "pay_status", label: "Pay Status" },
  { key: "check_status", label: "Check Status" },
  { key: "action_taken", label: "Action Taken" },
];

/**
 * The dropdowns from the AR sheet. Options can be added, retired and restored. They are never renamed
 * or deleted, so values already saved on claims keep their meaning; to fix a spelling, add the corrected
 * option and retire the old one.
 */
export function ListsEditor() {
  const { permissions } = useAuth();
  const canEdit = permissions.includes("lists.manage");
  const lists = useApi<Lists>("/lists");
  const [error, setError] = useState<string | null>(null);

  if (lists.error)
    return (
      <EmptyState title="Lists could not be loaded" description={lists.error} />
    );
  if (!lists.data) return <p className="text-muted">Loading lists…</p>;
  const data = lists.data;

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      lists.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
    }
  }

  return (
    <>
      <p className="mb-3 text-[12px] text-muted">
        These are the dropdowns on every claim. Retired options stay on claims
        that already use them but can’t be chosen again. To correct a spelling,
        add the corrected option and retire the old one. Every change is
        recorded in the audit log. “Assigned to” isn’t a list here: it shows the
        AR staff of each claim’s practice.
      </p>
      <FormError message={error} />
      <div className="mt-3 grid grid-cols-2 items-start gap-3 max-[900px]:grid-cols-1">
        {LISTS.map(({ key, label }) => (
          <ListCard
            key={key}
            label={label}
            options={data[key]}
            canEdit={canEdit}
            onAdd={(value) =>
              run(() =>
                api(`/lists/${key}`, { method: "POST", body: { value } }),
              )
            }
            onToggle={(id, active) =>
              run(() =>
                api(`/lists/items/${id}`, {
                  method: "PATCH",
                  body: { active },
                }),
              )
            }
          />
        ))}
      </div>
    </>
  );
}

function ListCard({
  label,
  options,
  canEdit,
  onAdd,
  onToggle,
}: {
  label: string;
  options: Lists[ListKey];
  canEdit: boolean;
  onAdd: (value: string) => Promise<void>;
  onToggle: (id: number, active: boolean) => Promise<void>;
}) {
  const [value, setValue] = useState("");
  return (
    <Panel
      title={`${label} (${options.filter((o) => o.active).length} in use)`}
    >
      <ul className="mb-3">
        {options.map((o) => (
          <li
            key={o.id}
            className="flex items-center gap-2 border-b border-[#f0f1f3] py-1.5 last:border-b-0"
          >
            <span
              className={cn(
                "text-[12px]",
                !o.active && "text-muted line-through",
              )}
            >
              {o.value}
            </span>
            {!o.active && (
              <span className="text-[10px] text-muted">retired</span>
            )}
            {canEdit && (
              <button
                type="button"
                onClick={() => void onToggle(o.id, !o.active)}
                className="ml-auto text-[11px] font-semibold text-brand"
              >
                {o.active ? "Retire" : "Restore"}
              </button>
            )}
          </li>
        ))}
      </ul>
      {canEdit && (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (value.trim()) void onAdd(value.trim()).then(() => setValue(""));
          }}
        >
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            maxLength={80}
            aria-label={`New ${label} option`}
            placeholder="New option"
            className={cn(inputClass, "min-w-0 flex-1")}
          />
          <Button type="submit" disabled={!value.trim()}>
            Add
          </Button>
        </form>
      )}
    </Panel>
  );
}
