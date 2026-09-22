import { api } from "@/lib/api";
import { Icon, Money, Shell } from "./components";
import {
  CustomerChart, MetricCard, PeriodPoint, ProductSalesChart, ProductSeries, RevenueChart,
} from "./dashboard-charts";

type Analytics = {
  available_years: number[]; selected_year: number; selected_month?: number;
  window: "year" | "quarter"; grain: "month" | "day";
  period_start: string; period_end: string;
  summary: {
    revenue: string; order_count: number; average_order_value: string; active_customers: number;
    repeat_customers: number; new_customers: number; revenue_change?: number | null;
    order_change?: number | null; new_customer_change?: number | null;
  };
  periods: PeriodPoint[]; products: ProductSeries[];
};

const months = ["January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"];

export default async function DashboardPage({ searchParams }: {
  searchParams: Promise<{ year?: string; month?: string; view?: string }>;
}) {
  const params = await searchParams;
  const parsedYear = Number(params.year);
  const legacyMonth = Number(params.month);
  const view = params.view || (
    Number.isInteger(legacyMonth) && legacyMonth >= 1 && legacyMonth <= 12
      ? "month-" + legacyMonth : "year"
  );
  const query = new URLSearchParams();
  if (Number.isInteger(parsedYear) && parsedYear >= 2000 && parsedYear <= 2099) {
    query.set("year", String(parsedYear));
  }
  if (view === "quarter") {
    query.set("window", "quarter");
  } else if (view.startsWith("month-")) {
    const selectedMonth = Number(view.slice(6));
    if (Number.isInteger(selectedMonth) && selectedMonth >= 1 && selectedMonth <= 12) {
      query.set("month", String(selectedMonth));
    }
  }
  const data = await api<Analytics>("/admin/analytics?" + query.toString());
  const periodName = data.selected_month
    ? months[data.selected_month - 1] + " " + data.selected_year
    : data.window === "quarter"
      ? data.periods[0].label + " - " + data.periods[data.periods.length - 1].label +
        " " + data.selected_year
      : String(data.selected_year);
  const bestPeriod = data.periods.reduce((best, point) =>
    Number(point.revenue) > Number(best.revenue) ? point : best, data.periods[0]);
  const grainLabel = data.grain === "month" ? "month" : "day";

  return <Shell title="Executive dashboard"
    subtitle={"Revenue, customers and product performance for " + periodName}>
    <section className="executive-toolbar">
      <div><span className="section-kicker">Business pulse</span>
        <h2>{periodName} performance</h2><p>All figures update from processed orders.</p></div>
      <form className="period-filter">
        <label><span>Financial year</span><select name="year" defaultValue={data.selected_year}>
          {data.available_years.map(year => <option key={year} value={year}>{year}</option>)}
        </select></label>
        <label><span>View</span><select name="view"
          defaultValue={data.selected_month ? "month-" + data.selected_month : data.window}>
          <option value="year">Full year - monthly</option>
          <option value="quarter">Last 3 months - monthly</option>
          {months.map((month, index) => <option value={"month-" + (index + 1)} key={month}>
            {month + " - daily"}</option>)}
        </select></label>
        <button className="button primary"><Icon name="calendar" size={17} />Apply period</button>
      </form>
    </section>

    <section className="metric-grid executive-grid">
      <MetricCard label="Net revenue" value={<Money value={data.summary.revenue} compact />}
        icon="rupee" change={data.summary.revenue_change} detail="vs previous period" />
      <MetricCard label="Orders" value={data.summary.order_count.toLocaleString("en-IN")}
        icon="bag" change={data.summary.order_change} detail="processed sales" tone="blue" />
      <MetricCard label="Average order value" value={<Money value={data.summary.average_order_value} />}
        icon="trend" detail="revenue per order" tone="gold" />
      <MetricCard label="Active customers" value={data.summary.active_customers.toLocaleString("en-IN")}
        icon="users" detail="buyers in this period" tone="plum" />
      <MetricCard label="New customers" value={data.summary.new_customers.toLocaleString("en-IN")}
        icon="spark" change={data.summary.new_customer_change} detail="first purchase in period" />
      <MetricCard label="Repeat buyers" value={data.summary.repeat_customers.toLocaleString("en-IN")}
        icon="repeat" detail="more than one order" tone="gold" />
    </section>

    <section className="dashboard-chart-grid">
      <article className="panel chart-card revenue-card"><div className="chart-heading"><div>
        <span className="section-kicker">Revenue trajectory</span><h2>Revenue by {grainLabel}</h2>
        <p>Order value booked across the selected period.</p></div>
        <div className="chart-highlight"><span>Best {grainLabel}</span>
          <strong>{bestPeriod?.label || "-"}</strong>
          <small><Money value={bestPeriod?.revenue || 0} compact /></small></div></div>
        <RevenueChart points={data.periods} />
      </article>
      <article className="panel chart-card"><div className="chart-heading"><div>
        <span className="section-kicker">Acquisition</span><h2>New customers</h2>
        <p>Customers grouped by their first purchase {grainLabel}.</p></div>
        <span className="chart-icon"><Icon name="users" size={24} /></span></div>
        <CustomerChart points={data.periods} />
      </article>
    </section>

    <section className="panel product-performance"><div className="chart-heading"><div>
      <span className="section-kicker">Product intelligence</span>
      <h2>{data.grain === "month" ? "Month-wise" : "Day-wise"} product sales</h2>
      <p>Top five products ranked by item revenue, with period contribution and units sold.</p></div>
      <span className="chart-icon gold"><Icon name="package" size={24} /></span></div>
      <ProductSalesChart points={data.periods} products={data.products} />
    </section>
  </Shell>;
}
