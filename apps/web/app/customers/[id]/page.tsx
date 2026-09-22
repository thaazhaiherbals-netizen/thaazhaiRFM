import Link from "next/link";
import { api } from "@/lib/api";
import { Shell, Money } from "../../components";

type Detail = {
  customer: Record<string, any>;
  orders: Record<string, any>[];
  follow_ups: Record<string, any>[];
};
const formatDateTime = (value: string) =>
  new Date(value).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });

export default async function CustomerDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params, data = await api<Detail>(`/customers/${id}`), c = data.customer;
  return <Shell title={c.customer_name || "Customer"}>
    <section className="panel"><dl className="wide-dl"><dt>Phone</dt><dd>{c.normalized_phone}</dd>
      <dt>Email</dt><dd>{c.email || "Unknown"}</dd><dt>First order</dt><dd>{c.first_order_date}</dd>
      <dt>Last order</dt><dd>{c.last_order_date}</dd></dl></section>
    <section className="panel"><div className="panel-heading"><h2>Contact history</h2>
      <span>{data.follow_ups.length} updates</span></div>
      {data.follow_ups.length === 0 ? <p>No follow-up recorded yet.</p> :
        <div className="follow-up-history">{data.follow_ups.map(item => <article key={item.id}>
          <span className={`follow-up-pill ${item.status.toLowerCase()}`}>
            {String(item.status).replaceAll("_", " ")}</span>
          <div><strong>{item.contacted_by} via {String(item.channel).toLowerCase()}</strong>
            <small>{formatDateTime(item.contacted_at)}</small>
            {item.notes && <p>{item.notes}</p>}</div>
        </article>)}</div>}
    </section>
    <section className="panel table-wrap"><table><thead><tr><th>Order</th><th>Date</th>
      <th>Payment</th><th>Location</th><th>Value</th></tr></thead><tbody>{data.orders.map(o =>
      <tr key={o.id}><td><Link href={`/orders/${o.id}`}>{o.source_record_id}</Link></td>
        <td>{o.order_date}</td><td>{o.payment_method || "Unknown"}</td>
        <td>{o.delivery_city || o.delivery_pincode || "Unknown"}</td>
        <td><Money value={o.order_value} /></td></tr>)}
    </tbody></table></section>
  </Shell>;
}
