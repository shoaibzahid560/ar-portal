export function MetricCard({
  label,
  value,
  meta,
}: {
  label: string;
  value: string;
  meta?: string;
}) {
  return (
    <div className="rounded-[9px] border border-line bg-white p-3.5">
      <p className="text-[11px] text-muted">{label}</p>
      <p className="mt-1.5 text-[25px] leading-none font-extrabold">{value}</p>
      {meta && <p className="mt-2 text-[10px] text-muted">{meta}</p>}
    </div>
  );
}
