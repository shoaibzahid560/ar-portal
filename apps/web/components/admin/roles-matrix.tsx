"use client";

import { Fragment, useMemo, useState } from "react";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form";
import { api, type RolesResponse } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";

// The API refuses to remove these from the System Administrator, so they're shown locked.
const ADMIN_LOCKED = new Set([
  "roles.manage",
  "users.manage",
  "users.view",
  "users.manage_owners",
  "scope.all_practices",
]);

type Grants = Record<string, string[]>;

export function RolesMatrix() {
  const { permissions: mine } = useAuth();
  const canEdit = mine.includes("roles.manage");
  const matrix = useApi<RolesResponse>("/roles");
  const [draft, setDraft] = useState<Grants | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  const original = useMemo<Grants>(
    () =>
      Object.fromEntries(
        (matrix.data?.roles ?? []).map((r) => [r.key, r.permissions]),
      ),
    [matrix.data],
  );
  const grants = draft ?? original;
  const changedRoles = Object.keys(grants).filter(
    (role) =>
      [...grants[role]].sort().join() !==
      [...(original[role] ?? [])].sort().join(),
  );
  const modules = useMemo(() => {
    const groups = new Map<string, RolesResponse["permissions"]>();
    for (const p of matrix.data?.permissions ?? [])
      groups.set(p.module, [...(groups.get(p.module) ?? []), p]);
    return [...groups.entries()];
  }, [matrix.data]);

  function toggle(role: string, permission: string) {
    setSaved(false);
    const current = grants[role] ?? [];
    setDraft({
      ...grants,
      [role]: current.includes(permission)
        ? current.filter((p) => p !== permission)
        : [...current, permission],
    });
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      for (const role of changedRoles) {
        await api(`/roles/${role}/permissions`, {
          method: "PUT",
          body: { permissions: grants[role] },
        });
      }
      setDraft(null);
      setSaved(true);
      matrix.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  if (matrix.error)
    return (
      <EmptyState
        title="Roles could not be loaded"
        description={matrix.error}
      />
    );
  if (!matrix.data) return <p className="text-muted">Loading roles…</p>;
  const roles = matrix.data.roles;

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <p className="text-[12px] text-muted">
          Changes apply on each person’s next action. Every change is recorded
          in the audit log.
        </p>
        {canEdit && (
          <div className="ml-auto flex gap-2">
            <Button
              onClick={() => setDraft(null)}
              disabled={saving || changedRoles.length === 0}
            >
              Discard
            </Button>
            <Button
              variant="primary"
              onClick={() => void save()}
              disabled={saving || changedRoles.length === 0}
            >
              {saving
                ? "Saving…"
                : `Save changes${changedRoles.length ? ` (${changedRoles.length})` : ""}`}
            </Button>
          </div>
        )}
      </div>
      {saved && (
        <p
          role="status"
          className="mb-3 rounded-[9px] bg-ok-soft px-3 py-2.5 text-[12px] text-ok-ink"
        >
          Permissions saved.
        </p>
      )}
      <FormError message={error} />
      <Panel flush className="mt-3">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[12px]">
            <thead>
              <tr>
                <th className="border-b border-line px-3 py-2.5 text-left text-[10px] font-semibold tracking-[0.04em] text-[#7b818c] uppercase">
                  Permission
                </th>
                {roles.map((r) => (
                  <th
                    key={r.key}
                    title={r.description}
                    className="border-b border-line px-2 py-2.5 text-center text-[11px] font-bold"
                  >
                    {r.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {modules.map(([module, perms]) => (
                <Fragment key={module}>
                  <tr>
                    <td
                      colSpan={roles.length + 1}
                      className="bg-[#f7f8fa] px-3 py-1.5 text-[10px] font-extrabold tracking-[0.08em] text-[#8a909b] uppercase"
                    >
                      {module}
                    </td>
                  </tr>
                  {perms.map((p) => (
                    <tr key={p.key} className="hover:bg-[#fafbfc]">
                      <td className="border-b border-[#f0f1f3] px-3 py-2">
                        <p className="font-semibold">{p.description}</p>
                        <p className="font-mono text-[10px] text-muted">
                          {p.key}
                        </p>
                      </td>
                      {roles.map((r) => {
                        const locked =
                          r.key === "system_admin" && ADMIN_LOCKED.has(p.key);
                        return (
                          <td
                            key={r.key}
                            className="border-b border-[#f0f1f3] px-2 py-2 text-center"
                          >
                            <input
                              type="checkbox"
                              aria-label={`${r.name}: ${p.description}`}
                              title={
                                locked
                                  ? "The System Administrator always keeps this permission."
                                  : undefined
                              }
                              checked={(grants[r.key] ?? []).includes(p.key)}
                              disabled={!canEdit || locked || saving}
                              onChange={() => toggle(r.key, p.key)}
                              className="size-4 accent-brand"
                            />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
