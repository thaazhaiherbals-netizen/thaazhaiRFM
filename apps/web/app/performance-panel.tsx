import Link from "next/link";
import { api } from "@/lib/api";
import "./performance.css";

type Value = string | number | null;
type Metric = { current: Value; previous: Value;
  change: { absolute: Value; percent: Value; state: string } };
type Day = { day: string; revenue: Value; orders: number };
type Performance = {
  period: string; timezone: string; generated_at: string; latest_order_date: string | null;
  order_note: string;
  window: { current_start: string; current_end: string | null;
    previous_start: string; previous_end: string | null; days: number; partial: boolean; note: string };
  metrics: Record<string, Metric>; insights: string[];
  daily: { current: Day; previous: Day }[];
  meta: null | { currency: string | null; last_data_date: string | null;
    current_coverage: { unsynced_days: number }; previous_coverage: { unsynced_days: number } };
};
const choices = [["today", "Today"], ["yesterday", "Yesterday"], ["week", "This week"], ["month", "This month"]];
const fields = [
  ["revenue", "Recorded sales", "money", "Sum of order values; not net profit"],
  ["orders", "Orders", "count", "Processed orders in the selected dates"],
  ["aov", "Average order value", "money", "Recorded sales / orders"],
  ["new_customers", "New customers", "count", "First purchase in available history"],
  ["repeat_revenue", "Returning-customer sales", "money", "Orders after the customer's first purchase date"],
  ["spend", "Meta ad spend", "money", "Unavailable when any selected day is unsynced"],
  ["mer", "Sales per ₹1 of Meta spend", "ratio", "All recorded sales / Meta spend; not profit"],
  ["spend_per_new_customer", "Meta spend per new customer", "money", "Blended indicator; not attributed or fully loaded CAC"],
  ["meta_roas", "Meta-reported ROAS", "ratio", "Meta-attributed purchase value / spend"],
];
function format(value: Value, kind: string, currency = "INR"): string {
  if (value === null) return "—";
  const amount = Number(value);
  if (kind === "ratio") return amount.toFixed(2) + "×";
  return new Intl.NumberFormat("en-IN", kind === "money"
    ? { style: "currency", currency, maximumFractionDigits: 0 }
    : { maximumFractionDigits: 0 }).format(amount);
}
function dateLabel(date: string | null) {
  return date ? new Date(date + "T00:00:00+05:30").toLocaleDateString("en-IN", {
    day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata",
  }) : "No completed days";
}
export async function PerformancePanel({ period, preserved }: {
  period: string; preserved: Record<string, string>;
}) {
  let data: Performance;
  try { data = await api<Performance>("/admin/performance?period=" + encodeURIComponent(period)); }
  catch {
    return <section className="panel performance-panel"><h2>Business comparison unavailable</h2>
      <p>The comparison report could not load. Existing sales reports remain below. Try refreshing.</p></section>;
  }
  const w = data.window;
  return <section className="performance-panel" aria-labelledby="performance-title">
    <div className="performance-heading"><div><span className="section-kicker">Sales + marketing</span>
      <h2 id="performance-title">How is the business performing?</h2>
      <p>Compare orders, customers and advertising on matching dates.</p></div>
      <span className="performance-clock">India time · {w.partial ? "In progress" : "Completed days"}</span>
    </div>
    <nav className="performance-tabs" aria-label="Business comparison period">
      {choices.map(([key, label]) => <Link key={key}
        href={"?" + new URLSearchParams({ ...preserved, compare: key })}
        aria-current={period === key ? "page" : undefined}>{label}</Link>)}
    </nav>
    <div className="performance-periods">
      <div><small>Current period</small><strong>{dateLabel(w.current_start)}
        {w.current_end && w.current_end !== w.current_start ? " – " + dateLabel(w.current_end) : ""}</strong></div>
      <span>compared with</span>
      <div><small>Previous period</small><strong>{dateLabel(w.previous_start)}
        {w.previous_end && w.previous_end !== w.previous_start ? " – " + dateLabel(w.previous_end) : ""}</strong></div>
    </div>
    <p className="footnote">{w.note || "Two completed calendar days."} {w.days > 0 && !w.partial
      ? w.days + " day(s) in each period." : ""}</p>
    <div className="performance-freshness" role="status">
      <strong>Data coverage</strong>
      <p>Latest recorded order: {dateLabel(data.latest_order_date)}. {data.order_note}</p>
      {data.meta && <p>Meta data through {dateLabel(data.meta.last_data_date)}.
        {" "}Unsynced days: {data.meta.current_coverage.unsynced_days} current /
        {" "}{data.meta.previous_coverage.unsynced_days} previous.
        {data.meta.currency && data.meta.currency !== "INR"
          ? " Meta uses " + data.meta.currency + "; cross-currency sales/spend ratios are unavailable." : ""}</p>}
      {w.partial && <p>Meta normally syncs through yesterday. Today is not a same-time-of-day comparison.</p>}
    </div>
    {w.days === 0 ? <p className="panel">{w.note}</p> : <>
      <div className="performance-grid">{fields.map(([key, label, kind, detail]) => {
        const metric = data.metrics[key];
        const change = metric.change;
        const currency = key === "spend" ? data.meta?.currency || "INR" : "INR";
        const scale = Math.max(Number(metric.current || 0), Number(metric.previous || 0), 1);
        return <article className="panel performance-metric" key={key}>
          <h3>{label}</h3><strong className="performance-value">{format(metric.current, kind, currency)}</strong>
          <p>Previous: <b>{format(metric.previous, kind, currency)}</b></p>
          <div className="performance-bars" aria-hidden="true">
            <i style={{ width: (Number(metric.current || 0) / scale * 100) + "%" }} />
            <i style={{ width: (Number(metric.previous || 0) / scale * 100) + "%" }} />
          </div>
          <span className="performance-change">{change.state === "unavailable"
            ? w.partial ? "Provisional · no percentage verdict" : "Comparison unavailable"
            : change.state === "no_baseline" ? "No percentage baseline (previous was zero)"
            : (Number(change.percent) > 0 ? "+" : "") + Number(change.percent).toFixed(1) + "%"}
            {change.absolute !== null && <> · {Number(change.absolute) > 0 ? "+" : ""}
              {format(change.absolute, kind, currency)}</>}</span>
          <small>{detail}</small>
        </article>;
      })}</div>
      <div className="panel performance-insights"><span className="section-kicker">What the numbers suggest</span>
        <h3>Signals to investigate</h3>
        <ul>{data.insights.map(message => <li key={message}>{message}</li>)}</ul>
        <p className="footnote">These observations use available records. Check source completeness before
          treating a change as a business trend. No campaign-to-order attribution is implied.</p>
      </div>
      <details className="panel performance-details"><summary>Daily comparison · inspect the evidence</summary>
        <div className="table-wrap"><table><thead><tr><th>Current date</th><th>Sales</th><th>Orders</th>
          <th>Previous date</th><th>Sales</th><th>Orders</th></tr></thead><tbody>
          {data.daily.map(({ current, previous }) => <tr key={current.day}>
            <td>{dateLabel(current.day)}</td><td>{format(current.revenue, "money")}</td><td>{current.orders}</td>
            <td>{dateLabel(previous.day)}</td><td>{format(previous.revenue, "money")}</td><td>{previous.orders}</td>
          </tr>)}</tbody></table></div>
      </details>
    </>}
  </section>;
}
