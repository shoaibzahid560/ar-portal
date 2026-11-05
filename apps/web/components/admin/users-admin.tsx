"use client";

import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { GrantsAdmin } from "@/components/admin/grants-admin";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { StatusPill } from "@/components/data/status-pill";
import { Table, Td, Th } from "@/components/data/table";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import {
  CheckboxGrid,
  Field,
  FieldGroup,
  FormError,
  inputClass,
  selectClass,
} from "@/components/ui/form";
import {
  api,
  type Practice,
  type Role,
  type RolesResponse,
  type Team,
  type User,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { getModule, resolveView } from "@/lib/navigation";
import type { Tone } from "@/lib/status";
import { useApi } from "@/lib/use-api";

const STATUS_TONE: Record<User["status"], Tone> = {
  active: "ok",
  paused: "warn",
  deactivated: "neutral",
};
const STATUS_LABEL: Record<User["status"], string> = {
  active: "Active",
  paused: "Paused",
  deactivated: "Deactivated",
};

/** The Users screen: the people list, or the Access Grants view. */
export function UsersSection() {
  const view = resolveView(
    getModule("users"),
    useSearchParams().get("view"),
  ).slug;
  return view === "grants" ? <GrantsAdmin /> : <UsersAdmin />;
}

function UsersAdmin() {
  const view = resolveView(
    getModule("users"),
    useSearchParams().get("view"),
  ).slug;
  const { user: me, permissions } = useAuth();
  const canManage = permissions.includes("users.manage");
  const canSeePractices = permissions.includes("practices.view");

  const users = useApi<User[]>("/users");
  const roles = useApi<RolesResponse>("/roles");
  const practices = useApi<Practice[]>(canSeePractices ? "/practices" : null);
  const teams = useApi<Team[]>(canSeePractices ? "/teams" : null);

  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<User | "new" | null>(null);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (users.data ?? []).filter(
      (u) =>
        (view === "all" || u.status === view) &&
        (!q ||
          [u.full_name, u.email, u.employee_code ?? ""].some((v) =>
            v.toLowerCase().includes(q),
          )),
    );
  }, [users.data, view, query]);

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search name, email or employee code..."
          aria-label="Search users"
          className={cn(inputClass, "min-w-[270px]")}
        />
        <span className="text-[12px] text-muted">
          {users.data ? `${rows.length} shown` : ""}
        </span>
        {canManage && (
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => setEditing("new")}
          >
            Add user
          </Button>
        )}
      </div>

      <Panel flush>
        {users.error ? (
          <EmptyState
            title="Users could not be loaded"
            description={users.error}
          />
        ) : users.loading ? (
          <p className="p-6 text-muted">Loading users…</p>
        ) : rows.length === 0 ? (
          <EmptyState
            title="No users in this view"
            description="Try another view or clear the search."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="pl-[15px]">Employee</Th>
                <Th>Code</Th>
                <Th>Roles</Th>
                <Th>Practices</Th>
                <Th>Teams</Th>
                <Th>Status</Th>
                <Th>Last sign-in</Th>
                {canManage && <Th className="pr-[15px] text-right">Action</Th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.id} className="hover:bg-[#fafbfc]">
                  <Td className="pl-[15px]">
                    <p className="font-bold">{u.full_name}</p>
                    <p className="text-muted">{u.email}</p>
                  </Td>
                  <Td>{u.employee_code ?? "—"}</Td>
                  <Td>
                    <p>{u.role.name}</p>
                    {u.extra_roles.map((r) => (
                      <p
                        key={`${r.role.key}-${r.practice?.id ?? "all"}`}
                        className="text-[11px] text-muted"
                      >
                        + {r.role.name}
                        {r.practice ? ` (${r.practice.name})` : ""}
                      </p>
                    ))}
                    {u.grants.map((g, i) => (
                      <p
                        key={`grant-${i}`}
                        className="text-[11px] text-warn-ink"
                      >
                        + {g.permission}
                        {g.practice ? ` (${g.practice.name})` : ""}
                      </p>
                    ))}
                  </Td>
                  <Td>{u.practices.map((p) => p.name).join(", ") || "—"}</Td>
                  <Td>{u.teams.map((t) => t.name).join(", ") || "—"}</Td>
                  <Td>
                    <StatusPill
                      label={STATUS_LABEL[u.status]}
                      tone={STATUS_TONE[u.status]}
                    />
                  </Td>
                  <Td className="whitespace-nowrap">
                    {formatDateTime(u.last_login_at)}
                  </Td>
                  {canManage && (
                    <Td className="pr-[15px] text-right">
                      <Button onClick={() => setEditing(u)}>
                        {u.status === "deactivated" ? "View" : "Edit"}
                      </Button>
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      {editing !== null && roles.data && (
        <UserDialog
          user={editing === "new" ? null : editing}
          roles={roles.data.roles}
          practices={practices.data ?? []}
          teams={teams.data ?? []}
          isMe={editing !== "new" && editing.id === me.id}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            users.reload();
          }}
        />
      )}
    </>
  );
}

