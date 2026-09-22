import Link from "next/link";
import { currentRole } from "@/lib/auth";
import { api, Page } from "@/lib/api";
import { Shell, Pager, Money } from "../components";
import { saveSegmentSettings } from "../actions";
import { Customer, CustomerTable } from "./customer-table";

const allowedSorts = [
  "last_order_date", "first_order_date", "lifetime_value", "order_count",
  "customer_name", "recency_days", "segment", "last_follow_up_at", "next_follow_up_at",
];
const allowedStatuses = [
  "NOT_CONTACTED", "CONTACTED", "NO_ANSWER", "CALLBACK", "INTERESTED",
  "NOT_INTERESTED", "DO_NOT_CONTACT",
];
const segments = [
  "CHAMPIONS", "LOYAL_REPEAT", "NEW_CUSTOMER", "HIGH_VALUE_ONE_TIME",
  "AT_RISK_REPEAT", "AT_RISK_HIGH_VALUE", "ACTIVE_ONE_TIME", "DORMANT_ONE_TIME",
];
const tags = [
  "RECENT_30D", "FIRST_TIME_BUYER", "REPEAT_BUYER", "HIGH_VALUE", "VIP_VALUE",
  "HAIR_COLOR", "HAIR_CARE", "SKIN_CARE", "HYDROSOL", "COMBO_BUYER",
];
const tagLabels: Record<string, string> = {
  RECENT_30D: "Recent 30 days", FIRST_TIME_BUYER: "First-time buyer",
  REPEAT_BUYER: "Repeat buyer", HIGH_VALUE: "High value", VIP_VALUE: "VIP value",
  HAIR_COLOR: "Hair colour buyer", HAIR_CARE: "Hair care buyer",
  SKIN_CARE: "Skin care buyer", HYDROSOL: "Hydrosol buyer",
  COMBO_BUYER: "Combo buyer",
};
const segmentDetails: Record<string, { label: string; meaning: string; action: string }> = {
  CHAMPIONS: { label: "Best repeat customers",
    meaning: "Buy often, spend more and bought recently",
    action: "Reward them and ask for referrals" },
  LOYAL_REPEAT: { label: "Regular repeat customers",
    meaning: "Bought more than once and are still active",
    action: "Cross-sell and keep them returning" },
  NEW_CUSTOMER: { label: "New first-order customers",
    meaning: "Made their first purchase recently",
    action: "Help them make a second purchase" },
  HIGH_VALUE_ONE_TIME: { label: "Big first-order customers",
    meaning: "Spent a high amount but bought only once",
    action: "Give them a priority personal follow-up" },
  AT_RISK_REPEAT: { label: "Repeat customers becoming inactive",
    meaning: "Bought repeatedly but have not returned recently",
    action: "Win them back now" },
  AT_RISK_HIGH_VALUE: { label: "Big spenders becoming inactive",
    meaning: "Spent a high amount once but have not returned",
    action: "Offer personal help and a relevant offer" },
  ACTIVE_ONE_TIME: { label: "Recent one-time customers",
    meaning: "Bought once and are still recent",
    action: "Explain the next useful product" },
  DORMANT_ONE_TIME: { label: "Old one-time customers",
    meaning: "Bought once a long time ago",
    action: "Use a low-cost reactivation campaign" },
};
type SegmentRow = {
  segment: string; customer_count: number; lifetime_value: string;
  average_lifetime_value: string; order_count: number;
};
type SegmentSettings = {
  new_customer_days: number; active_customer_days: number;
  champion_recency_days: number; champion_min_orders: number;
  high_value_percentile: string; vip_value_percentile: string;
};
type SegmentData = {
  segments: SegmentRow[];
  thresholds: { high_value: string; vip_value: string; latest_order_date: string };
  settings: SegmentSettings;
};

