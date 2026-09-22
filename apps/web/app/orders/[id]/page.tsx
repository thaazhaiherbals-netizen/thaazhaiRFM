import { api } from "@/lib/api";
import { Shell, Money, Status } from "../../components";

type Detail = { order: Record<string, any>; items: Record<string, any>[] };

export default async function OrderDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params, data = await api<Detail>(`/orders/${id}`), o = data.order;
  return <Shell title={`Order ${o.source_record_id}`}>
    <section className="detail-grid"><div className="panel"><h2>Order</h2>
      <dl><dt>Date</dt><dd>{o.order_date}</dd><dt>Value</dt><dd><Money value={o.order_value} /></dd>
        <dt>Payment</dt><dd>{o.payment_method || "Unknown"}</dd><dt>Pincode</dt><dd>{o.delivery_pincode || "Unknown"}</dd></dl></div>
      <div className="panel"><h2>Customer</h2><dl><dt>Name</dt><dd>{o.customer_name || "Unknown"}</dd>
        <dt>Phone</dt><dd>{o.normalized_phone || "Unknown"}</dd><dt>Email</dt><dd>{o.email || "Unknown"}</dd></dl></div></section>
    <section className="panel table-wrap"><table><thead><tr><th>Raw item</th><th>Catalogue match</th>
      <th>Qty</th><th>Unit price</th><th>Total</th><th>Status</th></tr></thead><tbody>
      {data.items.map(i => <tr key={i.id}><td>{i.raw_product_name}<small>{i.raw_variant_name}</small></td>
        <td>{i.canonical_name || "Unmapped"}<small>{i.variant_name}</small></td><td>{i.quantity}</td>
        <td><Money value={i.unit_price} /></td><td><Money value={i.line_total} /></td>
        <td><Status value={i.mapping_status} /></td></tr>)}</tbody></table></section>
  </Shell>;
}