function sameIds(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((id) => b.includes(id));
}

function UserDialog({
  user,
  roles,
  practices,
  teams,
  isMe,
  onClose,
  onSaved,
}: {
  user: User | null;
  roles: Role[];
  practices: Practice[];
  teams: Team[];
  isMe: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isNew = user === null;
  const locked = user?.status === "deactivated";
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [employeeCode, setEmployeeCode] = useState(user?.employee_code ?? "");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [roleKey, setRoleKey] = useState(user?.role.key ?? "ar_associate");
  const [status, setStatus] = useState<"active" | "paused">(
    user?.status === "paused" ? "paused" : "active",
  );
  const [practiceIds, setPracticeIds] = useState(
    user?.practices.map((p) => p.id) ?? [],
  );
  const [teamIds, setTeamIds] = useState(user?.teams.map((t) => t.id) ?? []);
  const startExtra: ExtraRole[] = (user?.extra_roles ?? []).map((r) => ({
    role_key: r.role.key,
    practice_id: r.practice?.id ?? "",
  }));
  const [extraRoles, setExtraRoles] = useState<ExtraRole[]>(startExtra);
  const extraChanged =
    JSON.stringify(extraRoles) !== JSON.stringify(startExtra);
  const rolesBody = {
    roles: extraRoles
      .filter((r) => r.role_key)
      .map((r) => ({
        role_key: r.role_key,
        practice_id: r.practice_id || null,
      })),
  };
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);

  async function run(action: () => Promise<unknown>) {
    setSaving(true);
    setError(null);
    try {
      await action();
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  function save() {
    void run(async () => {
      if (isNew) {
        const created = await api<User>("/users", {
          method: "POST",
          body: {
            email,
            full_name: fullName,
            employee_code: employeeCode || null,
            phone: phone || null,
            role_key: roleKey,
            practice_ids: practiceIds,
            team_ids: teamIds,
          },
        });
        if (rolesBody.roles.length > 0) {
          await api(`/users/${created.id}/roles`, {
            method: "PUT",
            body: rolesBody,
          });
        }
        return;
      }
      const changes: Record<string, unknown> = {};
      if (fullName !== user.full_name) changes.full_name = fullName;
      if ((employeeCode || null) !== user.employee_code)
        changes.employee_code = employeeCode || null;
      if ((phone || null) !== user.phone) changes.phone = phone || null;
      if (roleKey !== user.role.key) changes.role_key = roleKey;
      if (status !== user.status) changes.status = status;
      if (Object.keys(changes).length > 0)
        await api(`/users/${user.id}`, { method: "PATCH", body: changes });
      if (extraChanged) {
        await api(`/users/${user.id}/roles`, {
          method: "PUT",
          body: rolesBody,
        });
      }
      if (
        !sameIds(
          practiceIds,
          user.practices.map((p) => p.id),
        )
      ) {
        await api(`/users/${user.id}/practices`, {
          method: "PUT",
          body: { ids: practiceIds },
        });
      }
      if (
        !sameIds(
          teamIds,
          user.teams.map((t) => t.id),
        )
      ) {
        await api(`/users/${user.id}/teams`, {
          method: "PUT",
          body: { ids: teamIds },
        });
      }
    });
  }

  const footer = locked ? (
    <Button onClick={onClose}>Close</Button>
  ) : confirmDeactivate && user ? (
    <>
      <Button onClick={() => setConfirmDeactivate(false)} disabled={saving}>
        Keep account
      </Button>
      <Button
        className="border-danger bg-danger text-white hover:bg-danger-ink"
        disabled={saving}
        onClick={() =>
          void run(() =>
            api(`/users/${user.id}/deactivate`, { method: "POST" }),
          )
        }
      >
        Yes, deactivate
      </Button>
    </>
  ) : (
    <>
      {!isNew && !isMe && (
        <Button
          className="mr-auto text-danger-ink"
          onClick={() => setConfirmDeactivate(true)}
          disabled={saving}
        >
          Deactivate…
        </Button>
      )}
      <Button onClick={onClose} disabled={saving}>
        Cancel
      </Button>
      <Button
        variant="primary"
        onClick={save}
        disabled={saving || !fullName.trim() || !email.trim()}
      >
        {saving ? "Saving…" : isNew ? "Add user" : "Save changes"}
      </Button>
    </>
  );

  return (
    <Dialog
      open
      title={isNew ? "Add user" : user.full_name}
      onClose={onClose}
      footer={footer}
    >
      {locked && (
        <p className="mb-4 rounded-[9px] bg-neutral-soft px-3 py-2.5 text-[12px]">
          This account is deactivated and can’t sign in. Deactivation is
          permanent; add a new account if the person returns.
        </p>
      )}
      {confirmDeactivate && user && (
        <p
          role="alert"
          className="mb-4 rounded-[9px] bg-danger-soft px-3 py-2.5 text-[12px] text-danger-ink"
        >
          Deactivate {user.full_name}? They’ll be signed out everywhere
          immediately, and the account can’t be reactivated. Their history stays
          in the audit log.
        </p>
      )}
      <fieldset
        disabled={locked || saving || confirmDeactivate}
        className="grid grid-cols-2 gap-3 max-[560px]:grid-cols-1"
      >
        <Field label="Full name">
          <input
            className={cn(inputClass, "w-full")}
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />
        </Field>
        <Field
          label="Google sign-in email"
          hint={isNew ? "The exact address they sign in with." : undefined}
        >
          <input
            className={cn(inputClass, "w-full")}
            type="email"
            value={email}
            disabled={!isNew}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label="Employee code">
          <input
            className={cn(inputClass, "w-full")}
            value={employeeCode}
            onChange={(e) => setEmployeeCode(e.target.value)}
          />
        </Field>
        <Field label="Phone">
          <input
            className={cn(inputClass, "w-full")}
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </Field>
        <Field
          label="Primary role"
          hint={isMe ? "You can’t change your own role." : undefined}
        >
          <select
            className={cn(selectClass, "w-full")}
            value={roleKey}
            disabled={isMe}
            onChange={(e) => setRoleKey(e.target.value)}
          >
            {roles.map((r) => (
              <option key={r.key} value={r.key}>
                {r.name}
              </option>
            ))}
          </select>
        </Field>
        {!isNew && !locked && (
          <Field
            label="Status"
            hint={
              isMe
                ? "You can’t pause your own account."
                : "Paused people can’t sign in until made active again."
            }
          >
            <select
              className={cn(selectClass, "w-full")}
              value={status}
              disabled={isMe}
              onChange={(e) => setStatus(e.target.value as "active" | "paused")}
            >
              <option value="active">Active</option>
              <option value="paused">Paused</option>
            </select>
          </Field>
        )}
        <FieldGroup label="Additional roles">
          <ExtraRolesEditor
            value={extraRoles}
            onChange={setExtraRoles}
            roles={roles.filter((r) => r.key !== "system_admin")}
            practices={practices}
          />
        </FieldGroup>
        <FieldGroup label="Practices they can see">
          <CheckboxGrid
            items={practices}
            selected={practiceIds}
            onChange={setPracticeIds}
            empty="No practices yet. Add them under Practices."
          />
        </FieldGroup>
        <FieldGroup label="Teams">
          <CheckboxGrid
            items={teams}
            selected={teamIds}
            onChange={setTeamIds}
            empty="No teams yet. Add them under Practices › Teams."
          />
        </FieldGroup>
      </fieldset>
      <FormError message={error} />
    </Dialog>
  );
}

type ExtraRole = { role_key: string; practice_id: string };

/**
 * Roles on top of the primary one: for all the person's practices, or for one practice
 * (e.g. Practice Manager / AR Lead in one practice, AR Associate everywhere else).
 */
function ExtraRolesEditor({
  value,
  onChange,
  roles,
  practices,
}: {
  value: ExtraRole[];
  onChange: (rows: ExtraRole[]) => void;
  roles: Role[];
  practices: Practice[];
}) {
  const set = (index: number, patch: Partial<ExtraRole>) =>
    onChange(value.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  return (
    <div className="grid gap-2">
      <p className="text-[11px] text-muted">
        Use these when someone has a different role in one practice, or a second
        job such as Claim Importer. A role for one practice applies in that
        practice only; their primary role doesn’t extend there.
      </p>
      {value.map((row, index) => (
        <div key={index} className="flex flex-wrap items-center gap-2">
          <select
            aria-label={`Additional role ${index + 1}`}
            className={cn(selectClass, "min-w-[220px] flex-1")}
            value={row.role_key}
            onChange={(e) => set(index, { role_key: e.target.value })}
          >
            <option value="">Choose a role…</option>
            {roles.map((r) => (
              <option key={r.key} value={r.key}>
                {r.name}
              </option>
            ))}
          </select>
          <select
            aria-label={`Where additional role ${index + 1} applies`}
            className={cn(selectClass, "min-w-[200px] flex-1")}
            value={row.practice_id}
            onChange={(e) => set(index, { practice_id: e.target.value })}
          >
            <option value="">In all their practices</option>
            {practices.map((p) => (
              <option key={p.id} value={p.id}>
                Only in {p.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => onChange(value.filter((_, i) => i !== index))}
            className="text-[11px] font-semibold text-danger-ink"
          >
            Remove
          </button>
        </div>
      ))}
      <div>
        <Button
          type="button"
          onClick={() =>
            onChange([...value, { role_key: "", practice_id: "" }])
          }
        >
          Add a role
        </Button>
      </div>
    </div>
  );
}
