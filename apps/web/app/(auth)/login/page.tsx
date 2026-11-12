import type { Metadata } from "next";
import { Suspense } from "react";
import { APP_MONOGRAM, APP_NAME } from "@/lib/config";

export const metadata: Metadata = { title: "Sign in" };

/** Messages for /login?error=<code>. The codes come from the API's sign-in routes. */
const MESSAGES: Record<string, { text: string; kind: "error" | "info" }> = {
  not_registered: {
    kind: "error",
    text: "This Google account isn’t registered for the portal, or it has been deactivated. Ask your administrator to add you.",
  },
  domain: {
    kind: "error",
    text: "Please sign in with your company Google account.",
  },
  state: {
    kind: "error",
    text: "The sign-in took too long or was interrupted. Please try again.",
  },
  google: {
    kind: "error",
    text: "Google didn’t complete the sign-in. Please try again.",
  },
  signed_out: { kind: "info", text: "You’ve been signed out." },
};

export default function LoginPage({ searchParams }: PageProps<"/login">) {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[linear-gradient(115deg,#ffd8b7_0%,#f8e3e4_42%,#eaf2ff_100%)] p-4">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-[150px] -left-[130px] size-[420px] rounded-full bg-[#fff4e9] opacity-30"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -right-[190px] -bottom-[220px] size-[520px] rounded-full bg-[#dcecff] opacity-30"
      />

      <div className="relative w-full max-w-[430px] rounded-[22px] border border-white/90 bg-white/85 px-8 pt-9 pb-8 text-center shadow-[0_28px_80px_rgba(21,35,55,0.16)] backdrop-blur-lg">
        <div className="mx-auto mb-4 flex size-[72px] items-center justify-center rounded-2xl bg-navy text-[24px] font-extrabold text-white shadow-[0_8px_24px_rgba(11,29,51,0.16)]">
          {APP_MONOGRAM}
        </div>
        <h1 className="text-[26px] font-extrabold tracking-[-0.6px] text-navy">
          {APP_NAME}
        </h1>
        <p className="mt-2 mb-6 text-[12px] leading-relaxed text-[#6d7583]">
          Sign in with your company Google account.
        </p>

        <a
          href="/api/auth/google/login"
          className="flex h-[46px] w-full items-center justify-center gap-2.5 rounded-[11px] bg-navy font-extrabold text-white shadow-[0_7px_18px_rgba(11,29,51,0.18)] hover:bg-navy-2"
        >
          <span
            aria-hidden
            className="flex size-6 items-center justify-center rounded-full bg-white text-[13px] font-extrabold text-brand"
          >
            G
          </span>
          Sign in with Google
        </a>
        <p className="mt-4 text-[12px] text-[#6d7583]">
          A client of ours?{" "}
          <a
            href="/api/auth/google/login?client=true"
            className="font-bold text-brand underline"
          >
            Client sign-in
          </a>{" "}
          with the Google account we invited.
        </p>

        <Suspense>
          {searchParams.then((params) => {
            const code = typeof params.error === "string" ? params.error : "";
            const message = MESSAGES[code];
            if (!message) return null;
            return (
              <p
                role={message.kind === "error" ? "alert" : "status"}
                className={
                  message.kind === "error"
                    ? "mt-3 rounded-[9px] bg-[#fff0f1] px-2.5 py-2.5 text-left text-[11px] text-danger-ink"
                    : "mt-3 rounded-[9px] bg-[#edf9f2] px-2.5 py-2.5 text-left text-[11px] text-ok-ink"
                }
              >
                {message.text}
              </p>
            );
          })}
        </Suspense>

        <p className="mt-5 border-t border-navy/10 pt-4 text-[10px] leading-relaxed text-[#7a818c]">
          Access is limited to registered employees. Every sign-in is recorded.
        </p>
      </div>
    </main>
  );
}
