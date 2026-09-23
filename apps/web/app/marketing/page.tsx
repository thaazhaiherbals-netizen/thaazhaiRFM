import Link from "next/link";
import { api, Page } from "@/lib/api";
import { currentRole } from "@/lib/auth";
import { syncMarketing } from "../actions";
import { Icon, Pager, Shell, SortLink, Status } from "../components";
import { MetricCard } from "../dashboard-charts";
import { Amount, count, DailyPoint, ratio, SpendRevenueChart, Totals } from "./marketing-ui";

type Run = {
  id: string; status: string; trigger: string; date_from: string; date_to: string;
  started_at: string; finished_at: string | null; error_summary: string | null;
};
type Overview = {
  date_from: string; date_to: string; is_stale: boolean;
  coverage: { total_days: number; unsynced_days: number; first_unsynced: string | null; last_unsynced: string | null };
  context: {
    configured: boolean; attribution_key: string | null;
    account: { name: string | null; currency: string | null; timezone_name: string | null } | null;
    last_successful_sync: { finished_at: string } | null; latest_run: Run | null;
    last_data_date: string | null;
  };
  meta: Totals;
  business: { orders: number; revenue: string; new_customers: number };
  blended: { mer: string | null; spend_per_order: string | null; new_customer_cac: string | null };
  daily: DailyPoint[];
  unclassified_actions: { action_type: string; rows: number }[];
};
type Campaign = Totals & { id: string; name: string; objective: string | null };
type SyncRun = Run & {
  row_count: number; page_count: number; normalized_spend: string | null;
  control_spend: string | null; control_difference: string | null;
};

const sorts = ["spend", "impressions", "link_clicks", "ctr", "cpc", "cpm", "meta_purchases", "meta_roas", "name"];
const isoDate = /^\d{4}-\d{2}-\d{2}$/;
const MAX_SYNC_DAYS = 400;

function spanDays(from: string, to: string) {
  return Math.round((Date.parse(to) - Date.parse(from)) / 86_400_000) + 1;
}

