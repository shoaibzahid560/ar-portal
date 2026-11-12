import type { ReportColumn } from "@/lib/api";
import { formatDate, formatDateTime, formatMoney } from "@/lib/format";

/** A report value as it reads on screen, matching the PDF and Excel files. */
export function formatCell(
  column: ReportColumn,
  value: string | number | null | undefined,
): string {
  if (value === null || value === undefined || value === "") return "";
  switch (column.kind) {
    case "date":
      return formatDate(String(value));
    case "datetime":
      return formatDateTime(String(value));
    case "money":
      return formatMoney(value);
    case "percent":
      return `${Number(value).toFixed(1)}%`;
    case "int":
      return Number(value).toLocaleString("en-US");
    default:
      return String(value);
  }
}

export const NUMERIC = new Set(["money", "int", "percent"]);
