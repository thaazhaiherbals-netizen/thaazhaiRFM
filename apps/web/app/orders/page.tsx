import Link from "next/link";
import { api, Page } from "@/lib/api";
import { Shell, Pager, SortLink } from "../components";
import { Order, OrderRows } from "./order-rows";
import { orderDateRange } from "@/lib/order-dates";
import { ListSummary } from "../list-summary";

const allowedSorts = ["order_date", "order_value", "item_count", "customer_name"];

export default async function Orders({ searchParams }: {
  searchParams: Promise<{ search?: string; offset?: string; sort?: string; direction?: string;
    start_date?: string; end_date?: string; period?: string }>;
}) {
  const params = await searchParams;
  const search = params.search || "", offset = Number(params.offset || 0), limit = 50;
  const sort = allowedSorts.includes(params.sort || "") ? params.sort! : "order_date";
  const direction = params.direction === "asc" ? "asc" : "desc";
  const query = new URLSearchParams({ sort, direction });
  if (search) query.set("search", search);
  const validDate = (value?: string) => !!value && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
  const preset = orderDateRange(params.period || "");
  const period = preset ? params.period! : "";
  const start = preset?.start ?? (validDate(params.start_date) ? params.start_date! : "");
  const end = preset?.end ?? (validDate(params.end_date) ? params.end_date! : "");
  const invalid = !preset && ((!!params.start_date && !start) || (!!params.end_date && !end)
    || (!!start && !!end && start > end));
  if (start) query.set("start_date", start);
  if (end) query.set("end_date", end);
  const data = invalid ? { items: [], total: 0, summary: { revenue: "0", average_order_value: "0", customers: 0 } }
    : await api<Page<Order> & { summary: { revenue: string; average_order_value: string; customers: number } }>(`/orders?limit=${limit}&offset=${offset}&${query}`);
  if (period) query.set("period", period);
  const sortParams: Record<string, string> = search ? { search } : {};
  if (start) sortParams.start_date = start;
  if (end) sortParams.end_date = end;
  if (period) sortParams.period = period;
  return <Shell title="Orders" subtitle="Find orders by customer, product or purchase date">
    <section className="order-date-shortcuts" aria-label="Quick order date filters">
      <strong>Purchase date</strong><div>
      {[["", "All dates"], ["today", "Today"], ["yesterday", "Yesterday"], ["week", "This week"], ["month", "This month"]].map(([value, label]) => {
        const shortcut = new URLSearchParams({ sort, direction });
        if (search) shortcut.set("search", search);
        if (value) shortcut.set("period", value);
        const active = value ? period === value : !period && !start && !end;
        return <Link className={`button ${active ? "primary" : ""}`} key={value}
          aria-current={active ? "page" : undefined} href={`/orders?${shortcut}`}>{label}</Link>;
      })}</div><p>India time · Weeks start Monday · This week and this month include orders through today.</p>
    </section>
    <form className="search order-filters" key={query.toString()}>
    <label>Search orders<input name="search" defaultValue={search}
    placeholder="Order, customer, phone or product" /></label>
    <label>From date<input type="date" name="start_date" defaultValue={start} max={end || undefined} /></label>
    <label>To date<input type="date" name="end_date" defaultValue={end} min={start || undefined} /></label>
    <input type="hidden" name="sort" value={sort} />
    <input type="hidden" name="direction" value={direction} />
    <button className="button primary">Apply filters</button><Link className="button" href="/orders">Clear</Link></form>
    {invalid && <p className="alert error" role="alert">Choose valid dates with the from date on or before the to date.</p>}
    {!invalid && <ListSummary title="Order overview" description="All orders matching the current date and search filters, across every page."
      cards={[
        { label: "Orders", value: data.total, hint: "Matching orders" },
        { label: "Order value", value: data.summary.revenue, money: true, hint: "Total value of matching orders" },
        { label: "Average order", value: data.summary.average_order_value, money: true, hint: "Average value per matching order" },
        { label: "Customers", value: data.summary.customers, hint: "Unique customers in these orders" },
      ]} />}
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
      <OrderRows key={`${query}:${offset}`} orders={data.items} /></table></section>
    <Pager total={data.total} offset={offset} limit={limit} path="/orders" query={query.toString()} />
  </Shell>;
}


