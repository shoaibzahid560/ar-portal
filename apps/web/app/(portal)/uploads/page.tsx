import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/shell/module-placeholder";

export const metadata: Metadata = { title: "Uploads" };

export default function UploadsPage() {
  return (
    <ModulePlaceholder
      moduleKey="uploads"
      subtitle="Import Dentrix AR reports and check validation results"
      milestone="M1"
      description="Each upload will list its row counts, validation errors and reconciliation results."
    />
  );
}
