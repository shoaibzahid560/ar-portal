import type { Metadata } from "next";
import "@fontsource-variable/inter"; // self-hosted Inter: no request to Google at build or run time
import { APP_NAME } from "@/lib/config";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: APP_NAME, template: `%s | ${APP_NAME}` },
  description: "Claim uploads, assignments, follow-ups, audit trail and reporting.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
