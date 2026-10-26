import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/shell/module-placeholder";

export const metadata: Metadata = { title: "Review Queue" };

export default function ReviewQueuePage() {
  return (
    <ModulePlaceholder
      moduleKey="review"
      subtitle="Resolve possible duplicates and conflicting values"
      milestone="M2"
      description="Rows the matching rules can't settle automatically will wait here for a person to decide."
    />
  );
}
