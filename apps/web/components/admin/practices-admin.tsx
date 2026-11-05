"use client";

import { useSearchParams } from "next/navigation";
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
import { api, type Practice, type Team, type User } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { getModule, resolveView } from "@/lib/navigation";
import { useApi } from "@/lib/use-api";

export function PracticesAdmin() {
  const view = resolveView(
    getModule("practices"),
    useSearchParams().get("view"),
  ).slug;
  return view === "teams" ? (
    <TeamsTable />
  ) : (
    <PracticesTable status={view === "all" ? null : view} />
  );
}

/* ---- Practices ---- */

function PracticesTable({ status }: { status: string | null }) {
  const { permissions } = useAuth();
  const canManage = permissions.includes("practices.manage");
  const practices = useApi<Practice[]>("/practices");
  const [editing, setEditing] = useState<Practice | "new" | null>(null);
  const rows = (practices.data ?? []).filter(
    (p) => !status || p.status === status,
  );

  return (
    <>
      {canManage && (
        <div className="mb-3 flex">
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => setEditing("new")}
          >
            Add practice
          </Button>
        </div>
      )}
      <Panel flush>
        {practices.error ? (
          <EmptyState
            title="Practices could not be loaded"
            description={practices.error}
          />
        ) : practices.loading ? (
          <p className="p-6 text-muted">Loading practices…</p>
        ) : rows.length === 0 ? (
          <EmptyState
            title="No practices in this view"
            description={
              canManage
                ? "Add the dental practices your team works for."
                : undefined
            }
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="pl-[15px]">Practice</Th>
                <Th>Status</Th>
                <Th className="text-right">People</Th>
                <Th className="text-right">Teams</Th>
                <Th>Notes</Th>
                {canManage && <Th className="pr-[15px] text-right">Action</Th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id}>
                  <Td className="pl-[15px] font-bold">{p.name}</Td>
                  <Td>
                    <StatusPill
                      label={p.status === "active" ? "Active" : "Paused"}
                      tone={p.status === "active" ? "ok" : "warn"}
                    />
                  </Td>
                  <Td className="text-right">{p.user_count}</Td>
                  <Td className="text-right">{p.team_count}</Td>
                  <Td className="max-w-[320px] truncate text-muted">
                    {p.notes || "—"}
                  </Td>
                  {canManage && (
                    <Td className="pr-[15px] text-right">
                      <Button onClick={() => setEditing(p)}>Edit</Button>
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
      {editing !== null && (
        <PracticeDialog
          practice={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            practices.reload();
          }}
        />
      )}
    </>
  );
}

function PracticeDialog({
  practice,
  onClose,
  onSaved,
}: {
  practice: Practice | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(practice?.name ?? "");
  const [notes, setNotes] = useState(practice?.notes ?? "");
  const [importCode, setImportCode] = useState(practice?.import_code ?? "");
  const [status, setStatus] = useState(practice?.status ?? "active");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      if (practice === null) {
        await api("/practices", {
          method: "POST",
          body: { name, notes, import_code: importCode || null },
        });
      } else {
        const changes: Record<string, string> = {};
        if (name !== practice.name) changes.name = name;
        if (notes !== practice.notes) changes.notes = notes;
        if (importCode !== (practice.import_code ?? ""))
          changes.import_code = importCode;
        if (status !== practice.status) changes.status = status;
        if (Object.keys(changes).length > 0) {
          await api(`/practices/${practice.id}`, {
            method: "PATCH",
            body: changes,
          });
        }
      }
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open
      title={practice ? practice.name : "Add practice"}
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
            {saving ? "Saving…" : practice ? "Save changes" : "Add practice"}
          </Button>
        </>
      }
    >
      <fieldset
        disabled={saving}
        className="grid grid-cols-2 gap-3 max-[560px]:grid-cols-1"
      >
        <Field label="Practice name">
          <input
            className={cn(inputClass, "w-full")}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        {practice && (
          <Field
            label="Status"
            hint="Paused practices stay visible but are marked as inactive."
          >
            <select
              className={cn(selectClass, "w-full")}
              value={status}
              onChange={(e) => setStatus(e.target.value as "active" | "paused")}
            >
              <option value="active">Active</option>
              <option value="paused">Paused</option>
            </select>
          </Field>
        )}
        <Field
          label="File name code"
          hint="How this practice’s AR sheets are named, e.g. Irie_Dental. Uploads warn when a file seems to belong to another practice. Leave empty to use the practice name."
        >
          <input
            className={cn(inputClass, "w-full")}
            value={importCode}
            maxLength={60}
            onChange={(e) => setImportCode(e.target.value)}
          />
        </Field>
        <Field label="Notes" wide>
          <textarea
            className={cn(inputClass, "h-auto min-h-24 w-full py-2")}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </Field>
      </fieldset>
      <FormError message={error} />
    </Dialog>
  );
}

/* ---- Teams ---- */

function TeamsTable() {
  const { permissions } = useAuth();
  const canManage = permissions.includes("teams.manage");
  const teams = useApi<Team[]>("/teams");
  const practices = useApi<Practice[]>("/practices");
  const users = useApi<User[]>(
    permissions.includes("users.view") ? "/users?status=active" : null,
  );
  const [editing, setEditing] = useState<Team | "new" | null>(null);
  const rows = teams.data ?? [];

  return (
    <>
      {canManage && (
        <div className="mb-3 flex">
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => setEditing("new")}
          >
            Add team
          </Button>
        </div>
      )}
      <Panel flush>
        {teams.error ? (
          <EmptyState
            title="Teams could not be loaded"
            description={teams.error}
          />
        ) : teams.loading ? (
          <p className="p-6 text-muted">Loading teams…</p>
        ) : rows.length === 0 ? (
          <EmptyState
            title="No teams yet"
            description={
              canManage
                ? "Teams group people under a manager, optionally within one practice."
                : undefined
            }
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="pl-[15px]">Team</Th>
                <Th>Practice</Th>
                <Th>Manager</Th>
                <Th className="text-right">Members</Th>
                {canManage && <Th className="pr-[15px] text-right">Action</Th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id}>
                  <Td className="pl-[15px] font-bold">{t.name}</Td>
                  <Td>{t.practice_name ?? "All practices"}</Td>
                  <Td>{t.manager_name ?? "—"}</Td>
                  <Td className="text-right">{t.member_count}</Td>
                  {canManage && (
                    <Td className="pr-[15px] text-right">
                      <Button onClick={() => setEditing(t)}>Edit</Button>
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
      <p className="mt-2 text-[11px] text-muted">
        Add people to a team from Users › Edit.
      </p>
      {editing !== null && (
        <TeamDialog
          team={editing === "new" ? null : editing}
          practices={practices.data ?? []}
          users={users.data ?? []}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            teams.reload();
          }}
        />
      )}
    </>
  );
}

function TeamDialog({
  team,
  practices,
  users,
  onClose,
  onSaved,
}: {
  team: Team | null;
  practices: Practice[];
  users: User[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(team?.name ?? "");
  const [practiceId, setPracticeId] = useState(team?.practice_id ?? "");
  const [managerId, setManagerId] = useState(team?.manager_user_id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    setError(null);
    const body = {
      name,
      practice_id: practiceId || null,
      manager_user_id: managerId || null,
    };
    try {
      await (team === null
        ? api("/teams", { method: "POST", body })
        : api(`/teams/${team.id}`, { method: "PATCH", body }));
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open
      title={team ? team.name : "Add team"}
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
            {saving ? "Saving…" : team ? "Save changes" : "Add team"}
          </Button>
        </>
      }
    >
      <fieldset
        disabled={saving}
        className="grid grid-cols-2 gap-3 max-[560px]:grid-cols-1"
      >
        <Field label="Team name">
          <input
            className={cn(inputClass, "w-full")}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field
          label="Practice"
          hint="Leave as ‘All practices’ for a team that works across practices."
        >
          <select
            className={cn(selectClass, "w-full")}
            value={practiceId}
            onChange={(e) => setPracticeId(e.target.value)}
          >
            <option value="">All practices</option>
            {practices.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Manager">
          <select
            className={cn(selectClass, "w-full")}
            value={managerId}
            onChange={(e) => setManagerId(e.target.value)}
          >
            <option value="">No manager yet</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name} ({u.role.name})
              </option>
            ))}
          </select>
        </Field>
      </fieldset>
      <FormError message={error} />
    </Dialog>
  );
}
