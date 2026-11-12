import type { ReportBar } from "@/lib/api";

/**
 * Horizontal bars, scaled to the largest value. Each row reads label, bar, value, so the numbers stay
 * legible without a chart library.
 */
export function Bars({
  bars,
  value,
  show,
  note,
  empty = "Nothing to show yet.",
}: {
  bars: ReportBar[];
  value: (bar: ReportBar) => number;
  show: (bar: ReportBar) => string;
  note?: (bar: ReportBar) => string | null;
  empty?: string;
}) {
  const max = Math.max(0, ...bars.map(value));
  if (bars.length === 0 || max === 0)
    return <p className="text-[12px] text-muted">{empty}</p>;
  return (
    <ul className="grid gap-2">
      {bars.map((bar) => (
        <li
          key={bar.label}
          className="grid grid-cols-[minmax(90px,30%)_1fr_auto] items-center gap-3"
        >
          <span className="truncate text-[12px]" title={bar.label}>
            {bar.label}
          </span>
          <span className="h-2.5 rounded-full bg-[#E5E7ED]" aria-hidden="true">
            <span
              className="block h-2.5 rounded-full bg-brand"
              style={{
                width: `${Math.max((value(bar) / max) * 100, value(bar) > 0 ? 2 : 0)}%`,
              }}
            />
          </span>
          <span className="text-right text-[12px] font-semibold tabular-nums">
            {show(bar)}
            {note?.(bar) && (
              <span className="ml-1.5 font-normal text-danger-ink">
                {note(bar)}
              </span>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}
