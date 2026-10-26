import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/shell/module-placeholder";

export const metadata: Metadata = { title: "Audit" };

export default function AuditPage() {
  return (
    <ModulePlaceholder
      moduleKey="audit"
      subtitle="Claim timelines, field changes and access history"
      milestone="M4"
      description="Every change to a claim, with who made it, when, and the values before and after."
    />
  );
}
