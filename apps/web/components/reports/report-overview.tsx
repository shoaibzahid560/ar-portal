"use client";

import Link from "next/link";
import { useState } from "react";
import { EmptyState } from "@/components/data/empty-state";
import { MetricCard } from "@/components/data/metric-card";
import { Panel } from "@/components/data/panel";
import { selectClass } from "@/components/ui/form";
import type { Practice, ReportOverview } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatMoney } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { Bars } from "./bars";

const ALERT_STYLE = {
  danger: "bg-danger-soft text-danger-ink",
  warn: "bg-warn-soft text-warn-ink",
  info: "bg-info-soft",
};

/** The AR performance dashboard (brief section 6): open work, aging, recovery, practices and workload. */
export function ReportOverviewPanel() {
  const [practice, setPractice] = useState("");
  const practices = useApi<Practice[]>("/practices?status=active");
  const data = useApi<ReportOverview>(
    `/reports/overview${practice ? `?practice_id=${practice}` : ""}`,
  );
  const o = data.data;

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select
          aria-label="Practice"
          className={selectClass}
          value={practice}
          onChange={(e) => setPractice(e.target.value)}
        >
          <option value="">All practices I can see</option>
          {(practices.data ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <Link
          href="/reports?view=run"
          className="ml-auto text-[12px] font-semibold text-brand"
        >
          Run a report or download one
        </Link>
      </div>

      {data.error ? (
        <EmptyState
          title="The dashboard could not be loaded"
          description={data.error}
        />
      ) : !o ? (
        <p className="text-muted">Loading…</p>
      ) : (
        <>
          {o.alerts.length > 0 && (
            <div className="mb-3 grid gap-1.5">
              {o.alerts.map((a) => (
                <p
                  key={a.text}
                  className={cn(
                    "rounded-[9px] px-3 py-2.5 text-[12px]",
                    ALERT_STYLE[a.tone],
                  )}
                >
                  {a.text}{" "}
                  {a.link && (
                    <Link href={a.link} className="font-bold underline">
                      Open
                    </Link>
                  )}
                </p>
              ))}
            </div>
          )}
          <section className="mb-3 grid grid-cols-4 gap-2.5 max-[1000px]:grid-cols-2">
            <MetricCard
              label="Open claims"
              value={o.open_claims.toLocaleString("en-US")}
              meta={`${formatMoney(o.open_unrecovered)} not yet recovered`}
            />
            <MetricCard
              label="Recovered this month"
              value={formatMoney(o.recovered_this_month)}
              meta={`${formatMoney(o.recovered_total)} recovered in total`}
            />
            <MetricCard
              label="Follow-ups"
              value={`${o.due_today} due, ${o.overdue} overdue`}
              meta="Open claims only"
            />
            <MetricCard
              label="Over 90 days"
              value={`${o.over_90_pct}%`}
              meta={`of open claims; target at most ${o.targets.aging_over_90_pct}%`}
            />
          </section>
          <div className="grid grid-cols-2 gap-3 max-[1000px]:grid-cols-1">
            <Panel
              title="Aging of open claims"
              action={<span className="text-muted">Unrecovered (claims)</span>}
            >
              <Bars
                bars={o.aging}
                value={(b) => b.count}
                show={(b) => `${formatMoney(b.amount)} (${b.count})`}
              />
            </Panel>
            <Panel
              title="Recovered by month"
              action={
                <span className="text-muted">By payment posted date</span>
              }
            >
              <Bars
                bars={o.recovered_by_month}
                value={(b) => Number(b.amount)}
                show={(b) => formatMoney(b.amount)}
                empty="No payments recorded in the last six months."
              />
            </Panel>
            <Panel title="Open claims by status">
              <Bars
                bars={o.by_status}
                value={(b) => b.count}
                show={(b) => String(b.count)}
              />
            </Panel>
            <Panel
              title="Open claims by practice"
              action={<span className="text-muted">Unrecovered (claims)</span>}
            >
              <Bars
                bars={o.by_practice}
                value={(b) => b.count}
                show={(b) => `${formatMoney(b.amount)} (${b.count})`}
              />
            </Panel>
            {o.workload && (
              <Panel
                title="Workload"
                action={
                  <span className="text-muted">
                    Open claims, with overdue follow-ups in red
                  </span>
                }
              >
                <Bars
                  bars={o.workload}
                  value={(b) => b.count}
                  show={(b) => String(b.count)}
                  note={(b) => (b.secondary ? `${b.secondary} overdue` : null)}
                  empty="No open claims are assigned yet."
                />
              </Panel>
            )}
            <Panel title="This month">
              <dl className="grid grid-cols-2 gap-y-2 text-[12px]">
                <dt className="text-muted">Closed</dt>
                <dd className="text-right font-semibold">
                  {o.closed_this_month}
                </dd>
                <dt className="text-muted">Awaiting completion review</dt>
                <dd className="text-right font-semibold">
                  {o.awaiting_completion}
                </dd>
                <dt className="text-muted">Open billed amount</dt>
                <dd className="text-right font-semibold">
                  {formatMoney(o.open_billed)}
                </dd>
              </dl>
            </Panel>
          </div>
        </>
      )}
    </>
  );
}
