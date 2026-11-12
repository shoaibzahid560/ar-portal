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
  FieldGroup,
  FormError,
  inputClass,
  selectClass,
} from "@/components/ui/form";
import {
  api,
  CLIENT_REPORTS,
  type ClientOrg,
  type ClientUser,
  type NamedRef,
  type Practice,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/use-api";

/**
 * The portal team's view of client organisations (specification, sections 2 to 5): the practices each
 * owns, the reports approved for it, whether its reports show patient names, whether its admin manages its
 * own users, and its client accounts.
 */
export function ClientsAdmin() {
  const orgs = useApi<ClientOrg[]>("/clients");
  const [editing, setEditing] = useState<ClientOrg | "new" | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const chosen = orgs.data?.find((o) => o.id === selected) ?? null;

  return (
    <>
      <div className="mb-3 flex items-center gap-2">
        <p className="text-[12px] text-muted">
          Client accounts see only their organisation&apos;s practices and the
          reports approved here. They never see internal notes, staff names,
          queues or import details.
        </p>
        <Button
          variant="primary"
          className="ml-auto"
          onClick={() => setEditing("new")}
        >
          New client
        </Button>
      </div>
      <Panel flush>
        {orgs.error ? (
          <EmptyState
            title="Clients could not be loaded"
            description={orgs.error}
          />
        ) : !orgs.data ? (
          <p className="p-6 text-muted">Loading…</p>
        ) : orgs.data.length === 0 ? (
          <EmptyState
            title="No clients yet"
            description="Add a client organisation to give its staff reports."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="pl-[15px]">Client</Th>
                <Th>Practices</Th>
                <Th>Approved reports</Th>
                <Th>Patient names</Th>
                <Th>Client admin adds users</Th>
                <Th className="text-right">Accounts</Th>
                <Th>Status</Th>
                <Th className="pr-[15px] text-right">Action</Th>
              </tr>
            </thead>
            <tbody>
              {orgs.data.map((o) => (
                <tr
                  key={o.id}
                  className={cn(
                    "align-top",
                    o.id === selected && "bg-brand-soft/40",
                  )}
                >
                  <Td className="pl-[15px] font-bold">{o.name}</Td>
                  <Td className="text-[12px]">
                    {o.practices.map((p) => p.name).join(", ") || "None yet"}
                  </Td>
                  <Td className="text-[12px]">
                    {o.reports.map((r) => CLIENT_REPORTS[r]).join(", ") ||
                      "None yet"}
                  </Td>
                  <Td>
                    {o.patient_detail ? (
                      <StatusPill label="Shown" tone="warn" />
                    ) : (
                      "Hidden"
                    )}
                  </Td>
                  <Td>{o.users_delegated ? "Yes" : "No"}</Td>
                  <Td className="text-right">{o.user_count}</Td>
                  <Td>
                    <StatusPill
                      label={o.status === "active" ? "Active" : "Paused"}
                      tone={o.status === "active" ? "ok" : "neutral"}
                    />
                  </Td>
                  <Td className="pr-[15px] text-right whitespace-nowrap">
                    <button
                      type="button"
                      className="mr-3 font-semibold text-brand"
                      onClick={() => setSelected(o.id)}
                    >
                      Accounts
                    </button>
                    <button
                      type="button"
                      className="font-semibold text-brand"
                      onClick={() => setEditing(o)}
                    >
                      Edit
                    </button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      {chosen && <ClientAccounts org={chosen} onChanged={orgs.reload} />}

      {editing && (
        <OrgDialog
          org={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setEditing(null);
            setSelected(saved.id);
            orgs.reload();
          }}
        />
      )}
    </>
  );
}

function OrgDialog({
  org,
  onClose,
  onSaved,
}: {
  org: ClientOrg | null;
  onClose: () => void;
  onSaved: (org: ClientOrg) => void;
}) {
  const practices = useApi<Practice[]>("/practices");
  const [name, setName] = useState(org?.name ?? "");
  const [notes, setNotes] = useState(org?.notes ?? "");
  const [status, setStatus] = useState(org?.status ?? "active");
  const [practiceIds, setPracticeIds] = useState<string[]>(
    org?.practices.map((p) => p.id) ?? [],
  );
  const [reports, setReports] = useState<string[]>(
    org?.reports ?? ["statement", "aging", "recovery"],
  );
  const [patientDetail, setPatientDetail] = useState(
    org?.patient_detail ?? false,
  );
  const [delegated, setDelegated] = useState(org?.users_delegated ?? false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const toggle = (list: string[], value: string) =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

  async function save() {
    setSaving(true);
    setError(null);
    const body = {
      name,
      notes,
      practice_ids: practiceIds,
      reports,
      patient_detail: patientDetail,
      users_delegated: delegated,
    };
    try {
      const saved = org
        ? await api<ClientOrg>(`/clients/${org.id}`, {
            method: "PATCH",
            body: { ...body, status },
          })
        : await api<ClientOrg>("/clients", { method: "POST", body });
      onSaved(saved);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
      setSaving(false);
    }
  }

  return (
    <Dialog
      open
      title={org ? `Edit ${org.name}` : "New client"}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => void save()}
            disabled={saving || !name.trim()}
          >
            {saving ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      <fieldset
        disabled={saving}
        className="grid grid-cols-2 gap-3 max-[560px]:grid-cols-1"
      >
        <Field label="Client name">
          <input
            className={cn(inputClass, "w-full")}
            value={name}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        {org && (
          <Field
            label="Status"
            hint="Paused clients can't sign in; they are signed out at once."
          >
            <select
              className={cn(selectClass, "w-full")}
              value={status}
              onChange={(e) => setStatus(e.target.value as "active")}
            >
              <option value="active">Active</option>
              <option value="paused">Paused</option>
            </select>
          </Field>
        )}
        <FieldGroup label="Practices this client owns">
          <div className="grid grid-cols-2 gap-1.5">
            {(practices.data ?? []).map((p) => (
              <label key={p.id} className="flex items-center gap-2 text-[12px]">
                <input
                  type="checkbox"
                  checked={practiceIds.includes(p.id)}
                  onChange={() => setPracticeIds(toggle(practiceIds, p.id))}
                />
                {p.name}
              </label>
            ))}
          </div>
        </FieldGroup>
        <FieldGroup label="Approved reports">
          <div className="grid gap-1.5">
            {Object.entries(CLIENT_REPORTS).map(([key, title]) => (
              <label key={key} className="flex items-center gap-2 text-[12px]">
                <input
                  type="checkbox"
                  checked={reports.includes(key)}
                  onChange={() => setReports(toggle(reports, key))}
                />
                {title}
              </label>
            ))}
          </div>
        </FieldGroup>
        <FieldGroup label="Patient detail">
          <label className="flex items-start gap-2 text-[12px]">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={patientDetail}
              onChange={(e) => setPatientDetail(e.target.checked)}
            />
            <span>
              Show patient names and subscriber IDs in this client&apos;s AR
              statement. Off by default; changing it is recorded and Management
              is told.
            </span>
          </label>
        </FieldGroup>
        <FieldGroup label="User management">
          <label className="flex items-start gap-2 text-[12px]">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={delegated}
              onChange={(e) => setDelegated(e.target.checked)}
            />
            <span>
              Let this client&apos;s Reporting Admin add and deactivate their
              own Client Reporting Users (only for this client&apos;s
              practices).
            </span>
          </label>
        </FieldGroup>
        <Field label="Notes" wide>
          <textarea
            className={cn(inputClass, "h-auto min-h-16 w-full py-2")}
            value={notes}
            maxLength={2000}
            onChange={(e) => setNotes(e.target.value)}
          />
        </Field>
      </fieldset>
      <FormError message={error} />
    </Dialog>
  );
}

/**
 * Client accounts of one organisation. Used by the portal team (base "/clients/{id}") and by a delegated
 * Client Reporting Admin for their own organisation (base "/client-portal").
 */
export function ClientAccounts({
  org,
  base,
  practices,
  canAddAdmin = true,
  onChanged,
}: {
  org?: ClientOrg;
  base?: string;
  practices?: NamedRef[];
  canAddAdmin?: boolean;
  onChanged?: () => void;
}) {
  const root = base ?? `/clients/${org?.id}`;
  const users = useApi<ClientUser[]>(`${root}/users`);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const choices = practices ?? org?.practices ?? [];

  async function act(path: string, body?: unknown) {
    setError(null);
    try {
      await api(path, { method: body ? "PATCH" : "POST", body: body ?? {} });
      users.reload();
      onChanged?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
    }
  }

  return (
    <Panel
      flush
      className="mt-3"
      title={org ? `${org.name}: client accounts` : "Client accounts"}
      action={
        <Button
          variant="primary"
          onClick={() => setAdding(true)}
          disabled={choices.length === 0}
        >
          Add account
        </Button>
      }
    >
      <FormError message={error} />
      {!users.data ? (
        <p className="p-6 text-muted">Loading…</p>
      ) : users.data.length === 0 ? (
        <EmptyState
          title="No accounts yet"
          description="Client staff sign in with their own Google account, using the email added here."
        />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th className="pl-[15px]">Name</Th>
              <Th>Google sign-in email</Th>
              <Th>Role</Th>
              <Th>Practices</Th>
              <Th>Last sign-in</Th>
              <Th>Status</Th>
              <Th className="pr-[15px] text-right">Action</Th>
            </tr>
          </thead>
          <tbody>
            {users.data.map((u) => (
              <tr key={u.id}>
                <Td className="pl-[15px] font-bold">{u.full_name}</Td>
                <Td>{u.email}</Td>
                <Td>{u.role.name}</Td>
                <Td className="text-[12px]">
                  {u.practices.map((p) => p.name).join(", ")}
                </Td>
                <Td className="text-[12px]">
                  {u.last_login_at ? formatDateTime(u.last_login_at) : "Never"}
                </Td>
                <Td>
                  <StatusPill
                    label={
                      {
                        active: "Active",
                        paused: "Paused",
                        deactivated: "Deactivated",
                      }[u.status]
                    }
                    tone={u.status === "active" ? "ok" : "neutral"}
                  />
                </Td>
                <Td className="pr-[15px] text-right whitespace-nowrap">
                  {u.status === "active" && (
                    <button
                      type="button"
                      className="mr-3 font-semibold text-brand"
                      onClick={() =>
                        void act(`${root}/users/${u.id}`, { status: "paused" })
                      }
                    >
                      Pause
                    </button>
                  )}
                  {u.status === "paused" && (
                    <button
                      type="button"
                      className="mr-3 font-semibold text-brand"
                      onClick={() =>
                        void act(`${root}/users/${u.id}`, { status: "active" })
                      }
                    >
                      Make active
                    </button>
                  )}
                  {u.status !== "deactivated" && (
                    <button
                      type="button"
                      className="font-semibold text-danger-ink"
                      onClick={() =>
                        void act(`${root}/users/${u.id}/deactivate`)
                      }
                    >
                      Deactivate
                    </button>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {adding && (
        <AccountDialog
          root={root}
          practices={choices}
          canAddAdmin={canAddAdmin}
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            users.reload();
            onChanged?.();
          }}
        />
      )}
    </Panel>
  );
}

function AccountDialog({
  root,
  practices,
  canAddAdmin,
  onClose,
  onSaved,
}: {
  root: string;
  practices: NamedRef[];
  canAddAdmin: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState(
    canAddAdmin ? "client_admin" : "client_user",
  );
  const [picked, setPicked] = useState<string[]>(practices.map((p) => p.id));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api(`${root}/users`, {
        method: "POST",
        body: { email, full_name: name, role_key: role, practice_ids: picked },
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
      title="Add a client account"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => void save()}
            disabled={saving || !email || !name || picked.length === 0}
          >
            {saving ? "Saving…" : "Add account"}
          </Button>
        </>
      }
    >
      <fieldset
        disabled={saving}
        className="grid grid-cols-2 gap-3 max-[560px]:grid-cols-1"
      >
        <Field label="Full name">
          <input
            className={cn(inputClass, "w-full")}
            value={name}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field
          label="Google sign-in email"
          hint="They sign in with this Google account, using Client sign-in."
        >
          <input
            type="email"
            className={cn(inputClass, "w-full")}
            value={email}
            maxLength={254}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label="Role">
          <select
            className={cn(selectClass, "w-full")}
            value={role}
            onChange={(e) => setRole(e.target.value)}
          >
            {canAddAdmin && (
              <option value="client_admin">Client Reporting Admin</option>
            )}
            <option value="client_user">Client Reporting User</option>
          </select>
        </Field>
        <FieldGroup label="Practices they can see">
          <div className="grid gap-1.5">
            {practices.map((p) => (
              <label key={p.id} className="flex items-center gap-2 text-[12px]">
                <input
                  type="checkbox"
                  checked={picked.includes(p.id)}
                  onChange={() =>
                    setPicked(
                      picked.includes(p.id)
                        ? picked.filter((x) => x !== p.id)
                        : [...picked, p.id],
                    )
                  }
                />
                {p.name}
              </label>
            ))}
          </div>
        </FieldGroup>
      </fieldset>
      <FormError message={error} />
    </Dialog>
  );
}
