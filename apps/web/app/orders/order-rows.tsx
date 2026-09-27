"use client";

import { Fragment, useEffect, useState } from "react";

export type Order = { id: string; source_record_id: string; order_date: string; order_value: string;
  customer_name?: string; normalized_phone?: string; item_count: number; pending_items: number;
  delivery_city?: string; delivery_pincode?: string };
type Detail = { order: Order & { payment_method?: string; email?: string }; items: {
  id: string; raw_product_name: string; raw_variant_name?: string; canonical_name?: string;
  variant_name?: string; quantity: number; unit_price: string; line_total: string; mapping_status: string;
}[] };
const money = (value: string) => "₹" + Number(value).toLocaleString("en-IN", {
  minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function OrderRows({ orders }: { orders: Order[] }) {
  const [expanded, setExpanded] = useState<string>();
  return <tbody>{!orders.length && <tr><td colSpan={6}>No orders match these filters. Try a different date range or search.</td></tr>}
    {orders.map(order => <Fragment key={order.id}>
      <tr className={`order-list-row ${expanded === order.id ? "order-selected" : ""}`}>
        <td><button type="button" className="order-expand" aria-expanded={expanded === order.id}
          aria-controls={`order-detail-${order.id}`} onClick={() => setExpanded(expanded === order.id ? undefined : order.id)}>
          <span aria-hidden="true">{expanded === order.id ? "−" : "+"}</span>
          <span>#{order.source_record_id}<small>{expanded === order.id ? "Hide details" : "View details"}</small></span>
        </button></td>
        <td>{order.order_date}</td><td>{order.customer_name || "Unknown"}<small>{order.normalized_phone}</small></td>
        <td>{order.delivery_city || order.delivery_pincode || "Unknown"}</td>
        <td><span className="item-count-chip">{order.item_count}</span>{order.pending_items ? ` (${order.pending_items} pending)` : ""}</td>
        <td><strong className="order-value-chip">{money(order.order_value)}</strong></td>
      </tr>
      {expanded === order.id && <tr className="order-expanded-row"><td colSpan={6}>
        <div id={`order-detail-${order.id}`}><InlineOrderDetail id={order.id} /></div>
      </td></tr>}
    </Fragment>)}
  </tbody>;
}

function InlineOrderDetail({ id }: { id: string }) {
  const [data, setData] = useState<Detail>();
  const [error, setError] = useState<string>();
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(undefined); setError(undefined);
    async function load() {
      try {
        const response = await fetch(`/api/orders/${id}`, { signal: controller.signal });
        if (!response.ok) throw new Error("Could not load this order's details.");
        const detail: Detail = await response.json();
        if (!controller.signal.aborted) setData(detail);
      } catch (reason) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Could not load order.");
      }
    }
    void load();
    return () => controller.abort();
  }, [id, retry]);
  return <section className="inline-order-detail" aria-label="Order details" aria-live="polite" aria-busy={!data && !error}>
    {error ? <div role="alert"><p>{error}</p><button className="button" onClick={() => setRetry(value => value + 1)}>Try again</button></div>
      : !data ? <p>Loading order details…</p> : <>
        <h3>Order #{data.order.source_record_id}</h3>
        <div className="inline-order-summary"><section><h4>Order information</h4>
          <dl><dt>Date</dt><dd>{data.order.order_date}</dd><dt>Total</dt><dd>{money(data.order.order_value)}</dd>
            <dt>Payment</dt><dd>{data.order.payment_method || "Not recorded"}</dd>
            <dt>Location</dt><dd>{[data.order.delivery_city, data.order.delivery_pincode].filter(Boolean).join(" · ") || "Not recorded"}</dd></dl>
        </section><section><h4>Customer</h4><dl><dt>Name</dt><dd>{data.order.customer_name || "Unknown"}</dd>
          <dt>Phone</dt><dd>{data.order.normalized_phone || "Not recorded"}</dd><dt>Email</dt><dd>{data.order.email || "Not recorded"}</dd></dl></section></div>
        <h4>Products purchased</h4><div className="table-wrap"><table className="item-table">
          <thead><tr><th>Product</th><th>Catalogue match</th><th>Quantity</th><th>Unit price</th><th>Total</th><th>Status</th></tr></thead>
          <tbody>{!data.items.length && <tr><td colSpan={6}>No products recorded.</td></tr>}
            {data.items.map(item => <tr key={item.id}><td>{item.raw_product_name}<small>{item.raw_variant_name}</small></td>
              <td>{item.canonical_name || "Unmapped"}<small>{item.variant_name}</small></td><td>{item.quantity}</td>
              <td>{money(item.unit_price)}</td><td>{money(item.line_total)}</td><td>{item.mapping_status.replaceAll("_", " ")}</td></tr>)}</tbody>
        </table></div>
      </>}
  </section>;
}
