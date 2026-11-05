"use client";

import { useState } from "react";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { StatusPill } from "@/components/data/status-pill";
import { Table, Td, Th } from "@/components/data/table";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import {
  Field,
  FormError,
  inputClass,
  selectClass,
} from "@/components/ui/form";
import {
  api,
  type Grant,
  type GrantablePermission,
  type Practice,
  type User,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { formatDate, formatDateTime } from "@/lib/format";
import type { Tone } from "@/lib/status";
import { useApi } from "@/lib/use-api";

const SHOW = [
  { key: "current", label: "Current" },
  { key: "pending", label: "Waiting for approval" },
  { key: "review", label: "Due for review" },
  { key: "ended", label: "Ended" },
  { key: "all", label: "All" },
] as const;

const STATE: Record<Grant["state"], { label: string; tone: Tone }> = {
  pending: { label: "Waiting for approval", tone: "warn" },
  active: { label: "Active", tone: "ok" },
  expired: { label: "Expired", tone: "neutral" },
  rejected: { label: "Turned down", tone: "neutral" },
  revoked: { label: "Ended", tone: "neutral" },
};

/**
 * Additional permissions for individual people (specification, section 4). Standard ones take effect at
 * once; elevated ones wait for a second person's approval and come up for review every 90 days.
 */
export function GrantsAdmin() {
  const { permissions } = useAuth();
  const canManage = permissions.includes("grants.manage");
  const canApprove = permissions.includes("grants.approve");
  const [show, setShow] = useState<(typeof SHOW)[number]["key"]>("current");
  const grants = useApi<Grant[]>(`/grants?show=${show}`);
  const [creating, setCreating] = useState(false);
  const [ending, setEnding] = useState<{
    grant: Grant;
    action: "reject" | "revoke";
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function act(path: string, body?: unknown) {
    setError(null);
    try {
      await api(path, { method: "POST", body: body ?? {} });
      grants.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
    }
  }

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div
          role="tablist"
          aria-label="Which grants"
          className="flex flex-wrap gap-1"
        >
          {SHOW.map((s) => (
            <button
              key={s.key}
              role="tab"
              type="button"
              aria-selected={show === s.key}
              onClick={() => setShow(s.key)}
              className={cn(
                "rounded-[7px] border px-2.5 py-1.5 text-[12px]",
                show === s.key
                  ? "border-brand bg-brand-soft font-semibold text-brand"
                  : "border-line bg-white",
              )}
            >
              {s.label}
            </button>
          ))}
        </div>
        {canManage && (
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => setCreating(true)}
          >
            Give a permission
          </Button>
        )}
      </div>
      <p className="mb-3 text-[12px] text-muted">
        One extra permission for one person, on top of their roles. Permissions
        that reach beyond a practice or manage access (marked{" "}
        <strong>elevated</strong>) need a second person’s approval and a review
        every 90 days.
      </p>
      <FormError message={error} />

      <Panel flush className="mt-3">
        {grants.error ? (
          <EmptyState
            title="Grants could not be loaded"
            description={grants.error}
          />
        ) : !grants.data ? (
          <p className="p-6 text-muted">Loading…</p>
        ) : grants.data.length === 0 ? (
          <EmptyState title="No grants in this view" />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="pl-[15px]">Person</Th>
                <Th>Permission</Th>
                <Th>Where</Th>
                <Th>Reason</Th>
                <Th>Given by / approved by</Th>
                <Th>Ends</Th>
                <Th>Status</Th>
                <Th className="pr-[15px] text-right">Action</Th>
              </tr>
            </thead>
            <tbody>
              {grants.data.map((g) => (
                <tr key={g.id} className="align-top">
                  <Td className="pl-[15px] font-bold">{g.person.name}</Td>
                  <Td>
                    <p>{g.permission_description}</p>
                    {g.elevated && (
                      <p className="text-[10px] font-bold text-warn-ink uppercase">
                        Elevated
                      </p>
                    )}
                  </Td>
                  <Td>{g.practice?.name ?? "All their practices"}</Td>
                  <Td className="max-w-[260px]">
                    <p className="text-[12px]">{g.reason}</p>
                    {g.end_reason && (
                      <p className="text-[11px] text-muted">
                        Ended: {g.end_reason}
                      </p>
                    )}
                  </Td>
                  <Td>
                    <p>{g.requested_by.name}</p>
                    <p className="text-[11px] text-muted">
                      {g.approved_by
                        ? `Approved by ${g.approved_by.name}`
                        : "Not yet approved"}
                    </p>
                    <p className="text-[10px] text-muted">
                      {formatDateTime(g.created_at)}
                    </p>
                  </Td>
                  <Td className="whitespace-nowrap">
                    <p>
                      {g.expires_at
                        ? formatDate(g.expires_at.slice(0, 10))
                        : "No end date"}
                    </p>
                    {g.review_due_at && g.state === "active" && (
                      <p
                        className={cn(
                          "text-[11px]",
                          g.review_overdue
                            ? "font-bold text-danger-ink"
                            : "text-muted",
                        )}
                      >
                        Review {g.review_overdue ? "overdue since" : "due"}{" "}
                        {formatDate(g.review_due_at.slice(0, 10))}
                      </p>
                    )}
                  </Td>
                  <Td>
                    <StatusPill
                      label={STATE[g.state].label}
                      tone={STATE[g.state].tone}
                    />
                  </Td>
                  <Td className="pr-[15px] text-right">
                    <div className="flex flex-wrap justify-end gap-1.5">
                      {g.can_approve && (
                        <>
                          <Button
                            variant="primary"
                            onClick={() => void act(`/grants/${g.id}/approve`)}
                          >
                            Approve
                          </Button>
                          <Button
                            onClick={() =>
                              setEnding({ grant: g, action: "reject" })
                            }
                          >
                            Turn down
                          </Button>
                        </>
                      )}
                      {g.review_overdue && canApprove && (
                        <Button
                          onClick={() => void act(`/grants/${g.id}/review`)}
                        >
                          Still needed
                        </Button>
                      )}
                      {canManage &&
                        (g.state === "active" || g.state === "pending") && (
                          <Button
                            onClick={() =>
                              setEnding({ grant: g, action: "revoke" })
                            }
                          >
                            End now
                          </Button>
                        )}
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      {creating && (
        <NewGrantDialog
          onClose={() => setCreating(false)}
          onSaved={() => {
            setCreating(false);
            grants.reload();
          }}
        />
      )}
      {ending && (
        <EndDialog
          grant={ending.grant}
          action={ending.action}
          onClose={() => setEnding(null)}
          onSaved={() => {
            setEnding(null);
            grants.reload();
          }}
        />
      )}
    </>
  );
}

function NewGrantDialog({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const { user: me } = useAuth();
  const people = useApi<User[]>("/users?status=active");
  const catalogue = useApi<GrantablePermission[]>("/grants/permissions");
  const practices = useApi<Practice[]>(
    "/practices?status=active&can=grants.manage",
  );
  const [userId, setUserId] = useState("");
  const [permission, setPermission] = useState("");
  const [practiceId, setPracticeId] = useState("");
  const [reason, setReason] = useState("");
  const [expiresOn, setExpiresOn] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const chosen = catalogue.data?.find((p) => p.key === permission);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api("/grants", {
        method: "POST",
        body: {
          user_id: userId,
          permission,
          practice_id: practiceId || null,
          reason,
          expires_on: expiresOn || null,
        },
      });
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
      setSaving(false);
    }
  }

  return (
    <Dialog
      open
      title="Give a permission"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => void save()}
            disabled={
              saving || !userId || !permission || reason.trim().length < 5
            }
          >
            {saving
              ? "Saving…"
              : chosen?.elevated
                ? "Ask for approval"
                : "Give permission"}
          </Button>
        </>
      }
    >
      <fieldset
        disabled={saving}
        className="grid grid-cols-2 gap-3 max-[560px]:grid-cols-1"
      >
        <Field label="Person">
          <select
            className={cn(selectClass, "w-full")}
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
          >
            <option value="">Choose a person…</option>
            {(people.data ?? [])
              .filter((p) => p.id !== me.id)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.full_name} ({p.role.name})
                </option>
              ))}
          </select>
        </Field>
        <Field
          label="Permission"
          hint="Only permissions you hold yourself can be given."
        >
          <select
            className={cn(selectClass, "w-full")}
            value={permission}
            onChange={(e) => setPermission(e.target.value)}
          >
            <option value="">Choose a permission…</option>
            {(catalogue.data ?? []).map((p) => (
              <option key={p.key} value={p.key}>
                {p.description}
                {p.elevated ? " (elevated)" : ""}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Where">
          <select
            className={cn(selectClass, "w-full")}
            value={practiceId}
            disabled={permission === "scope.all_practices"}
            onChange={(e) => setPracticeId(e.target.value)}
          >
            <option value="">In all their practices</option>
            {(practices.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                Only in {p.name}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label="Ends on (optional)"
          hint="After this date the permission stops working by itself."
        >
          <input
            type="date"
            className={cn(inputClass, "w-full")}
            value={expiresOn}
            onChange={(e) => setExpiresOn(e.target.value)}
          />
        </Field>
        <Field
          label="Reason"
          wide
          hint="Recorded with the grant and in the audit log."
        >
          <textarea
            className={cn(inputClass, "h-auto min-h-20 w-full py-2")}
            value={reason}
            maxLength={500}
            onChange={(e) => setReason(e.target.value)}
          />
        </Field>
      </fieldset>
      {chosen?.elevated && (
        <p className="mt-3 rounded-[9px] bg-warn-soft px-3 py-2.5 text-[12px] text-warn-ink">
          This is an elevated permission. It takes effect only after someone
          else with approval rights approves it, and it must be confirmed every
          90 days.
        </p>
      )}
      <FormError message={error} />
    </Dialog>
  );
}

function EndDialog({
  grant,
  action,
  onClose,
  onSaved,
}: {
  grant: Grant;
  action: "reject" | "revoke";
  onClose: () => void;
  onSaved: () => void;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const title =
    action === "reject" ? "Turn down this request" : "End this permission now";

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api(`/grants/${grant.id}/${action}`, {
        method: "POST",
        body: { reason: reason || null },
      });
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
      setSaving(false);
    }
  }

  return (
    <Dialog
      open
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => void save()}
            disabled={saving}
          >
            {action === "reject" ? "Turn down" : "End now"}
          </Button>
        </>
      }
    >
      <p className="mb-3 text-[12px]">
        {grant.person.name}: {grant.permission_description} (
        {grant.practice?.name ?? "all their practices"})
      </p>
      <Field label="Reason (recorded)">
        <textarea
          className={cn(inputClass, "h-auto min-h-20 w-full py-2")}
          value={reason}
          maxLength={500}
          onChange={(e) => setReason(e.target.value)}
        />
      </Field>
      <FormError message={error} />
    </Dialog>
  );
}