export default async function Marketing({ searchParams }: {
  searchParams: Promise<{
    date_from?: string; date_to?: string; sort?: string; direction?: string; offset?: string;
    synced?: string; sync_error?: string;
  }>;
}) {
  const params = await searchParams;
  const range = new URLSearchParams();
  if (isoDate.test(params.date_from || "")) range.set("date_from", params.date_from!);
  if (isoDate.test(params.date_to || "")) range.set("date_to", params.date_to!);
  const sort = sorts.includes(params.sort || "") ? params.sort! : "spend";
  const direction = params.direction === "asc" ? "asc" : "desc";
  const offset = Math.max(0, Number(params.offset) || 0), limit = 25;
  const [data, campaigns, runs, role] = await Promise.all([
    api<Overview>(`/admin/marketing/overview?${range}`),
    api<Page<Campaign>>(`/admin/marketing/campaigns?${range}&sort=${sort}&direction=${direction}&limit=${limit}&offset=${offset}`),
    api<Page<SyncRun>>("/admin/marketing/sync-runs?limit=5"),
    currentRole(),
  ]);
  const currency = data.context.account?.currency;
  const rangeParams = { date_from: data.date_from, date_to: data.date_to };
  const tableQuery = new URLSearchParams({ ...rangeParams, sort, direction }).toString();
  const latest = data.context.latest_run;
  const m = data.meta;

  return <Shell title="Marketing performance"
    subtitle={`Meta Ads from ${data.date_from} to ${data.date_to}, read-only`}>
    <section className="executive-toolbar">
      <div><span className="section-kicker">Paid acquisition</span>
        <h2>Meta Ads vs business results</h2>
        <p>{data.context.account
          ? `${data.context.account.name || "Ad account"} - ${currency || "currency unknown"} - ${data.context.account.timezone_name || "timezone unknown"}`
          : "No ad account data yet"}{data.context.attribution_key
          && ` - attribution ${data.context.attribution_key.replace("|", ", reported at ")}`}</p></div>
      <form className="period-filter">
        <label><span>From</span><input type="date" name="date_from" defaultValue={data.date_from} /></label>
        <label><span>To</span><input type="date" name="date_to" defaultValue={data.date_to} /></label>
        <button className="button primary"><Icon name="calendar" size={17} />Apply range</button>
      </form>
    </section>

    <Freshness data={data} canSync={role === "admin" && data.context.configured} />
    {params.synced === "background" && <div className="alert success" role="status">
      Sync started in the background in 31-day chunks. Watch progress in Sync history below; refresh
      the page to see new data as each chunk finishes.</div>}
    {params.synced && params.synced !== "background" && <div className="alert success" role="status">
      Sync finished for the requested dates.</div>}
    {params.sync_error && <div className="alert error" role="alert">Sync failed: {params.sync_error}</div>}

    <section className="metric-grid executive-grid">
      <MetricCard label="Meta spend" value={<Amount value={m.spend} currency={currency} />}
        icon="rupee" detail={`${count(m.impressions)} impressions`} />
      <MetricCard label="Link clicks" value={count(m.link_clicks)} icon="trend" tone="blue"
        detail={`CTR ${ratio(m.ctr, "%")} - CPC ${m.cpc === null ? "-" : count(m.cpc)} - CPM ${m.cpm === null ? "-" : count(m.cpm)}`} />
      <MetricCard label="Meta-reported purchases" value={count(m.meta_purchases)} icon="bag" tone="gold"
        detail={`Value ${count(m.meta_purchase_value)} - ROAS ${ratio(m.meta_roas, "x")}`} />
      <MetricCard label="Business revenue (orders)" value={<Amount value={data.business.revenue} currency={currency || "INR"} />}
        icon="rupee" tone="plum" detail={`${count(data.business.orders)} orders - ${count(data.business.new_customers)} new customers`} />
      <MetricCard label="Blended MER" value={ratio(data.blended.mer, "x")} icon="spark"
        detail="business revenue / Meta spend" />
      <MetricCard label="New-customer CAC" value={<Amount value={data.blended.new_customer_cac} currency={currency} />}
        icon="users" tone="gold"
        detail={`Spend per order ${data.blended.spend_per_order === null ? "-" : count(data.blended.spend_per_order)}`} />
    </section>
    <p className="footnote">Meta purchases are platform-attributed. Business revenue, orders and new customers
      come from processed orders by order date. Blended MER and CAC compare the same dates only; they do not
      attribute individual orders to campaigns. Reach is summed per day ({count(m.reach_daily_sum)}), so it is
      not unique reach; average daily frequency is {ratio(m.avg_daily_frequency)}.</p>

    <section className="panel chart-card"><div className="chart-heading"><div>
      <span className="section-kicker">Daily trend</span><h2>Spend vs revenue</h2>
      <p>Meta spend by reporting date, with revenue from processed orders by order date.</p></div>
      <div className="chart-highlight"><span>Funnel (Meta)</span>
        <strong>{count(m.landing_page_views)} LPV</strong>
        <small>{count(m.add_to_cart)} ATC - {count(m.checkouts_initiated)} checkout - {count(m.leads)} leads</small></div>
    </div><SpendRevenueChart points={data.daily} /></section>

    <div className="list-heading"><h2>Campaigns</h2></div>
    <section className="panel table-wrap"><table><thead><tr>
      <th><SortLink label="Campaign" column="name" current={sort} direction={direction} path="/marketing" params={rangeParams} /></th>
      <th><SortLink label="Spend" column="spend" current={sort} direction={direction} path="/marketing" params={rangeParams} /></th>
      <th><SortLink label="Impressions" column="impressions" current={sort} direction={direction} path="/marketing" params={rangeParams} /></th>
      <th><SortLink label="Link clicks" column="link_clicks" current={sort} direction={direction} path="/marketing" params={rangeParams} /></th>
      <th><SortLink label="CTR" column="ctr" current={sort} direction={direction} path="/marketing" params={rangeParams} /></th>
      <th><SortLink label="CPC" column="cpc" current={sort} direction={direction} path="/marketing" params={rangeParams} /></th>
      <th><SortLink label="Meta purchases" column="meta_purchases" current={sort} direction={direction} path="/marketing" params={rangeParams} /></th>
      <th><SortLink label="Meta ROAS" column="meta_roas" current={sort} direction={direction} path="/marketing" params={rangeParams} /></th>
    </tr></thead><tbody>
      {campaigns.items.length === 0 && <tr><td colSpan={8} className="empty">No campaign data for this range.</td></tr>}
      {campaigns.items.map(c => <tr key={c.id}>
        <td><Link href={`/marketing/campaigns/${encodeURIComponent(c.id)}?${new URLSearchParams(rangeParams)}`}>
          {c.name}</Link><small>{c.objective || c.id}</small></td>
        <td><strong><Amount value={c.spend} currency={currency} /></strong></td>
        <td>{count(c.impressions)}</td><td>{count(c.link_clicks)}</td>
        <td>{ratio(c.ctr, "%")}</td><td>{c.cpc === null ? "-" : count(c.cpc)}</td>
        <td>{count(c.meta_purchases)}</td><td>{ratio(c.meta_roas, "x")}</td>
      </tr>)}</tbody></table></section>
    <Pager total={campaigns.total} offset={offset} limit={limit} path="/marketing" query={tableQuery} />

    {data.unclassified_actions.length > 0 && <section className="panel operations-command">
      <span className="section-kicker">Unclassified actions</span>
      <p>Meta reported these action types that are not mapped to a funnel metric. They stay in the raw
        data and are not dropped.</p>
      <div className="tabs">{data.unclassified_actions.map(a =>
        <span className="status-pill" key={a.action_type}>{a.action_type} ({a.rows})</span>)}</div>
    </section>}

    <div className="list-heading"><h2>Sync history</h2></div>
    <section className="panel table-wrap"><table><thead><tr><th>Started</th><th>Dates</th>
      <th>Trigger</th><th>Status</th><th>Rows</th><th>Spend vs control</th><th>Error</th></tr></thead>
      <tbody>{runs.items.length === 0 && <tr><td colSpan={7} className="empty">No syncs have run yet.</td></tr>}
        {runs.items.map(run => <tr key={run.id}>
          <td>{new Date(run.started_at).toLocaleString("en-IN")}</td>
          <td>{run.date_from} to {run.date_to}</td><td>{run.trigger}</td>
          <td><Status value={run.status} /></td><td>{count(run.row_count)}</td>
          <td>{run.normalized_spend === null ? "-" : `${count(run.normalized_spend)} / ${count(run.control_spend)}`}
            {run.control_difference !== null && Number(run.control_difference) !== 0
              && <small>differs by {count(run.control_difference)}</small>}</td>
          <td>{run.error_summary || ""}</td></tr>)}</tbody></table></section>

    {role === "admin" && <section className="panel operations-command">
      <span className="section-kicker">Manual re-fetch</span>
      {data.context.configured
        ? <form action={syncMarketing} className="inline-form">
          <label>From <input type="date" name="date_from" required defaultValue={data.date_from} /></label>
          <label>To <input type="date" name="date_to" required defaultValue={data.date_to} /></label>
          <button className="button primary">Sync from Meta</button>
          <small>Up to 31 days runs immediately; longer ranges (up to {MAX_SYNC_DAYS} days) run in the background.{latest?.status === "RUNNING" ? " A sync is running now." : ""}</small>
        </form>
        : <p>Meta is not configured on the API server. Set META_AD_ACCOUNT_ID, META_ACCESS_TOKEN and
          META_GRAPH_API_VERSION in the server environment.</p>}
    </section>}
  </Shell>;
}

