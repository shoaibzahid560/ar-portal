import type { ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

/**
 * Dense table primitives matching the current portal. Large lists move to
 * TanStack Table with server-side paging when real data arrives (M3).
 */
export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse [&_tbody_tr:last-child_td]:border-b-0">
        {children}
      </table>
    </div>
  );
}

export function Th({
  className,
  ...props
}: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "border-b border-line px-2 py-2 text-left text-[10px] font-semibold tracking-[0.04em] whitespace-nowrap text-[#7b818c] uppercase",
        className,
      )}
      {...props}
    />
  );
}

export function Td({
  className,
  ...props
}: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      className={cn(
        "border-b border-[#f0f1f3] px-2 py-[9px] text-[12px]",
        className,
      )}
      {...props}
    />
  );
}
