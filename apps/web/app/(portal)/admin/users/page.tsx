import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/shell/module-placeholder";

export const metadata: Metadata = { title: "Users" };

export default function UsersPage() {
  return (
    <ModulePlaceholder
      moduleKey="users"
      subtitle="Employee access and roles"
      milestone="M0"
      description="Add employees, set their role, practices and teams, and deactivate accounts."
    />
  );
}
