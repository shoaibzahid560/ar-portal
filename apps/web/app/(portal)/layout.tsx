import { Suspense, type ReactNode } from "react";
import { NavRail } from "@/components/shell/nav-rail";
import {
  SecondaryPanel,
  SecondaryPanelFallback,
} from "@/components/shell/secondary-panel";
import { TopBar } from "@/components/shell/top-bar";
import { AuthProvider } from "@/lib/auth";

/** Three-pane shell, shown only to signed-in people: top bar, icon rail, secondary panel, workspace. */
export default function PortalLayout({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <div className="flex h-screen flex-col overflow-hidden">
        <TopBar />
        <div className="flex min-h-0 flex-1">
          <NavRail />
          <Suspense fallback={<SecondaryPanelFallback />}>
            <SecondaryPanel />
          </Suspense>
          <main className="flex min-w-0 flex-1 flex-col bg-white">
            {children}
          </main>
        </div>
      </div>
    </AuthProvider>
  );
}
