import { cn } from "@/lib/cn";
import type { Tone } from "@/lib/status";

const TONES: Record<Tone, string> = {
  neutral: "bg-neutral-soft text-ink",
  info: "bg-info-soft text-navy",
  ok: "bg-ok-soft text-ok-ink",
  warn: "bg-warn-soft text-warn-ink",
  danger: "bg-danger-soft text-danger-ink",
};

export function StatusPill({ label, tone = "neutral" }: { label: string; tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-full px-[7px] py-[3px] text-[10px] font-bold",
        TONES[tone],
      )}
    >
      {label}
    </span>
  );
}
