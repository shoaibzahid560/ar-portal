import type { ActivityItem } from "@/lib/sample-data";
import { StatusPill } from "./status-pill";

export function ActivityList({ items }: { items: ActivityItem[] }) {
  if (items.length === 0) {
    return <p className="py-10 text-center text-muted">No activity recorded yet.</p>;
  }
  return (
    <ul>
      {items.map((item) => (
        <li
          key={item.id}
          className="flex items-start justify-between gap-2.5 border-b border-[#f0f1f3] p-2.5 last:border-b-0"
        >
          <div className="min-w-0">
            <p className="text-[12px] font-bold">{item.title}</p>
            <p className="mt-0.5 truncate text-[10px] text-muted">
              {item.detail} · {item.when}
            </p>
          </div>
          <StatusPill label={item.pill.label} tone={item.pill.tone} />
        </li>
      ))}
    </ul>
  );
}
