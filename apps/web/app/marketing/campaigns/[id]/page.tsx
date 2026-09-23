import Link from "next/link";
import { api } from "@/lib/api";
import { Shell } from "../../../components";
import { MetricCard } from "../../../dashboard-charts";
import { Amount, count, ratio, Totals } from "../../marketing-ui";

type Row = Totals & { id: string; name: string; parent_id?: string };
type Detail = {
  date_from: string; date_to: string;
  campaign: { campaign_id: string; name: string | null; objective: string | null; status: string | null };
  totals: Totals; ad_sets: Row[]; ads: Row[];
};
type Overview = { context: { account: { currency: string | null } | null } };

const isoDate = /^\d{4}-\d{2}-\d{2}$/;

export default async function CampaignDetail({ params, searchParams }: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ date_from?: string; date_to?: string }>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const range = new URLSearchParams();
  if (isoDate.test(query.date_from || "")) range.set("date_from", query.date_from!);
  if (isoDate.test(query.date_to || "")) range.set("date_to", query.date_to!);
  const [data, overview] = await Promise.all([
    api<Detail>(`/admin/marketing/campaigns/${encodeURIComponent(id)}?${range}`),
    api<Overview>(`/admin/marketing/overview?${range}`),
  ]);
  const currency = overview.context.account?.currency;
  const t = data.totals;
  const adSetNames = new Map(data.ad_sets.map(set => [set.id, set.name]));

  return <Shell title={data.campaign.name || data.campaign.campaign_id}
    subtitle={`${data.campaign.objective || "Campaign"} - ${data.date_from} to ${data.date_to}`}>
    <p><Link href={`/marketing?${range}`}>Back to marketing</Link></p>
    <section className="metric-grid executive-grid">
      <MetricCard label="Spend" value={<Amount value={t.spend} currency={currency} />} icon="rupee"
        detail={`${count(t.impressions)} impressions - CPM ${t.cpm === null ? "-" : count(t.cpm)}`} />
      <MetricCard label="Link clicks" value={count(t.link_clicks)} icon="trend" tone="blue"
        detail={`CTR ${ratio(t.ctr, "%")} - CPC ${t.cpc === null ? "-" : count(t.cpc)}`} />
      <MetricCard label="Meta-reported purchases" value={count(t.meta_purchases)} icon="bag" tone="gold"
        detail={`Value ${count(t.meta_purchase_value)} - ROAS ${ratio(t.meta_roas, "x")}`} />
    </section>
    <p className="footnote">Campaign results are Meta-attributed. Business orders are not attributed to
      campaigns until orders carry UTM or click IDs.</p>
    <BreakdownTable title="Ad sets" rows={data.ad_sets} currency={currency} />
    <BreakdownTable title="Ads" rows={data.ads} currency={currency} parentNames={adSetNames} />
  </Shell>;
}

function BreakdownTable({ title, rows, currency, parentNames }: {
  title: string; rows: Row[]; currency?: string | null; parentNames?: Map<string, string>;
}) {
  return <>
    <div className="list-heading"><h2>{title}</h2></div>
    <section className="panel table-wrap"><table><thead><tr><th>Name</th><th>Spend</th>
      <th>Impressions</th><th>Link clicks</th><th>CTR</th><th>CPC</th><th>Meta purchases</th>
      <th>Meta ROAS</th></tr></thead><tbody>
      {rows.length === 0 && <tr><td colSpan={8} className="empty">No data in this range.</td></tr>}
      {rows.map(row => <tr key={row.id}>
        <td>{row.name}<small>{parentNames && row.parent_id
          ? parentNames.get(row.parent_id) || row.parent_id : row.id}</small></td>
        <td><strong><Amount value={row.spend} currency={currency} /></strong></td>
        <td>{count(row.impressions)}</td><td>{count(row.link_clicks)}</td>
        <td>{ratio(row.ctr, "%")}</td><td>{row.cpc === null ? "-" : count(row.cpc)}</td>
        <td>{count(row.meta_purchases)}</td><td>{ratio(row.meta_roas, "x")}</td>
      </tr>)}</tbody></table></section>
  </>;
}
