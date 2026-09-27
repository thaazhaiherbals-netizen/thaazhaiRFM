export function orderDateRange(period: string, now = new Date()): { start: string; end: string } | undefined {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata",
    year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  const date = new Date(`${today}T00:00:00Z`);
  const iso = (value: Date) => value.toISOString().slice(0, 10);
  if (period === "today") return { start: today, end: today };
  if (period === "yesterday") {
    date.setUTCDate(date.getUTCDate() - 1);
    return { start: iso(date), end: iso(date) };
  }
  if (period === "week") {
    date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7);
    return { start: iso(date), end: today };
  }
  if (period === "month") {
    date.setUTCDate(1);
    return { start: iso(date), end: today };
  }
}
