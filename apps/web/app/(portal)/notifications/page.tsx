import type { Metadata } from "next";
import { NotificationsPage } from "@/components/notifications/notifications-page";
import { PageBody, PageHeader } from "@/components/shell/page-header";

export const metadata: Metadata = { title: "Notifications" };

export default function Page() {
  return (
    <>
      <PageHeader
        title="Notifications"
        subtitle="Assignments, follow-ups, uploads and changes that concern you"
      />
      <PageBody>
        <NotificationsPage />
      </PageBody>
    </>
  );
}
