"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

export type Me = {
  user: { id: string; email: string; full_name: string; employee_code: string | null; phone: string | null };
  role: { key: string; name: string };
  permissions: string[];
  practices: { id: string; name: string }[];
  teams: { id: string; name: string }[];
};

type State = { kind: "loading" } | { kind: "ready"; me: Me } | { kind: "unreachable" };

const AuthContext = createContext<Me | null>(null);

/**
 * Loads the signed-in person from GET /api/auth/me before showing the portal.
 * No session sends the browser to /login. The API still checks permissions on every request;
 * this only decides what to draw.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(() => {
    fetch("/api/auth/me", { cache: "no-store" })
      .then(async (response) => {
        if (response.status === 401) {
          window.location.replace("/login");
          return;
        }
        if (!response.ok) throw new Error(String(response.status));
        setState({ kind: "ready", me: (await response.json()) as Me });
      })
      .catch(() => setState({ kind: "unreachable" }));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (state.kind === "ready") return <AuthContext value={state.me}>{children}</AuthContext>;

  return (
    <div className="flex h-screen items-center justify-center bg-canvas p-6">
      {state.kind === "loading" ? (
        <p role="status" className="text-muted">
          Loading the portal…
        </p>
      ) : (
        <div role="alert" className="max-w-sm rounded-[9px] border border-line bg-white p-6 text-center">
          <p className="mb-1 font-semibold">The portal can’t reach its server</p>
          <p className="mb-4 text-muted">Check that the API is running, then try again.</p>
          <button
            type="button"
            onClick={() => {
              setState({ kind: "loading" });
              load();
            }}
            className="rounded-[7px] border border-brand bg-brand px-3 py-2 text-[12px] font-semibold text-white"
          >
            Try again
          </button>
        </div>
      )}
    </div>
  );
}

/** The signed-in person. Only usable inside the portal, below AuthProvider. */
export function useAuth(): Me {
  const me = useContext(AuthContext);
  if (!me) throw new Error("useAuth must be used inside <AuthProvider>");
  return me;
}

export async function signOut(): Promise<void> {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } finally {
    window.location.replace("/login?error=signed_out");
  }
}
