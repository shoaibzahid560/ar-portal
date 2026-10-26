import type { ReactNode } from "react";

/** Title row at the top of the workspace (title, subtitle, actions on the right). */
export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="flex min-h-[60px] shrink-0 items-center gap-3 border-b border-line bg-white px-[18px] py-2">
      <div className="min-w-0">
        <h1 className="text-[20px] leading-tight font-bold">{title}</h1>
        {subtitle && <p className="mt-0.5 text-[11px] text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="ml-auto flex shrink-0 gap-[7px]">{actions}</div>}
    </div>
  );
}

/** Scrollable grey area below the page header. */
export function PageBody({ children }: { children: ReactNode }) {
  return <div className="min-h-0 flex-1 overflow-auto bg-canvas p-[18px]">{children}</div>;
}
