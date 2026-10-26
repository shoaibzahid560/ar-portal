import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/** White card with an optional heading. Use `flush` when a table should run edge to edge. */
export function Panel({
  title,
  action,
  flush = false,
  className,
  children,
}: {
  title?: string;
  action?: ReactNode;
  flush?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={cn(
        "overflow-hidden rounded-[9px] border border-line bg-white",
        !flush && "p-[15px]",
        className,
      )}
    >
      {title && (
        <div className={cn("mb-3 flex items-center gap-3", flush && "px-[15px] pt-[15px]")}>
          <h2 className="text-[13px] font-bold">{title}</h2>
          {action && <div className="ml-auto text-[12px]">{action}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
