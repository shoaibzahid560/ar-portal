import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/shell/module-placeholder";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <ModulePlaceholder
      moduleKey="settings"
      subtitle="System configuration"
      milestone="M0"
      description="Session limits, retention rules and other settings that apply to everyone."
    />
  );
}
