const dateFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

const moneyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

/** "2026-10-26" -> "26 Oct 2026" (dates are stored as plain calendar dates) */
export function formatDate(isoDate: string | null): string {
  if (!isoDate) return "—";
  return dateFormatter.format(new Date(`${isoDate}T00:00:00Z`));
}

export function formatMoney(amount: number): string {
  return moneyFormatter.format(amount);
}

export function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}
