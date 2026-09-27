import Link from "next/link";
import { api, Page } from "@/lib/api";
import { Shell, Money, Pager, SortLink } from "../components";

type Order = { id: string; source_record_id: string; order_date: string; order_value: string;
  customer_name?: string; normalized_phone?: string; item_count: number; pending_items: number;
  delivery_city?: string; delivery_pincode?: string };

const allowedSorts = ["order_date", "order_value", "item_count", "customer_name"];

export default async function Orders({ searchParams }: {
  searchParams: Promise<{ search?: string; offset?: string; sort?: string; direction?: string;
    start_date?: string; end_date?: string }>;
}) {
  const params = await searchParams;
  const search = params.search || "", offset = Number(params.offset || 0), limit = 50;
  const sort = allowedSorts.includes(params.sort || "") ? params.sort! : "order_date";
  const direction = params.direction === "asc" ? "asc" : "desc";
  const query = new URLSearchParams({ sort, direction });
  if (search) query.set("search", search);
  const validDate = (value?: string) => !!value && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
  const start = validDate(params.start_date) ? params.start_date! : "";
  const end = validDate(params.end_date) ? params.end_date! : "";
  const invalid = (!!params.start_date && !start) || (!!params.end_date && !end)
    || (!!start && !!end && start > end);
  if (start) query.set("start_date", start);
  if (end) query.set("end_date", end);
  const data = invalid ? { items: [], total: 0 } : await api<Page<Order>>(`/orders?limit=${limit}&offset=${offset}&${query}`);
  const sortParams: Record<string, string> = search ? { search } : {};
  if (start) sortParams.start_date = start;
  if (end) sortParams.end_date = end;
  return <Shell title="Orders" subtitle="Find orders by customer, product or purchase date">
    <form className="search order-filters">
    <label>Search orders<input name="search" defaultValue={search}
    placeholder="Order, customer, phone or product" /></label>
    <label>From date<input type="date" name="start_date" defaultValue={start} max={end || undefined} /></label>
    <label>To date<input type="date" name="end_date" defaultValue={end} min={start || undefined} /></label>
    <input type="hidden" name="sort" value={sort} />
    <input type="hidden" name="direction" value={direction} />
    <button className="button primary">Apply filters</button><Link className="button" href="/orders">Clear</Link></form>
    {invalid && <p className="alert error" role="alert">Choose valid dates with the from date on or before the to date.</p>}
    <p>{data.total.toLocaleString("en-IN")} orders found · Date range includes both selected dates</p>
    <section className="panel table-wrap"><table className="orders-table"><thead><tr><th>Order</th>
      <th><SortLink label="Date" column="order_date" current={sort} direction={direction}
        path="/orders" params={sortParams} /></th>
      <th><SortLink label="Customer" column="customer_name" current={sort} direction={direction}
        path="/orders" params={sortParams} /></th><th>Location</th>
      <th><SortLink label="Items" column="item_count" current={sort} direction={direction}
        path="/orders" params={sortParams} /></th>
      <th><SortLink label="Value" column="order_value" current={sort} direction={direction}
        path="/orders" params={sortParams} /></th></tr></thead>
      <tbody>{!data.items.length && <tr><td colSpan={6}>No orders match these filters. Try a different date range or search.</td></tr>}{data.items.map(o => <tr className="order-list-row" key={o.id}><td><Link
        className="order-number" href={`/orders/${o.id}`}>#{o.source_record_id}</Link></td>
        <td>{o.order_date}</td><td>{o.customer_name || "Unknown"}<small>{o.normalized_phone}</small></td>
        <td>{o.delivery_city || o.delivery_pincode || "Unknown"}</td>
        <td><span className="item-count-chip">{o.item_count}</span>
          {o.pending_items ? ` (${o.pending_items} pending)` : ""}</td>
        <td><strong className="order-value-chip"><Money value={o.order_value} /></strong></td></tr>)}</tbody></table></section>
    <Pager total={data.total} offset={offset} limit={limit} path="/orders" query={query.toString()} />
  </Shell>;
}


