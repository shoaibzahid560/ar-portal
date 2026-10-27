import type { Metadata } from "next";
import { Suspense } from "react";
import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { StatusPill } from "@/components/data/status-pill";
import { Table, Td, Th } from "@/components/data/table";
import { PageBody, PageHeader } from "@/components/shell/page-header";
import { Button, LinkButton } from "@/components/ui/button";
import { inputClass, selectClass } from "@/components/ui/form";
import { cn } from "@/lib/cn";
import { formatDate, formatMoney } from "@/lib/format";
import { getModule, resolveView, viewHref } from "@/lib/navigation";
import {
  SAMPLE_CLAIMS,
  SAMPLE_PRACTICES,
  claimMatchesView,
  isOverdue,
} from "@/lib/sample-data";
import { CLAIM_STATUSES, type ClaimStatus } from "@/lib/status";

export const metadata: Metadata = { title: "Claims" };

type SearchParams = Record<string, string | string[] | undefined>;

const text = (value: string | string[] | undefined) =>
  typeof value === "string" ? value : "";

export default function ClaimsPage({ searchParams }: PageProps<"/claims">) {
  return (
    <>
      <PageHeader
        title="Claims"
        subtitle="Work queues for every claim in your scope"
      />
      <PageBody>
        <Suspense fallback={<Panel>Loading claims…</Panel>}>
          {searchParams.then((params) => (
            <ClaimsView params={params} />
          ))}
        </Suspense>
      </PageBody>
    </>
  );
}

function ClaimsView({ params }: { params: SearchParams }) {
  const claimsModule = getModule("claims");
  const view = resolveView(claimsModule, text(params.view));
  const query = text(params.q).trim().toLowerCase();
  const status = text(params.status);
  const practice = text(params.practice);

  // Sample filtering. In M3 these filters become query parameters on GET /api/claims.
  const rows = SAMPLE_CLAIMS.filter(
    (c) =>
      claimMatchesView(c, view.slug) &&
      (!status || c.status === status) &&
      (!practice || c.practice === practice) &&
      (!query ||
        [c.id, c.patient, c.practice, c.payer].some((field) =>
          field.toLowerCase().includes(query),
        )),
  );

  return (
    <>
      <form className="mb-3 flex flex-wrap items-center gap-2">
        <input type="hidden" name="view" value={view.slug} />
        <input
          name="q"
          defaultValue={text(params.q)}
          placeholder="Search claim, patient, payer..."
          aria-label="Search claims"
          className={cn(inputClass, "min-w-[270px]")}
        />
        <select
          name="status"
          defaultValue={status}
          aria-label="Status"
          className={selectClass}
        >
          <option value="">All statuses</option>
          {(Object.keys(CLAIM_STATUSES) as ClaimStatus[]).map((s) => (
            <option key={s} value={s}>
              {CLAIM_STATUSES[s].label}
            </option>
          ))}
        </select>
        <select
          name="practice"
          defaultValue={practice}
          aria-label="Practice"
          className={selectClass}
        >
          <option value="">All practices</option>
          {SAMPLE_PRACTICES.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <Button type="submit">Apply filters</Button>
      </form>

      <Panel flush>
        {rows.length === 0 ? (
          <EmptyState
            title="No claims match these filters"
            description="Try a different search, or clear the filters to see every claim in this view."
            action={
              <LinkButton href={viewHref(claimsModule, view)}>
                Clear filters
              </LinkButton>
            }
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="pl-[15px]">Claim</Th>
                <Th>Patient</Th>
                <Th>Practice</Th>
                <Th>Payer</Th>
                <Th>Date of service</Th>
                <Th className="text-right">Balance</Th>
                <Th>Assigned to</Th>
                <Th>Follow-up</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className="hover:bg-[#fafbfc]">
                  <Td className="pl-[15px] font-bold whitespace-nowrap">
                    {c.id}
                  </Td>
                  <Td>{c.patient}</Td>
                  <Td>{c.practice}</Td>
                  <Td>{c.payer}</Td>
                  <Td className="whitespace-nowrap">
                    {formatDate(c.dateOfService)}
                  </Td>
                  <Td className="text-right">{formatMoney(c.balance)}</Td>
                  <Td className={cn(!c.assignedTo && "text-muted")}>
                    {c.assignedTo ?? "Unassigned"}
                  </Td>
                  <Td
                    className={cn(
                      "whitespace-nowrap",
                      isOverdue(c) && "font-bold text-danger-ink",
                    )}
                  >
                    {formatDate(c.followUp)}
                  </Td>
                  <Td>
                    <StatusPill
                      label={CLAIM_STATUSES[c.status].label}
                      tone={CLAIM_STATUSES[c.status].tone}
                    />
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
      <p className="mt-2 text-[11px] text-muted">
        Showing {rows.length} of {SAMPLE_CLAIMS.length} sample claims.
      </p>
    </>
  );
}
