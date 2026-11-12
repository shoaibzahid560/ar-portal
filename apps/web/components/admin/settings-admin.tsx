"use client";

import { useSearchParams } from "next/navigation";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { getModule, resolveView } from "@/lib/navigation";
import { ListsEditor } from "./lists-editor";
import { ReportTargetsForm } from "./report-targets";
import { RolesMatrix } from "./roles-matrix";

export function SettingsAdmin() {
  const view = resolveView(
    getModule("settings"),
    useSearchParams().get("view"),
  ).slug;
  if (view === "roles") return <RolesMatrix />;
  if (view === "lists") return <ListsEditor />;
  if (view === "targets") return <ReportTargetsForm />;
  return (
    <Panel>
      <EmptyState
        title="General settings arrive with later modules"
        description="Retention periods (management decision #4) and notification options are added with later modules."
      />
    </Panel>
  );
}