function bucketBasis(segment: string, analysis: SegmentData) {
  const s = analysis.settings;
  const high = Number(analysis.thresholds.high_value).toLocaleString("en-IN");
  const vip = Number(analysis.thresholds.vip_value).toLocaleString("en-IN");
  const rules: Record<string, string> = {
    CHAMPIONS: `${s.champion_min_orders}+ orders, at least \u20B9${vip} spent, bought within ${s.champion_recency_days} days`,
    LOYAL_REPEAT: `2+ orders and bought within ${s.active_customer_days} days`,
    NEW_CUSTOMER: `first order made within ${s.new_customer_days} days`,
    HIGH_VALUE_ONE_TIME: `one order of at least \u20B9${high}, within ${s.active_customer_days} days`,
    AT_RISK_REPEAT: `2+ orders, no purchase for over ${s.active_customer_days} days`,
    AT_RISK_HIGH_VALUE: `one order of at least \u20B9${high}, inactive over ${s.active_customer_days} days`,
    ACTIVE_ONE_TIME: `one lower-value order within ${s.active_customer_days} days`,
    DORMANT_ONE_TIME: `one lower-value order, inactive over ${s.active_customer_days} days`,
  };
  return rules[segment];
}

export default async function Customers({ searchParams }: {
  searchParams: Promise<{
    search?: string; offset?: string; sort?: string; direction?: string;
    follow_up_status?: string; segment?: string; tag?: string; sales_signal?: string;
  }>;
}) {
  const canWrite = (await currentRole()) === "admin";
  const params = await searchParams;
  const search = params.search || "", offset = Number(params.offset || 0), limit = 50;
  const sort = allowedSorts.includes(params.sort || "") ? params.sort! : "last_order_date";
  const direction = params.direction === "asc" ? "asc" : "desc";
  const followUpStatus = allowedStatuses.includes(params.follow_up_status || "")
    ? params.follow_up_status! : "";
  const segment = segments.includes(params.segment || "") ? params.segment! : "";
  const tag = tags.includes(params.tag || "") ? params.tag! : "";
  const salesSignals = ["HIGH_INTENT", "OFFER_INTEREST", "CONCERNS", "PRICE_HIGH"];
  const salesSignal = salesSignals.includes(params.sales_signal || "") ? params.sales_signal! : "";
  const query = new URLSearchParams({ sort, direction });
  if (search) query.set("search", search);
  if (followUpStatus) query.set("follow_up_status", followUpStatus);
  if (segment) query.set("segment", segment);
  if (tag) query.set("tag", tag);
  if (salesSignal) query.set("sales_signal", salesSignal);
  const [data, analysis] = await Promise.all([
    api<Page<Customer>>(`/customers?limit=${limit}&offset=${offset}&${query}`),
    api<SegmentData>("/admin/customer-segments"),
  ]);
  return <Shell title="Customers" subtitle="Prioritize retention, second purchases and win-back">
    <section className="segment-overview">
      <div className="segment-overview-heading">
        <div><p className="section-kicker">Customer opportunity</p>
          <h2>Easy-to-understand sales groups</h2></div>
        <p>High value starts at <strong><Money value={analysis.thresholds.high_value} /></strong>
          {" "}and VIP value at <strong><Money value={analysis.thresholds.vip_value} /></strong>.</p>
      </div>
      <div className="segment-grid">{analysis.segments.map(row => {
        const detail = segmentDetails[row.segment];
        const href = new URLSearchParams({ segment: row.segment });
        return <Link className={`segment-card ${row.segment.toLowerCase()} ${segment === row.segment ? "active" : ""}`}
          href={`/customers?${href}`} key={row.segment}>
          <span>{detail.label}</span><strong>{row.customer_count.toLocaleString("en-IN")}</strong>
          <small><b>{detail.meaning}.</b> {bucketBasis(row.segment, analysis)}.
            <br />Action: {detail.action}.</small>
          <em><Money value={row.lifetime_value} /> total customer value</em>
        </Link>;
      })}</div>
      <details className="segment-settings">
        <summary>{canWrite ? "See how these groups work or change the rules" : "See how these groups work"}</summary>
        <p>These rules define the customer groups for the whole team. Only administrators can change them.</p>
        <form action={canWrite ? saveSegmentSettings : undefined}>
          <label><span>A customer is new for</span><input disabled={!canWrite} type="number"
            name="new_customer_days" min="1" max="89"
            defaultValue={analysis.settings.new_customer_days} /><small>days after first order</small></label>
          <label><span>A customer stays active for</span><input disabled={!canWrite} type="number"
            name="active_customer_days" min="30" max="365"
            defaultValue={analysis.settings.active_customer_days} /><small>days after last order</small></label>
          <label><span>A best customer must buy within</span><input disabled={!canWrite} type="number"
            name="champion_recency_days" min="1" max="365"
            defaultValue={analysis.settings.champion_recency_days} /><small>days</small></label>
          <label><span>A best customer needs at least</span><input disabled={!canWrite} type="number"
            name="champion_min_orders" min="3" max="20"
            defaultValue={analysis.settings.champion_min_orders} /><small>orders</small></label>
          <label><span>High value means top</span><input disabled={!canWrite} type="number"
            name="high_value_percentile" min="50" max="95" step="1"
            defaultValue={Number(analysis.settings.high_value_percentile) * 100} />
            <small>percentile; now \u20B9{Number(analysis.thresholds.high_value).toLocaleString("en-IN")}</small></label>
          <label><span>VIP value means top</span><input disabled={!canWrite} type="number"
            name="vip_value_percentile" min="60" max="99" step="1"
            defaultValue={Number(analysis.settings.vip_value_percentile) * 100} />
            <small>percentile; now \u20B9{Number(analysis.thresholds.vip_value).toLocaleString("en-IN")}</small></label>
          {canWrite && <button className="button">Save group rules</button>}
        </form>
      </details>
    </section>
    <form className="search customer-search">
      <input name="search" defaultValue={search} placeholder="Name, phone, email or product" />
      <select name="segment" defaultValue={segment} aria-label="Filter by customer group">
        <option value="">All sales groups</option>
        {segments.map(value => <option value={value} key={value}>
          {segmentDetails[value].label}</option>)}
      </select>
      <select name="tag" defaultValue={tag} aria-label="Filter by customer tag">
        <option value="">All customer tags</option>
        {tags.map(value => <option value={value} key={value}>{tagLabels[value]}</option>)}
      </select>
      <select name="sales_signal" defaultValue={salesSignal} aria-label="Filter by call result">
        <option value="">All call results</option>
        <option value="HIGH_INTENT">Likely to order soon</option>
        <option value="OFFER_INTEREST">Interested in an offer</option>
        <option value="CONCERNS">Has concerns</option>
        <option value="PRICE_HIGH">Feels price is high</option>
      </select>
      <select name="follow_up_status" defaultValue={followUpStatus}
        aria-label="Filter by follow-up status">
        <option value="">All follow-up statuses</option>
        <option value="NOT_CONTACTED">Not contacted</option>
        <option value="CALLBACK">Callback due</option>
        <option value="NO_ANSWER">No answer</option>
        <option value="CONTACTED">Contacted</option>
        <option value="INTERESTED">Interested</option>
        <option value="NOT_INTERESTED">Not interested</option>
        <option value="DO_NOT_CONTACT">Do not contact</option>
      </select>
      <input type="hidden" name="sort" value={sort} />
      <input type="hidden" name="direction" value={direction} />
      <button className="button">Apply</button>
    </form>
    <CustomerTable canWrite={canWrite} customers={data.items} sort={sort} direction={direction}
      search={search} followUpStatus={followUpStatus} segment={segment} tag={tag}
      salesSignal={salesSignal} />
    <Pager total={data.total} offset={offset} limit={limit} path="/customers"
      query={query.toString()} />
  </Shell>;
}
