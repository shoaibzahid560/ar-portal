"use client";

import { useSearchParams } from "next/navigation";
import { getModule, resolveView } from "@/lib/navigation";
import { ExportHistory } from "./export-history";
import { ReportOverviewPanel } from "./report-overview";
import { RunReport } from "./run-report";

/** The Reports screen: dashboard, report runner, productivity, data quality and export history. */
export function ReportsSection() {
  const view = resolveView(
    getModule("reports"),
    useSearchParams().get("view"),
  ).slug;
  switch (view) {
    case "run":
      return <RunReport />;
    case "productivity":
      return <RunReport fixed="productivity" />;
    case "data-quality":
      return <RunReport fixed="uploads" />;
    case "exports":
      return <ExportHistory />;
    default:
      return <ReportOverviewPanel />;
  }
}
