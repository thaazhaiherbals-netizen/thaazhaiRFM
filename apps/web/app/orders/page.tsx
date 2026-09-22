import Link from "next/link";
import { api, Page } from "@/lib/api";
import { Shell, Money, Pager, SortLink } from "../components";

type Order = { id: string; source_record_id: string; order_date: string; order_value: string;
  customer_name?: string; normalized_phone?: string; item_count: number; pending_items: number;
  delivery_city?: string; delivery_pincode?: string };

const allowedSorts = ["order_date", "order_value", "item_count", "customer_name"];

export default async function Orders({ searchParams }: {
  searchParams: Promise<{ search?: string; offset?: string; sort?: string; direction?: string }>;
}) {
  const params = await searchParams;
  const search = params.search || "", offset = Number(params.offset || 0), limit = 50;
  const sort = allowedSorts.includes(params.sort || "") ? params.sort! : "order_date";
  const direction = params.direction === "asc" ? "asc" : "desc";
  const query = new URLSearchParams({ sort, direction });
  if (search) query.set("search", search);
  const data = await api<Page<Order>>(`/orders?limit=${limit}&offset=${offset}&${query}`);
  const sortParams: Record<string, string> = search ? { search } : {};
  return <Shell title="Orders"><form className="search"><input name="search" defaultValue={search}
    placeholder="Order, customer, phone or product" />
    <input type="hidden" name="sort" value={sort} />
    <input type="hidden" name="direction" value={direction} />
    <button className="button">Search</button></form>
    <section className="panel table-wrap"><table className="orders-table"><thead><tr><th>Order</th>
      <th><SortLink label="Date" column="order_date" current={sort} direction={direction}
        path="/orders" params={sortParams} /></th>
      <th><SortLink label="Customer" column="customer_name" current={sort} direction={direction}
        path="/orders" params={sortParams} /></th><th>Location</th>
      <th><SortLink label="Items" column="item_count" current={sort} direction={direction}
        path="/orders" params={sortParams} /></th>
      <th><SortLink label="Value" column="order_value" current={sort} direction={direction}
        path="/orders" params={sortParams} /></th></tr></thead>
      <tbody>{data.items.map(o => <tr className="order-list-row" key={o.id}><td><Link
        className="order-number" href={`/orders/${o.id}`}>#{o.source_record_id}</Link></td>
        <td>{o.order_date}</td><td>{o.customer_name || "Unknown"}<small>{o.normalized_phone}</small></td>
        <td>{o.delivery_city || o.delivery_pincode || "Unknown"}</td>
        <td><span className="item-count-chip">{o.item_count}</span>
          {o.pending_items ? ` (${o.pending_items} pending)` : ""}</td>
        <td><strong className="order-value-chip"><Money value={o.order_value} /></strong></td></tr>)}</tbody></table></section>
    <Pager total={data.total} offset={offset} limit={limit} path="/orders" query={query.toString()} />
  </Shell>;
}


