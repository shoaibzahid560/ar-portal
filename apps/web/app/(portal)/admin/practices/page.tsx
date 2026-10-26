import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/shell/module-placeholder";

export const metadata: Metadata = { title: "Practices" };

export default function PracticesPage() {
  return (
    <ModulePlaceholder
      moduleKey="practices"
      subtitle="Practices and teams"
      milestone="M0"
      description="Create practices and teams and choose which employees can see each one."
    />
  );
}
