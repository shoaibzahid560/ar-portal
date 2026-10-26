import { EmptyState } from "@/components/data/empty-state";
import { Panel } from "@/components/data/panel";
import { getModule } from "@/lib/navigation";
import { PageBody, PageHeader } from "./page-header";

/** Holds the place of a module that is built in a later milestone. */
export function ModulePlaceholder({
  moduleKey,
  subtitle,
  milestone,
  description,
}: {
  moduleKey: string;
  subtitle: string;
  milestone: string;
  description: string;
}) {
  const navModule = getModule(moduleKey);
  return (
    <>
      <PageHeader title={navModule.title} subtitle={subtitle} />
      <PageBody>
        <Panel>
          <EmptyState title={`${navModule.title} is built in ${milestone}`} description={description} />
        </Panel>
      </PageBody>
    </>
  );
}