function Freshness({ data, canSync }: { data: Overview; canSync: boolean }) {
  const latest = data.context.latest_run;
  const { coverage } = data;
  const failed = latest?.status === "FAILED" && <div className="alert error" role="alert">
    Latest Meta sync failed ({latest.date_from} to {latest.date_to}): {latest.error_summary || "unknown error"}.
    {data.context.last_successful_sync
      ? ` Figures below come from the last successful sync at ${new Date(data.context.last_successful_sync.finished_at).toLocaleString("en-IN")}.`
      : ""}
  </div>;
  if (!data.context.configured && !data.context.last_data_date) return <div className="alert" role="status">
    Meta is not configured on the API server, so no ad data has been synced.
  </div>;
  if (coverage.unsynced_days > 0 && coverage.first_unsynced && coverage.last_unsynced) {
    const fits = spanDays(coverage.first_unsynced, coverage.last_unsynced) <= MAX_SYNC_DAYS;
    return <>{failed}<div className="alert warning coverage-alert" role="status">
      <span>{coverage.unsynced_days} of {coverage.total_days} days in this range have not been fetched from
        Meta yet ({coverage.first_unsynced} to {coverage.last_unsynced}), so they show no spend.</span>
      {canSync && (fits
        ? <form action={syncMarketing}>
          <input type="hidden" name="date_from" value={coverage.first_unsynced} />
          <input type="hidden" name="date_to" value={coverage.last_unsynced} />
          <input type="hidden" name="view_from" value={data.date_from} />
          <input type="hidden" name="view_to" value={data.date_to} />
          <button className="button primary">Fetch these dates</button>
        </form>
        : <small>More than {MAX_SYNC_DAYS} days: run the backfill command
          (python -m db.import_meta_insights --from ... --to ...).</small>)}
    </div></>;
  }
  return failed || <div className="alert success" role="status">
    Every day in this range is synced from Meta
    {data.context.last_successful_sync ? `; last sync ${new Date(data.context.last_successful_sync.finished_at).toLocaleString("en-IN")}` : ""}.
  </div>;
}
