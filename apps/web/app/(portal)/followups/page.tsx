import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/shell/module-placeholder";

export const metadata: Metadata = { title: "Follow-ups" };

export default function FollowUpsPage() {
  return (
    <ModulePlaceholder
      moduleKey="followups"
      subtitle="Follow-ups due across the claims you can see"
      milestone="M3"
      description="Due, upcoming and overdue follow-ups, grouped by date and associate."
    />
  );
}
